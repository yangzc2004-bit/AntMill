from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


# Route-level metrics available for paired comparisons. success_excess_steps is
# None on failed routes, so failure penalties never masquerade as slowness.
PAIRED_METRICS = [
    "success",
    "cost_ratio",
    "failure_penalized_steps",
    "excess_steps",
    "success_excess_steps",
    "looped",
    "stagnation_rate",
    "revisit_max",
]

DEFAULT_RUNS = {
    "frozen:0": "runs_maze_alpha_mas_frozen_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_frozen_reviewer/result.json",
    "frozen:1": "runs_maze_alpha_mas_frozen_h3_t3_seed1_v1_v3_c4/n4_gt_false_seed1_maze_mad_frozen_reviewer/result.json",
    "frozen:2": "runs_maze_alpha_mas_frozen_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_frozen_reviewer/result.json",
    "private_fixed:0": "runs_maze_alpha_mas_private_fixed_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_private_reviewer/result.json",
    "private_fixed:1": "runs_maze_alpha_mas_private_fixed_h3_t3_seed1_v1_v3_c4/n4_gt_false_seed1_maze_mad_private_reviewer/result.json",
    "private_fixed:2": "runs_maze_alpha_mas_private_fixed_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_private_reviewer/result.json",
    "shared_reviewer:0": "runs_maze_alpha_mas_shared_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_reviewer/result.json",
    "shared_reviewer:1": "runs_maze_alpha_mas_shared_h3_t3_seed1_v1_v3_c4/n4_gt_false_seed1_maze_mad_shared_reviewer/result.json",
    "shared_reviewer:2": "runs_maze_alpha_mas_shared_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_shared_reviewer/result.json",
    "shared_direct:0": "runs_maze_alpha_mas_shared_direct_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_direct/result.json",
    "shared_direct:1": "runs_maze_alpha_mas_shared_direct_h3_t3_seed1_v1_v3_c4/n4_gt_false_seed1_maze_mad_shared_direct/result.json",
    "shared_direct:2": "runs_maze_alpha_mas_shared_direct_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_shared_direct/result.json",
    "shared_oracle:0": "runs_maze_alpha_mas_shared_oracle_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_oracle/result.json",
    "shared_oracle:1": "runs_maze_alpha_mas_shared_oracle_h3_t3_seed1_v1_v3_c4/n4_gt_false_seed1_maze_mad_shared_oracle/result.json",
    "shared_oracle:2": "runs_maze_alpha_mas_shared_oracle_h3_t3_seed2_v1_v3_c4/n4_gt_false_seed2_maze_mad_shared_oracle/result.json",
}


def route_rows(result: dict[str, Any], *, condition: str, seed: str) -> list[dict[str, Any]]:
    """Flatten heldout_records into per-route rows.

    Works retroactively on pre-P0 result files: everything here is computed from
    the recorded routes, not from the aggregated log[].
    """
    rows: list[dict[str, Any]] = []
    for record in result.get("heldout_records", []):
        t = int(record.get("t", 0))
        for ep in record.get("episodes", []):
            task_id = str(ep.get("task_id") or (ep.get("task") or {}).get("task_id") or "")
            for agent in ep.get("agents", []):
                route = agent.get("route") or {}
                success = bool(route.get("success"))
                excess = float(route.get("excess_steps") or 0.0)
                rows.append(
                    {
                        "condition": condition,
                        "seed": str(seed),
                        "t": t,
                        "task_id": task_id,
                        "agent_id": int(agent.get("agent_id", 0)),
                        "success": 1.0 if success else 0.0,
                        "steps": float(route.get("steps") or 0.0),
                        "shortest_path_length": float(route.get("shortest_path_length") or 0.0),
                        "cost_ratio": float(route.get("cost_ratio") or 0.0),
                        "failure_penalized_steps": float(route.get("failure_penalized_steps") or route.get("effective_steps") or 0.0),
                        "excess_steps": excess,
                        "success_excess_steps": excess if success else None,
                        "looped": 1.0 if route.get("looped") else 0.0,
                        "stagnation_rate": float(route.get("stagnation_rate") or 0.0),
                        "revisit_max": float(route.get("revisit_max") or 0.0),
                        "parse_failure_count": float(route.get("parse_failure_count") or 0.0),
                        "llm_error_count": float(route.get("llm_error_count") or 0.0),
                    }
                )
    return rows


