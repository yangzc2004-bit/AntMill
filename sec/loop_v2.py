from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from .config import Config, condition_name
from .data import batch_without_replacement, gold_map
from .debate import debate_answer
from .fusion import reviewer_synthesize_v2
from .llm import LLMClient
from .memory import InsightMemory
from .metrics import (
    answer_entropy,
    detect_collapse,
    eff_rank,
    eval_metrics,
    exact_match,
    ews,
    joint_collapse,
    majority_cluster,
)
from .solver import render_library  # noqa: F401  (kept for parity / debugging)


def _per_question(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-held-out-question records, needed for paired bootstrap across arms."""
    rows: list[dict[str, Any]] = []
    for item in items:
        majority = majority_cluster(item["answers"])
        rows.append(
            {
                "question": item["question"],
                "correct": 1 if exact_match(majority["answer"], item["gold"]) else 0,
                "consensus": len(majority["indices"]) / max(len(item["answers"]), 1),
                "entropy": answer_entropy(item["answers"]),
            }
        )
    return rows


async def _answer_dataset_debate(
    rows: list[dict[str, str]], memory: InsightMemory, cfg: Config, llm: LLMClient
) -> list[dict[str, Any]]:
    tasks = [debate_answer(row["question"], row.get("context", ""), memory, cfg, llm) for row in rows]
    per_row = await asyncio.gather(*tasks)
    grouped: list[dict[str, Any]] = []
    for row, per_agent in zip(rows, per_row, strict=True):
        grouped.append(
            {
                "question": row["question"],
                "gold": row["answer"],
                "answers": [agent["final"] for agent in per_agent],
                "trajectories": per_agent,
            }
        )
    return grouped


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_one_v2(cfg: Config, train_pool: list[dict[str, str]], heldout: list[dict[str, str]]) -> dict[str, Any]:
    llm = LLMClient(cfg)
    memory = InsightMemory(cfg)
    log: list[dict[str, Any]] = []
    batch_gold = gold_map(train_pool)
    rng = random.Random(cfg.seed)
    out_dir = cfg.output_path() / condition_name(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    last_details: list[dict[str, Any]] = []
    for t in range(cfg.T):
        heldout_results = await _answer_dataset_debate(heldout, memory, cfg, llm)
        metrics = eval_metrics(heldout_results)
        metrics["eff_rank"] = eff_rank(memory.all_items())
        last_details = _per_question(heldout_results)

        anchored = False
        if cfg.batch_M and cfg.memory_mode != "none":
            train_batch = batch_without_replacement(train_pool, cfg.batch_M, t)
            anchored = rng.random() < cfg.anchor_rho
            batch_results = await _answer_dataset_debate(train_batch, memory, cfg, llm)
            await reviewer_synthesize_v2(
                [{"question": r["question"], "answers": r["answers"]} for r in batch_results],
                memory,
                cfg,
                llm=llm,
                gold=batch_gold,
                use_gold=anchored,
            )

        row = {
            "t": t,
            **metrics,
            "anchored": anchored,
            "memory_size": memory.size(),
            "tokens_total_so_far": llm.stats.total_tokens,
            "cache_hits_so_far": llm.stats.cache_hits,
            "network_calls_so_far": llm.stats.network_calls,
        }
        log.append(row)
        print(
            f"[{condition_name(cfg)}] t={t:02d} A={row['A_t']:.3f} C={row['C_t']:.3f} "
            f"G={row['G_t']:.3f} D={row['D_t']:.3f} mem={memory.size()} "
            f"anchor={int(anchored)} tokens={llm.stats.total_tokens}",
            flush=True,
        )
        _write_json(
            out_dir / "partial.json",
            {"config": cfg.to_public_dict(), "log": log, "memory": memory.snapshot()},
        )

    a_list = [float(r["A_t"]) for r in log]
    c_list = [float(r["C_t"]) for r in log]
    d_list = [float(r["D_t"]) for r in log]
    g_list = [float(r["G_t"]) for r in log]
    collapse = joint_collapse(
        a_list,
        c_list,
        d_list,
        delta=cfg.delta,
        k_persist=cfg.k_persist,
    )
    summary = {
        "condition": condition_name(cfg),
        "memory_mode": cfg.memory_mode,
        "anchor_rho": cfg.anchor_rho,
        "debate_rounds": cfg.debate_rounds,
        "n_solvers": cfg.n_solvers,
        "t_star": collapse["t_star"],
        "collapse": collapse,
        "A_peak": max(a_list) if a_list else 0.0,
        "A_final": a_list[-1] if a_list else 0.0,
        "A_drop": (max(a_list) - a_list[-1]) if a_list else 0.0,
        "C_final": c_list[-1] if c_list else 0.0,
        "D_first": d_list[0] if d_list else 0.0,
        "D_final": d_list[-1] if d_list else 0.0,
        "ews_D": ews(d_list),
        "ews_G": ews(g_list),
        "detect_collapse_A": detect_collapse(a_list, delta=cfg.delta, k_persist=cfg.k_persist, rho_minrise=cfg.rho_minrise),
        "llm": llm.stats.public_summary(),
        "elapsed_sec": time.time() - started,
    }
    result = {
        "config": cfg.to_public_dict(),
        "log": log,
        "summary": summary,
        "memory": memory.snapshot(),
        "final_eval": last_details,
    }
    _write_json(out_dir / "result.json", result)
    return result
