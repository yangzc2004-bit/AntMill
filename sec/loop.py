from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from .config import Config, condition_name
from .data import batch_without_replacement, gold_map
from .fusion import reviewer_synthesize
from .llm import LLMClient
from .metrics import accuracy_consensus, detect_collapse, eff_rank, ews
from .solver import solver_answer


async def _answer_dataset(rows: list[dict[str, str]], library: list[dict[str, Any]], cfg: Config, llm: LLMClient) -> list[dict[str, Any]]:
    tasks = []
    meta = []
    for row in rows:
        for solver_id in range(cfg.n_solvers):
            tasks.append(
                solver_answer(
                    row["question"],
                    row.get("context", ""),
                    library,
                    cfg.solver_temp,
                    cfg=cfg,
                    llm=llm,
                    solver_id=solver_id,
                )
            )
            meta.append((row, solver_id))
    outputs = await asyncio.gather(*tasks)
    grouped: dict[str, dict[str, Any]] = {}
    for (row, _solver_id), output in zip(meta, outputs, strict=True):
        key = row["question"]
        grouped.setdefault(key, {"question": row["question"], "gold": row["answer"], "answers": []})
        grouped[key]["answers"].append(output)
    return list(grouped.values())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_one(cfg: Config, train_pool: list[dict[str, str]], heldout: list[dict[str, str]]) -> dict[str, Any]:
    llm = LLMClient(cfg)
    library: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []
    batch_gold = gold_map(train_pool)
    out_dir = cfg.output_path() / condition_name(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    for t in range(cfg.T):
        train_batch = batch_without_replacement(train_pool, cfg.batch_M, t) if cfg.batch_M else []
        heldout_results = await _answer_dataset(heldout, library, cfg, llm)
        metrics = accuracy_consensus(heldout_results)
        metrics["eff_rank"] = eff_rank(library)

        if train_batch:
            batch_results = await _answer_dataset(train_batch, library, cfg, llm)
            library = await reviewer_synthesize(
                [{"question": row["question"], "answers": row["answers"]} for row in batch_results],
                library,
                cfg,
                llm=llm,
                gold=batch_gold if cfg.use_ground_truth else None,
            )
        row = {
            "t": t,
            **metrics,
            "library_size": len(library),
            "tokens_total_so_far": llm.stats.total_tokens,
            "cache_hits_so_far": llm.stats.cache_hits,
            "network_calls_so_far": llm.stats.network_calls,
        }
        log.append(row)
        print(
            f"[{condition_name(cfg)}] t={t:02d} A={row['A_t']:.3f} C={row['C_t']:.3f} "
            f"G={row['G_t']:.3f} lib={len(library)} tokens={llm.stats.total_tokens}",
            flush=True,
        )
        _write_json(out_dir / "partial.json", {"config": cfg.to_public_dict(), "log": log, "library": library})

    a_list = [float(row["A_t"]) for row in log]
    g_list = [float(row["G_t"]) for row in log]
    summary = {
        "condition": condition_name(cfg),
        "t_star": detect_collapse(a_list, delta=cfg.delta, k_persist=cfg.k_persist, rho_minrise=cfg.rho_minrise),
        "A_peak": max(a_list) if a_list else 0.0,
        "A_final": a_list[-1] if a_list else 0.0,
        "A_drop": (max(a_list) - a_list[-1]) if a_list else 0.0,
        "ews_G": ews(g_list),
        "llm": llm.stats.public_summary(),
        "elapsed_sec": time.time() - started,
    }
    result = {"config": cfg.to_public_dict(), "log": log, "summary": summary, "library": library}
    _write_json(out_dir / "result.json", result)
    return result
