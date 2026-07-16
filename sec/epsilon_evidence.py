from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .maze_stats import PAIRED_METRICS, hierarchical_paired_diff, per_seed_paired_effects, route_rows


CONTROL_ARMS = [
    "epsilon_frozen_reviewer",
    "epsilon_private_consolidated",
    "epsilon_shared_consolidated",
    "epsilon_shared_append_cap14",
    "epsilon_shared_consolidated_mmr",
    "epsilon_shared_append_raw",
]
SENSITIVITY_ARMS = [
    "epsilon_sens_reference",
    "epsilon_sens_k3",
    "epsilon_sens_k10",
    "epsilon_sens_cap40",
    "epsilon_sens_ops3",
    "epsilon_sens_ops9",
    "epsilon_sens_merge07",
    "epsilon_sens_merge09",
    "epsilon_sens_recency1",
]
CONTROL_CONTRASTS = [
    ("shared_consolidated_minus_private_consolidated", "epsilon_shared_consolidated", "epsilon_private_consolidated"),
    ("append_cap14_minus_shared_consolidated", "epsilon_shared_append_cap14", "epsilon_shared_consolidated"),
    ("mmr_minus_shared_consolidated", "epsilon_shared_consolidated_mmr", "epsilon_shared_consolidated"),
    ("append_cap14_minus_frozen", "epsilon_shared_append_cap14", "epsilon_frozen_reviewer"),
    ("shared_consolidated_minus_frozen", "epsilon_shared_consolidated", "epsilon_frozen_reviewer"),
    ("append_raw_minus_frozen", "epsilon_shared_append_raw", "epsilon_frozen_reviewer"),
]
PRIMARY_METRICS = ["looped", "success", "success_excess_steps", "failure_penalized_steps", "stagnation_rate"]
EPSILON_PREREGISTRATION = "prereg_phase_epsilon.md + prereg_phase_epsilon_amendment1.md"
EPSILON_LEGACY_PREREGISTRATION = "prereg_phase_epsilon.md"
AMENDMENT_CONFIG_FIELDS = {"reviewer_temp", "append_dedup", "tie_rule"}
LEGACY_COMPATIBLE_CONTROL_ARMS = {
    "epsilon_frozen_reviewer",
    "epsilon_private_consolidated",
    "epsilon_shared_consolidated",
    "epsilon_shared_consolidated_mmr",
}

EPSILON_COMMON_CONFIG = {
    "model": "DeepSeek-V3",
    "base_url": "https://api.modelarts-maas.com/v2",
    "api_key_env": "MODELARTS_MAAS_KEY",
    "n_solvers": 4,
    "use_ground_truth": False,
    "batch_M": 4,
    "n_train": 24,
    "heldout_size": 12,
    "T": 6,
    "solver_temp": 0.7,
    "reviewer_temp": 0.2,
    "library_cap": 80,
    "retrieval_k": 6,
    "max_steps": 120,
    "maze_width": 15,
    "maze_height": 15,
    "maze_family": "trap",
    "maze_agent_mode": "state_guided",
    "maze_min_shortest": 30,
    "maze_max_shortest": 0,
    "maze_write_mode": "reviewer",
    "maze_eval_feedback": False,
    "skip_final_train": True,
    "retrieval_scoring": "ga",
    "ga_lambda": 0.0,
    "ga_recency": 0.0,
    "mmr_relevance_weight": 0.70,
    "max_reviewer_ops": 6,
    "similarity_threshold": 0.80,
    "append_dedup": True,
    "tie_rule": "oldest_evicted_recency_retaining",
    "memory_read_protocol": "standard",
    "cache_policy": "read_write",
    "max_tokens_solver": 256,
    "max_tokens_reviewer": 512,
}
EPSILON_ARM_CONFIG = {
    "epsilon_frozen_reviewer": {
        "memory_mode": "frozen",
        "memory_write_protocol": "expel_ops",
    },
    "epsilon_private_consolidated": {
        "memory_mode": "private",
        "memory_write_protocol": "expel_ops",
    },
    "epsilon_shared_consolidated": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
    },
    "epsilon_shared_append_cap14": {
        "memory_mode": "shared",
        "memory_write_protocol": "append",
        "library_cap": 14,
    },
    "epsilon_shared_consolidated_mmr": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "retrieval_scoring": "ga_mmr",
        "mmr_relevance_weight": 0.70,
    },
    "epsilon_shared_append_raw": {
        "memory_mode": "shared",
        "memory_write_protocol": "append",
        "append_dedup": False,
        "library_cap": 80,
    },
    "epsilon_sens_reference": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
    },
    "epsilon_sens_k3": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "retrieval_k": 3,
    },
    "epsilon_sens_k10": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "retrieval_k": 10,
    },
    "epsilon_sens_cap40": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "library_cap": 40,
    },
    "epsilon_sens_ops3": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "max_reviewer_ops": 3,
    },
    "epsilon_sens_ops9": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "max_reviewer_ops": 9,
    },
    "epsilon_sens_merge07": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "similarity_threshold": 0.70,
    },
    "epsilon_sens_merge09": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "similarity_threshold": 0.90,
    },
    "epsilon_sens_recency1": {
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
        "ga_recency": 1.0,
    },
}


