from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import Config, condition_name
from .data import load_hotpotqa
from .llm import LLMClient
from .loop import _answer_dataset
from .metrics import accuracy_consensus


def calibration_candidates(base: dict[str, Any]) -> list[Config]:
    configs: list[Config] = []
    for use_context in (False, True):
        for max_tokens in (256, 384):
            label = "ctx" if use_context else "qonly"
            params = {
                **base,
                "n_solvers": 1,
                "use_ground_truth": False,
                "use_context": use_context,
                "max_tokens_solver": max_tokens,
                "T": 1,
                "batch_M": 0,
                "n_train": 0,
                "heldout_size": 50,
                "run_id": f"calib_{label}_tok{max_tokens}",
            }
            configs.append(Config(**params))
    return configs


def select_calibration(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    viable = [row for row in rows if 0.25 <= float(row["A0"]) <= 0.60]
    if not viable:
        return None
    viable.sort(key=lambda row: (int(row["max_tokens_solver"]), 0 if row["use_context"] else 1, float(row["trace_total_tokens"])))
    return viable[0]


async def run_calibration(configs: list[Config]) -> dict[str, Any]:
    max_heldout = max(cfg.heldout_size for cfg in configs)
    seed = configs[0].seed
    _, heldout = load_hotpotqa(0, max_heldout, seed)
    out_dir = configs[0].output_path()
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    started_all = time.time()
    for cfg in configs:
        llm = LLMClient(cfg)
        started = time.time()
        results = await _answer_dataset(heldout[: cfg.heldout_size], [], cfg, llm)
        metrics = accuracy_consensus(results)
        row = {
            "condition": condition_name(cfg),
            "use_context": cfg.use_context,
            "max_tokens_solver": cfg.max_tokens_solver,
            "heldout_size": cfg.heldout_size,
            "A0": metrics["A_t"],
            "C0": metrics["C_t"],
            "G0": metrics["G_t"],
            "llm": llm.stats.public_summary(),
            "trace_total_tokens": llm.stats.public_summary().get("trace_total_tokens", llm.stats.total_tokens),
            "elapsed_sec": time.time() - started,
        }
        rows.append(row)
        print(
            f"[calibration] {row['condition']} A0={row['A0']:.3f} C0={row['C0']:.3f} "
            f"tokens={row['trace_total_tokens']} hit={row['llm']['cache_hit_rate']:.3f}",
            flush=True,
        )
    selected = select_calibration(rows)
    payload = {
        "rows": rows,
        "selected": selected,
        "stop_rule": selected is None,
        "elapsed_sec": time.time() - started_all,
        "selection_rule": "Prefer A0 in [0.25, 0.60] with smallest max_tokens_solver.",
    }
    (out_dir / "calibration.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_calibration_report(payload, out_dir)
    return payload


def write_calibration_report(payload: dict[str, Any], out_dir: Path) -> Path:
    lines = [
        "# SEC A0 Calibration Report",
        "",
        "| condition | context | max tokens | A0 | C0 | G0 | trace tokens | cache hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {condition} | {ctx} | {tok} | {a:.3f} | {c:.3f} | {g:.3f} | {tokens} | {hit:.3f} |".format(
                condition=row["condition"],
                ctx=str(row["use_context"]),
                tok=row["max_tokens_solver"],
                a=row["A0"],
                c=row["C0"],
                g=row["G0"],
                tokens=row["trace_total_tokens"],
                hit=row["llm"]["cache_hit_rate"],
            )
        )
    lines.append("")
    if payload["selected"] is None:
        lines.append("Stop rule triggered: no setting reached A0 in [0.25, 0.60]. Do not run full yet.")
    else:
        selected = payload["selected"]
        lines.append(
            "Selected setting: `{}` (`use_context={}`, `max_tokens_solver={}`).".format(
                selected["condition"],
                selected["use_context"],
                selected["max_tokens_solver"],
            )
        )
    path = out_dir / "CALIBRATION.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