def bootstrap_ci(diffs: list[float], *, n_boot: int = 10000, rng_seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean; same resampling core as analysis_stats.paired_bootstrap."""
    arr = np.asarray(diffs, dtype=float)
    rng = np.random.default_rng(rng_seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    boot = arr[idx].mean(axis=1)
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def paired_diff(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    metric: str,
    *,
    t: int | None = None,
    n_boot: int = 10000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    """Paired mean difference (A - B) on routes aligned by (seed, t, task_id, agent_id).

    Pairing on the same heldout maze/agent removes between-maze variance from the
    comparison. Unpaired routes and pairs with a missing metric are dropped and
    counted in n_dropped.
    """

    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, int, str, int], dict[str, Any]]:
        out: dict[tuple[str, int, str, int], dict[str, Any]] = {}
        for row in rows:
            if t is not None and int(row["t"]) != t:
                continue
            out[(str(row["seed"]), int(row["t"]), str(row["task_id"]), int(row["agent_id"]))] = row
        return out

    ia = index(rows_a)
    ib = index(rows_b)
    keys = sorted(set(ia) & set(ib))
    n_unpaired = (len(ia) - len(keys)) + (len(ib) - len(keys))
    diffs: list[float] = []
    n_missing = 0
    for key in keys:
        va = ia[key].get(metric)
        vb = ib[key].get(metric)
        if va is None or vb is None:
            n_missing += 1
            continue
        diffs.append(float(va) - float(vb))
    if not diffs:
        return {
            "metric": metric,
            "n_pairs": 0,
            "mean_diff": 0.0,
            "ci_lo": 0.0,
            "ci_hi": 0.0,
            "n_dropped": n_unpaired + n_missing,
            "ci_excludes_zero": False,
        }
    ci_lo, ci_hi = bootstrap_ci(diffs, n_boot=n_boot, rng_seed=rng_seed)
    return {
        "metric": metric,
        "n_pairs": len(diffs),
        "mean_diff": float(np.mean(diffs)),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_dropped": n_unpaired + n_missing,
        "ci_excludes_zero": bool(ci_lo > 0.0 or ci_hi < 0.0),
    }


def _paired_diffs_by_seed(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    metric: str,
    *,
    t: int | None = None,
) -> tuple[dict[str, list[float]], int]:
    """Return aligned route-level differences grouped by seed.

    The route key matches ``paired_diff``. Keeping the seed grouping lets the
    analysis treat independent run seeds as the outer resampling unit instead
    of treating every route as independent evidence.
    """

    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, int, str, int], dict[str, Any]]:
        out: dict[tuple[str, int, str, int], dict[str, Any]] = {}
        for row in rows:
            if t is not None and int(row["t"]) != t:
                continue
            out[(str(row["seed"]), int(row["t"]), str(row["task_id"]), int(row["agent_id"]))] = row
        return out

    ia = index(rows_a)
    ib = index(rows_b)
    keys = sorted(set(ia) & set(ib))
    n_dropped = (len(ia) - len(keys)) + (len(ib) - len(keys))
    grouped: dict[str, list[float]] = defaultdict(list)
    for key in keys:
        va = ia[key].get(metric)
        vb = ib[key].get(metric)
        if va is None or vb is None:
            n_dropped += 1
            continue
        grouped[key[0]].append(float(va) - float(vb))
    return grouped, n_dropped


def hierarchical_bootstrap_ci(
    diffs_by_seed: dict[str, list[float]],
    *,
    n_boot: int = 10000,
    rng_seed: int = 0,
) -> tuple[float, float]:
    """Clustered percentile CI for the equal-weight mean seed effect.

    Each bootstrap draw samples run seeds with replacement, then samples paired
    routes within every selected seed. This reflects the nested seed/route
    design while retaining within-seed maze matching.
    """
    seed_values = [np.asarray(values, dtype=float) for _seed, values in sorted(diffs_by_seed.items()) if values]
    if not seed_values:
        return 0.0, 0.0
    rng = np.random.default_rng(rng_seed)
    boot = np.empty(n_boot, dtype=float)
    n_seeds = len(seed_values)
    for i in range(n_boot):
        selected = rng.integers(0, n_seeds, size=n_seeds)
        seed_means: list[float] = []
        for index in selected:
            values = seed_values[int(index)]
            sampled = values[rng.integers(0, len(values), size=len(values))]
            seed_means.append(float(sampled.mean()))
        boot[i] = float(np.mean(seed_means))
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def hierarchical_paired_diff(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    metric: str,
    *,
    t: int | None = None,
    n_boot: int = 10000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    """Seed-clustered paired difference (A - B).

    The point estimate is the mean of seed-level paired route means so seeds
    with more valid route records cannot dominate the effect estimate.
    """
    diffs_by_seed, n_dropped = _paired_diffs_by_seed(rows_a, rows_b, metric, t=t)
    n_pairs = sum(len(values) for values in diffs_by_seed.values())
    if not n_pairs:
        return {
            "metric": metric,
            "n_pairs": 0,
            "n_seeds": 0,
            "mean_diff": 0.0,
            "ci_lo": 0.0,
            "ci_hi": 0.0,
            "n_dropped": n_dropped,
            "ci_excludes_zero": False,
        }
    mean_diff = float(np.mean([float(np.mean(values)) for values in diffs_by_seed.values() if values]))
    ci_lo, ci_hi = hierarchical_bootstrap_ci(diffs_by_seed, n_boot=n_boot, rng_seed=rng_seed)
    return {
        "metric": metric,
        "n_pairs": n_pairs,
        "n_seeds": len(diffs_by_seed),
        "mean_diff": mean_diff,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_dropped": n_dropped,
        "ci_excludes_zero": bool(ci_lo > 0.0 or ci_hi < 0.0),
    }


def per_seed_paired_effects(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    metrics: list[str] | None = None,
    *,
    t: int | None = None,
) -> list[dict[str, Any]]:
    """Compact paired-effect table for inspecting between-seed heterogeneity."""
    effects: list[dict[str, Any]] = []
    for metric in metrics or PAIRED_METRICS:
        diffs_by_seed, _n_dropped = _paired_diffs_by_seed(rows_a, rows_b, metric, t=t)
        for seed, values in sorted(diffs_by_seed.items()):
            effects.append(
                {
                    "metric": metric,
                    "seed": seed,
                    "t": t,
                    "n_pairs": len(values),
                    "mean_diff": float(np.mean(values)),
                }
            )
    return effects


def per_seed_table(rows: list[dict[str, Any]], metrics: list[str] | None = None) -> list[dict[str, Any]]:
    """Per-(condition, seed, t) means. Always ship this next to any mean: a claim
    driven by a single seed must be visible as such."""
    metrics = metrics or PAIRED_METRICS
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["condition"]), str(row["seed"]), int(row["t"]))].append(row)
    out: list[dict[str, Any]] = []
    for (condition, seed, t), group in sorted(grouped.items()):
        item: dict[str, Any] = {"condition": condition, "seed": seed, "t": t, "n_routes": len(group)}
        for metric in metrics:
            vals = [float(row[metric]) for row in group if row.get(metric) is not None]
            item[metric] = float(np.mean(vals)) if vals else None
        out.append(item)
    return out


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _parse_label(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        return raw.strip(), "0"
    condition, seed = raw.split(":", 1)
    return condition.strip(), seed.strip()


def _load_rows(specs: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for label, path in specs.items():
        condition, seed = _parse_label(label)
        p = Path(path)
        if not p.exists():
            missing.append(f"{label}: {p}")
            continue
        result = json.loads(p.read_text(encoding="utf-8"))
        rows.extend(route_rows(result, condition=condition, seed=seed))
    if missing:
        raise FileNotFoundError("Missing result files:\n" + "\n".join(missing))
    return rows


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _write_report(
    path: Path,
    *,
    baseline: str,
    t: int,
    paired_rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    seed_effect_rows: list[dict[str, Any]],
    analysis_method: str,
) -> None:
    lines = [
        "# Maze Paired Statistics",
        "",
        f"`{analysis_method}` analysis of routes aligned by seed/task/agent on the same heldout "
        f"mazes, baseline `{baseline}`, round `t={t}`. `ci_excludes_zero = yes` marks "
        "differences whose 95% CI does not contain 0.",
        "",
        "## Condition vs Baseline",
        "",
    ]
    if analysis_method == "seed-clustered paired bootstrap":
        lines.extend(
            [
                "| condition | metric | mean diff | ci lo | ci hi | n pairs | n seeds | n dropped | ci excludes zero |",
                "|---|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
    else:
        lines.extend(
            [
                "| condition | metric | mean diff | ci lo | ci hi | n pairs | n dropped | ci excludes zero |",
                "|---|---|---:|---:|---:|---:|---:|---|",
            ]
        )
    for row in paired_rows:
        if analysis_method == "seed-clustered paired bootstrap":
            lines.append(
                f"| {row['condition']} | {row['metric']} | {_fmt(row['mean_diff'])} | "
                f"{_fmt(row['ci_lo'])} | {_fmt(row['ci_hi'])} | {row['n_pairs']} | {row['n_seeds']} | "
                f"{row['n_dropped']} | {'yes' if row['ci_excludes_zero'] else 'no'} |"
            )
        else:
            lines.append(
                f"| {row['condition']} | {row['metric']} | {_fmt(row['mean_diff'])} | "
                f"{_fmt(row['ci_lo'])} | {_fmt(row['ci_hi'])} | {row['n_pairs']} | {row['n_dropped']} | "
                f"{'yes' if row['ci_excludes_zero'] else 'no'} |"
            )
    lines += [
        "",
        "## Per-Seed Paired Effects",
        "",
        "| condition | metric | seed | t | n paired routes | mean diff |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in seed_effect_rows:
        lines.append(
            f"| {row['condition']} | {row['metric']} | {row['seed']} | {row['t']} | "
            f"{row['n_pairs']} | {_fmt(row['mean_diff'])} |"
        )
    lines += [
        "",
        "## Per-Seed Means (never read the paired table without this one)",
        "",
        "| condition | seed | t | n routes | success | cost | success-only excess | looped |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in seed_rows:
        lines.append(
            f"| {row['condition']} | {row['seed']} | {row['t']} | {row['n_routes']} | "
            f"{_fmt(row.get('success'))} | {_fmt(row.get('cost_ratio'))} | "
            f"{_fmt(row.get('success_excess_steps'))} | {_fmt(row.get('looped'))} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Paired route-level statistics for Maze Alpha runs.")
    parser.add_argument("--out-dir", default="./runs_maze_alpha_paired_stats")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="condition[:seed]=path/to/result.json. Defaults to the h3/t3 3-seed matrix.",
    )
    parser.add_argument("--baseline", default="frozen", help="Baseline condition for paired diffs.")
    parser.add_argument("--t", type=int, default=-1, help="Round to compare (-1 = final common round).")
    parser.add_argument("--n-boot", type=int, default=10000)
    parser.add_argument("--rng-seed", type=int, default=0)
    parser.add_argument(
        "--bootstrap-unit",
        choices=["route", "seed_cluster"],
        default="route",
        help="Legacy route bootstrap or seed-clustered paired bootstrap.",
    )
    return parser


def main(argv: list[str] | None = None) -> Path:
    args = _parser().parse_args(argv)
    specs = dict(DEFAULT_RUNS) if not args.run else {}
    for item in args.run:
        if "=" not in item:
            raise ValueError(f"--run must be label=path, got {item!r}")
        label, path = item.split("=", 1)
        specs[label.strip()] = path.strip()

    rows = _load_rows(specs)
    conditions = sorted({str(row["condition"]) for row in rows})
    if args.baseline not in conditions:
        raise ValueError(f"baseline {args.baseline!r} not among conditions {conditions}")
    t = args.t if args.t >= 0 else max(int(row["t"]) for row in rows)

    baseline_rows = [row for row in rows if row["condition"] == args.baseline]
    paired: list[dict[str, Any]] = []
    seed_effect_rows: list[dict[str, Any]] = []
    use_seed_clusters = args.bootstrap_unit == "seed_cluster"
    for condition in conditions:
        if condition == args.baseline:
            continue
        cond_rows = [row for row in rows if row["condition"] == condition]
        for metric in PAIRED_METRICS:
            stat = (
                hierarchical_paired_diff(
                    cond_rows, baseline_rows, metric, t=t, n_boot=args.n_boot, rng_seed=args.rng_seed
                )
                if use_seed_clusters
                else paired_diff(
                    cond_rows, baseline_rows, metric, t=t, n_boot=args.n_boot, rng_seed=args.rng_seed
                )
            )
            paired.append(
                {
                    "condition": condition,
                    "baseline": args.baseline,
                    "t": t,
                    "analysis_method": "seed_cluster" if use_seed_clusters else "route",
                    **stat,
                }
            )
        for effect in per_seed_paired_effects(cond_rows, baseline_rows, t=t):
            seed_effect_rows.append({"condition": condition, "baseline": args.baseline, **effect})

    seed_rows = per_seed_table(rows)
    out_dir = Path(args.out_dir)
    _write_csv(paired, out_dir / "paired_stats.csv")
    _write_csv(seed_rows, out_dir / "per_seed.csv")
    _write_csv(seed_effect_rows, out_dir / "per_seed_paired_effects.csv")
    _write_report(
        out_dir / "stats_report.md",
        baseline=args.baseline,
        t=t,
        paired_rows=paired,
        seed_rows=seed_rows,
        seed_effect_rows=seed_effect_rows,
        analysis_method="seed-clustered paired bootstrap" if use_seed_clusters else "route-level paired bootstrap",
    )
    print(f"wrote {out_dir.resolve()}")
    return out_dir


if __name__ == "__main__":
    main()