def _config_mismatches(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    allow_missing: set[str] | None = None,
) -> list[dict[str, Any]]:
    allowed = allow_missing or set()
    return [
        {
            "field": field,
            "expected": expected_value,
            "actual": actual.get(field),
        }
        for field, expected_value in expected.items()
        if not (field in allowed and field not in actual)
        and actual.get(field) != expected_value
    ]


def _expected_epsilon_config(*, suite: str, arm: str, seed: int) -> dict[str, Any]:
    if suite not in {"controls", "sensitivity"}:
        raise ValueError(f"unknown Epsilon suite: {suite!r}")
    allowed = CONTROL_ARMS if suite == "controls" else SENSITIVITY_ARMS
    if arm not in allowed:
        return {"run_id": arm, "seed": seed, "__unexpected_arm__": True}
    expected = {
        **EPSILON_COMMON_CONFIG,
        "seed": seed,
        "run_id": arm,
        "notes": [],
        "out_dir": (
            "runs_maze_epsilon_controls"
            if suite == "controls"
            else "runs_maze_epsilon_sensitivity"
        ),
        "cache_dir": (
            "cache_maze_epsilon_controls"
            if suite == "controls"
            else "cache_maze_epsilon_sensitivity"
        ),
        **EPSILON_ARM_CONFIG[arm],
    }
    return expected


def _epsilon_manifest_check(
    *,
    result_path: Path | None,
    result_config: dict[str, Any],
    arm: str,
    seed: int,
) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    if result_path is None:
        return False, [{"field": "manifest_path", "expected": "manifest.json", "actual": None}], {}
    manifest_path = result_path.parent / "manifest.json"
    if not manifest_path.exists():
        return (
            False,
            [{"field": "manifest_path", "expected": str(manifest_path), "actual": "missing"}],
            {"path": str(manifest_path), "sha256": ""},
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected_condition = f"n4_gt_false_seed{seed}_{arm}"
    legacy_compatible = (
        arm in LEGACY_COMPATIBLE_CONTROL_ARMS
        and any(field not in result_config for field in AMENDMENT_CONFIG_FIELDS)
    )
    expected_preregistration = (
        EPSILON_LEGACY_PREREGISTRATION
        if legacy_compatible and manifest.get("preregistration") == EPSILON_LEGACY_PREREGISTRATION
        else EPSILON_PREREGISTRATION
    )
    allowed_missing = AMENDMENT_CONFIG_FIELDS if legacy_compatible else set()
    mismatches = _config_mismatches(
        manifest,
        {
            "condition": expected_condition,
            "run_id": arm,
            "seed": seed,
            "preregistration": expected_preregistration,
            "reviewer_temp": result_config.get("reviewer_temp"),
            "tie_rule": result_config.get("tie_rule"),
            "append_dedup": result_config.get("append_dedup"),
            "config": result_config,
        },
        allow_missing=allowed_missing,
    )
    return (
        not mismatches,
        mismatches,
        {"path": str(manifest_path), "sha256": _sha256(manifest_path)},
    )


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provenance_report() -> dict[str, Any]:
    prereg_freeze_path = Path("prereg_phase_epsilon.freeze.json")
    amendment_freeze_path = Path("prereg_phase_epsilon_amendment1.freeze.json")
    source_freeze_path = Path("epsilon_amendment1_runtime_source.freeze.json")
    prereg_freeze = json.loads(prereg_freeze_path.read_text(encoding="utf-8"))
    amendment_freeze = json.loads(amendment_freeze_path.read_text(encoding="utf-8"))
    source_freeze = json.loads(source_freeze_path.read_text(encoding="utf-8"))
    prereg_path = Path(prereg_freeze["document"])
    prereg_actual = _sha256(prereg_path)
    amendment_path = Path(amendment_freeze["path"])
    amendment_actual = _sha256(amendment_path)
    source_files = []
    for expected in source_freeze.get("files", []):
        path = Path(expected["path"])
        actual = _sha256(path)
        source_files.append(
            {
                "path": str(path),
                "expected_sha256": expected["sha256"],
                "actual_sha256": actual,
                "match": actual == expected["sha256"],
            }
        )
    return {
        "preregistration": {
            "document": str(prereg_path),
            "freeze_record": str(prereg_freeze_path),
            "expected_sha256": prereg_freeze["sha256"],
            "actual_sha256": prereg_actual,
            "match": prereg_actual == prereg_freeze["sha256"],
        },
        "amendment": {
            "document": str(amendment_path),
            "freeze_record": str(amendment_freeze_path),
            "expected_sha256": amendment_freeze["sha256"],
            "actual_sha256": amendment_actual,
            "match": amendment_actual == amendment_freeze["sha256"],
        },
        "runtime_source": {
            "freeze_record": str(source_freeze_path),
            "git_head": source_freeze.get("git_head", ""),
            "status": source_freeze.get("status", ""),
            "files": source_files,
            "all_match": bool(source_files) and all(row["match"] for row in source_files),
        },
    }


def _result_path(runs_dir: Path, arm: str, seed: int) -> Path:
    return runs_dir / f"n4_gt_false_seed{seed}_{arm}" / "result.json"


def _load_suite(
    *,
    runs_dir: Path,
    arms: list[str],
    seeds: list[int],
) -> tuple[
    dict[tuple[str, int], dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    results: dict[tuple[str, int], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    missing: list[str] = []
    for arm in arms:
        for seed in seeds:
            path = _result_path(runs_dir, arm, seed)
            if not path.exists():
                missing.append(str(path))
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            results[(arm, seed)] = result
            rows.extend(route_rows(result, condition=arm, seed=str(seed)))
            source_results.append(
                {
                    "condition": arm,
                    "seed": seed,
                    "path": str(path),
                    "sha256": _sha256(path),
                }
            )
    if missing:
        raise FileNotFoundError("Missing preregistered Epsilon results:\n" + "\n".join(missing))
    return results, rows, source_results


def _quality_rows(
    results: dict[tuple[str, int], dict[str, Any]],
    *,
    suite: str | None = None,
    result_paths: dict[tuple[str, int], Path] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (arm, seed), result in sorted(results.items()):
        summary = result.get("summary", {})
        llm = summary.get("llm", {})
        log = result.get("log", [])
        final = log[-1] if log else {}
        final_t = int(final.get("t", -1))
        expected_terminal_t = int(result.get("config", {}).get("T") or (final_t + 1)) - 1
        all_routes = route_rows(result, condition=arm, seed=str(seed))
        final_routes = [
            row
            for row in all_routes
            if int(row["t"]) == final_t
        ]
        route_llm_error_count_all = int(
            sum(float(route.get("llm_error_count") or 0.0) for route in all_routes)
        )
        route_llm_error_count_final = int(
            sum(float(route.get("llm_error_count") or 0.0) for route in final_routes)
        )
        parse_failure_count_all = int(
            sum(float(route.get("parse_failure_count") or 0.0) for route in all_routes)
        )
        parse_failure_count_final = int(
            sum(float(route.get("parse_failure_count") or 0.0) for route in final_routes)
        )
        route_llm_error_rounds = sorted(
            {
                int(route["t"])
                for route in all_routes
                if float(route.get("llm_error_count") or 0.0) > 0.0
            }
        )
        parse_failure_rounds = sorted(
            {
                int(route["t"])
                for route in all_routes
                if float(route.get("parse_failure_count") or 0.0) > 0.0
            }
        )
        audit = result.get("memory_audit", {})
        exhausted_calls = (
            list(audit.get("llm_errors", []))
            if isinstance(audit, dict)
            else []
        )
        exhausted_contexts: dict[str, int] = {}
        for event in exhausted_calls:
            tag = str(event.get("tag", "")).lower()
            task_id = str(event.get("task_id", "")).lower()
            if "reviewer" in tag:
                context = "reviewer"
            elif task_id.startswith("heldout"):
                context = "heldout_solver"
            elif task_id.startswith("train"):
                context = "train_solver"
            else:
                context = "other"
            exhausted_contexts[context] = exhausted_contexts.get(context, 0) + 1
        config = result.get("config", {})
        expected_routes = int(config.get("heldout_size") or 0) * int(config.get("n_solvers") or 0)
        if expected_routes <= 0:
            expected_routes = int(final.get("n_routes") or len(final_routes))
        config_mismatches: list[dict[str, Any]] = []
        manifest_mismatches: list[dict[str, Any]] = []
        manifest_source: dict[str, Any] = {}
        if suite is not None:
            config_mismatches = _config_mismatches(
                config,
                _expected_epsilon_config(suite=suite, arm=arm, seed=seed),
                allow_missing=(
                    AMENDMENT_CONFIG_FIELDS
                    if suite == "controls"
                    and arm in LEGACY_COMPATIBLE_CONTROL_ARMS
                    and any(field not in config for field in AMENDMENT_CONFIG_FIELDS)
                    else set()
                ),
            )
            manifest_pass, manifest_mismatches, manifest_source = _epsilon_manifest_check(
                result_path=(result_paths or {}).get((arm, seed)),
                result_config=config,
                arm=arm,
                seed=seed,
            )
        else:
            manifest_pass = True
        rows.append(
            {
                "condition": arm,
                "seed": seed,
                "network_calls": int(llm.get("network_calls", 0)),
                "cache_hits": int(llm.get("cache_hits", 0)),
                "llm_error_count": int(llm.get("errors", 0)),
                "llm_retry_count": int(llm.get("retry_count", 0)),
                "content_filter_hits": int(llm.get("content_filter_hits", 0)),
                "exhausted_llm_call_count": len(exhausted_calls),
                "exhausted_llm_call_rounds": sorted(
                    {
                        int(event.get("t", -1))
                        for event in exhausted_calls
                        if int(event.get("t", -1)) >= 0
                    }
                ),
                "exhausted_llm_call_contexts": exhausted_contexts,
                "route_llm_error_count_all_rounds": route_llm_error_count_all,
                "route_llm_error_count_final": route_llm_error_count_final,
                "route_llm_error_count_nonterminal": max(
                    route_llm_error_count_all - route_llm_error_count_final,
                    0,
                ),
                "route_llm_error_affected_routes_all_rounds": sum(
                    float(route.get("llm_error_count") or 0.0) > 0.0
                    for route in all_routes
                ),
                "route_llm_error_rounds": route_llm_error_rounds,
                "parse_failure_rate_final": float(
                    summary.get("parse_failure_rate_final", final.get("parse_failure_rate", 0.0))
                ),
                "parse_failure_count_all_rounds": parse_failure_count_all,
                "parse_failure_count_final": parse_failure_count_final,
                "parse_failure_count_nonterminal": max(
                    parse_failure_count_all - parse_failure_count_final,
                    0,
                ),
                "parse_failure_rounds": parse_failure_rounds,
                "terminal_t": final_t,
                "expected_terminal_t": expected_terminal_t,
                "terminal_round_pass": final_t == expected_terminal_t,
                "route_count_final": len(final_routes),
                "expected_route_count_final": expected_routes,
                "route_count_pass": len(final_routes) == expected_routes,
                "configuration_pass": not config_mismatches,
                "configuration_mismatches": config_mismatches,
                "manifest_pass": manifest_pass,
                "manifest_mismatches": manifest_mismatches,
                "manifest_path": manifest_source.get("path", ""),
                "manifest_sha256": manifest_source.get("sha256", ""),
                "elapsed_sec": float(summary.get("elapsed_sec", 0.0)),
            }
        )
    return rows


def _memory_rows(results: dict[tuple[str, int], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (arm, seed), result in sorted(results.items()):
        log = result.get("log", [])
        final = log[-1] if log else {}
        audit = result.get("memory_audit", {})
        trajectory = audit.get("pool_trajectory", []) if isinstance(audit, dict) else []
        final_pool = trajectory[-1] if trajectory else {}
        distinct_injected_ids = {
            str(item_id)
            for retrieval in (audit.get("retrievals", []) if isinstance(audit, dict) else [])
            for item_id in retrieval.get("items", [])
        }
        if distinct_injected_ids:
            distinct_injected = len(distinct_injected_ids)
        else:
            distinct_injected = int(final_pool.get("distinct_total_injected", 0))
        rows.append(
            {
                "condition": arm,
                "seed": seed,
                "final_memory_size": int(final.get("memory_size", 0)),
                "distinct_injected_strategy_count": distinct_injected,
                "final_distinct_total_injected": int(final_pool.get("distinct_total_injected", 0)),
                "final_distinct_active_injected": int(final_pool.get("distinct_active_injected", 0)),
                "final_mean_injected_per_prompt": float(final_pool.get("mean_injected_per_prompt", 0.0)),
                "retrieval_entropy_norm_final": float(final.get("retrieval_entropy_norm", 0.0)),
                "retrieval_top1_share_final": float(final.get("retrieval_top1_share", 0.0)),
                "retrieval_concentration_final": float(final.get("retrieval_concentration", 0.0)),
            }
        )
    return rows


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    position = q * (len(sorted_values) - 1)
    lo = int(position)
    hi = min(lo + 1, len(sorted_values) - 1)
    weight = position - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def _compression_manipulation_check(
    memory_rows: list[dict[str, Any]],
    *,
    n_boot: int,
    rng_seed: int,
) -> dict[str, Any]:
    cap14 = {
        int(row["seed"]): row
        for row in memory_rows
        if row["condition"] == "epsilon_shared_append_cap14"
    }
    raw = {
        int(row["seed"]): row
        for row in memory_rows
        if row["condition"] == "epsilon_shared_append_raw"
    }
    seeds = sorted(set(cap14) & set(raw))
    per_seed = [
        {
            "seed": seed,
            "cap14": int(cap14[seed]["distinct_injected_strategy_count"]),
            "raw": int(raw[seed]["distinct_injected_strategy_count"]),
            "difference_cap14_minus_raw": (
                int(cap14[seed]["distinct_injected_strategy_count"])
                - int(raw[seed]["distinct_injected_strategy_count"])
            ),
        }
        for seed in seeds
    ]
    differences = [float(row["difference_cap14_minus_raw"]) for row in per_seed]
    if len(differences) != 5:
        raise ValueError(
            "Epsilon manipulation check requires five paired cap14/raw seed scalars; "
            f"found {len(differences)}"
        )
    rng = random.Random(rng_seed)
    boot = sorted(
        sum(rng.choice(differences) for _ in differences) / len(differences)
        for _ in range(n_boot)
    )
    ci_lo = _percentile(boot, 0.025)
    ci_hi = _percentile(boot, 0.975)
    terminal_pool_by_seed = {
        seed: int(cap14[seed]["final_memory_size"])
        for seed in seeds
    }
    pool_pass = all(size <= 20 for size in terminal_pool_by_seed.values())
    compression_pass = ci_hi < 0.0
    return {
        "comparison": "epsilon_shared_append_cap14_minus_epsilon_shared_append_raw",
        "analysis_unit": "one distinct-injected scalar per arm per seed",
        "analysis_method": "seed_level_paired_bootstrap",
        "n_boot": n_boot,
        "rng_seed": rng_seed,
        "seeds": seeds,
        "per_seed": per_seed,
        "mean_difference_cap14_minus_raw": sum(differences) / len(differences),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "terminal_pool_size_by_seed": terminal_pool_by_seed,
        "terminal_pool_le_20_every_seed": pool_pass,
        "compression_interval_excludes_zero": compression_pass,
        "passed": pool_pass and compression_pass,
    }


def _contrasts_for_suite(suite: str) -> list[tuple[str, str, str]]:
    if suite == "controls":
        return CONTROL_CONTRASTS
    return [
        (f"{arm}_minus_epsilon_sens_reference", arm, "epsilon_sens_reference")
        for arm in SENSITIVITY_ARMS
        if arm != "epsilon_sens_reference"
    ]


def _write_report(
    *,
    path: Path,
    suite: str,
    final_t: int,
    stats_rows: list[dict[str, Any]],
    effect_rows: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
    provenance: dict[str, Any],
    manipulation_check: dict[str, Any] | None = None,
) -> None:
    lines = [
        f"# Phase Epsilon {suite.title()} Evidence",
        "",
        "Behavioral differences use the prespecified seed-clustered paired bootstrap: route pairs "
        "are matched by seed, round, heldout maze, and agent; seeds are resampled as the outer unit.",
        f"Terminal round: `t={final_t}`.",
        "",
    ]
    if manipulation_check is not None:
        lines.extend(
            [
                "## Compression Manipulation Check",
                "",
                "- unit: one cumulative distinct-injected scalar per arm per seed",
                f"- paired seeds: `{','.join(str(seed) for seed in manipulation_check['seeds'])}`",
                f"- mean cap14 minus raw: `{manipulation_check['mean_difference_cap14_minus_raw']:.4f}`",
                f"- seed-bootstrap 95% CI: "
                f"`[{manipulation_check['ci_lo']:.4f}, {manipulation_check['ci_hi']:.4f}]`",
                f"- cap14 terminal pool <=20 in every seed: "
                f"`{'yes' if manipulation_check['terminal_pool_le_20_every_seed'] else 'no'}`",
                f"- manipulation passed: `{'yes' if manipulation_check['passed'] else 'no'}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Primary Endpoints",
            "",
            "| contrast (A - B) | metric | mean diff | 95% CI | paired routes | seeds |",
            "|---|---|---:|---|---:|---:|",
        ]
    )
    for row in stats_rows:
        if row["metric"] not in PRIMARY_METRICS:
            continue
        lines.append(
            f"| {row['contrast']} | {row['metric']} | {row['mean_diff']:.4f} | "
            f"[{row['ci_lo']:.4f}, {row['ci_hi']:.4f}] | {row['n_pairs']} | {row['n_seeds']} |"
        )
    lines.extend(
        [
            "",
            "## Per-Seed Primary Effects",
            "",
            "| contrast (A - B) | metric | seed | mean diff | paired routes |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in effect_rows:
        if row["metric"] not in PRIMARY_METRICS:
            continue
        lines.append(
            f"| {row['contrast']} | {row['metric']} | {row['seed']} | "
            f"{row['mean_diff']:.4f} | {row['n_pairs']} |"
        )
    lines.extend(
        [
            "",
            "## Data Quality",
            "",
            "| condition | seed | network calls | cache hits | API errors | retries | filter hits | exhausted calls | exhausted contexts | route LLM errors all/final | affected routes | error rounds | parse failures all/final | parse rounds | final parse rate | terminal t | expected t | terminal complete | final routes | expected | routes complete | config | manifest |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---:|---|---:|---:|---:|---|---:|---:|---|---|---|",
        ]
    )
    for row in quality_rows:
        lines.append(
            f"| {row['condition']} | {row['seed']} | {row['network_calls']} | {row['cache_hits']} | "
            f"{row['llm_error_count']} | {row['llm_retry_count']} | {row['content_filter_hits']} | "
            f"{row['exhausted_llm_call_count']} | "
            f"{json.dumps(row['exhausted_llm_call_contexts'], sort_keys=True)} | "
            f"{row['route_llm_error_count_all_rounds']}/{row['route_llm_error_count_final']} | "
            f"{row['route_llm_error_affected_routes_all_rounds']} | "
            f"{','.join(str(value) for value in row['route_llm_error_rounds']) or '--'} | "
            f"{row['parse_failure_count_all_rounds']}/{row['parse_failure_count_final']} | "
            f"{','.join(str(value) for value in row['parse_failure_rounds']) or '--'} | "
            f"{row['parse_failure_rate_final']:.4f} | {row['terminal_t']} | "
            f"{row['expected_terminal_t']} | {'yes' if row['terminal_round_pass'] else 'no'} | "
            f"{row['route_count_final']} | {row['expected_route_count_final']} | "
            f"{'yes' if row['route_count_pass'] else 'no'} | "
            f"{'yes' if row['configuration_pass'] else 'no'} | "
            f"{'yes' if row['manifest_pass'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- preregistration SHA-256 match: "
            f"{'yes' if provenance['preregistration']['match'] else 'no'}",
            f"- Amendment 01 SHA-256 match: "
            f"{'yes' if provenance['amendment']['match'] else 'no'}",
            f"- frozen runtime source hashes all match: "
            f"{'yes' if provenance['runtime_source']['all_match'] else 'no'}",
            f"- runtime Git HEAD: `{provenance['runtime_source']['git_head']}`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_epsilon_evidence(
    *,
    suite: str,
    runs_dir: Path,
    out_dir: Path,
    seeds: list[int],
    n_boot: int = 10_000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    if suite not in {"controls", "sensitivity"}:
        raise ValueError(f"unknown suite: {suite!r}")
    arms = CONTROL_ARMS if suite == "controls" else SENSITIVITY_ARMS
    results, rows, source_results = _load_suite(runs_dir=runs_dir, arms=arms, seeds=seeds)
    final_t = max(int(row["t"]) for row in rows)
    stats_rows: list[dict[str, Any]] = []
    effect_rows: list[dict[str, Any]] = []
    for contrast, intervention, baseline in _contrasts_for_suite(suite):
        a = [row for row in rows if row["condition"] == intervention]
        b = [row for row in rows if row["condition"] == baseline]
        for metric in PAIRED_METRICS:
            stat = hierarchical_paired_diff(a, b, metric, t=final_t, n_boot=n_boot, rng_seed=rng_seed)
            stats_rows.append(
                {
                    "contrast": contrast,
                    "intervention": intervention,
                    "baseline": baseline,
                    "t": final_t,
                    "analysis_method": "seed_clustered_paired_bootstrap",
                    **stat,
                }
            )
        for effect in per_seed_paired_effects(a, b, t=final_t):
            effect_rows.append(
                {
                    "contrast": contrast,
                    "intervention": intervention,
                    "baseline": baseline,
                    **effect,
                }
            )

    result_paths = {
        (str(row["condition"]), int(row["seed"])): Path(str(row["path"]))
        for row in source_results
    }
    quality = _quality_rows(results, suite=suite, result_paths=result_paths)
    source_manifests = [
        {
            "condition": row["condition"],
            "seed": row["seed"],
            "path": row["manifest_path"],
            "sha256": row["manifest_sha256"],
        }
        for row in quality
    ]
    memory = _memory_rows(results)
    manipulation_check = (
        _compression_manipulation_check(memory, n_boot=n_boot, rng_seed=rng_seed)
        if suite == "controls"
        else None
    )
    provenance = _provenance_report()
    report = {
        "suite": suite,
        "runs_dir": str(runs_dir),
        "out_dir": str(out_dir),
        "seeds": seeds,
        "final_t": final_t,
        "contrasts": _contrasts_for_suite(suite),
        "analysis_method": "seed_clustered_paired_bootstrap",
        "n_boot": n_boot,
        "rng_seed": rng_seed,
        "stats": stats_rows,
        "per_seed_effects": effect_rows,
        "data_quality": quality,
        "memory_summary": memory,
        "manipulation_check": manipulation_check,
        "provenance": provenance,
        "source_results": source_results,
        "source_manifests": source_manifests,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(stats_rows, out_dir / "hierarchical_paired_stats.csv")
    _write_csv(effect_rows, out_dir / "per_seed_paired_effects.csv")
    _write_csv(quality, out_dir / "data_quality.csv")
    _write_csv(memory, out_dir / "memory_summary.csv")
    if manipulation_check is not None:
        _write_csv(
            list(manipulation_check["per_seed"]),
            out_dir / "manipulation_check_seed_differences.csv",
        )
    (out_dir / "evidence_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(
        path=out_dir / "evidence_report.md",
        suite=suite,
        final_t=final_t,
        stats_rows=stats_rows,
        effect_rows=effect_rows,
        quality_rows=quality,
        provenance=provenance,
        manipulation_check=manipulation_check,
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize frozen Phase Epsilon maze results.")
    parser.add_argument("--suite", choices=["controls", "sensitivity"], required=True)
    parser.add_argument("--runs-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seeds", default="", help="Comma-separated seeds; defaults follow preregistration.")
    parser.add_argument("--n-boot", type=int, default=10_000)
    parser.add_argument("--rng-seed", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    default = [0, 1, 2, 3, 4] if args.suite == "controls" else [0, 1, 2]
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()] if args.seeds else default
    report = build_epsilon_evidence(
        suite=args.suite,
        runs_dir=Path(args.runs_dir),
        out_dir=Path(args.out_dir),
        seeds=seeds,
        n_boot=args.n_boot,
        rng_seed=args.rng_seed,
    )
    print(f"wrote {Path(args.out_dir).resolve()}")
    return report


if __name__ == "__main__":
    main()
