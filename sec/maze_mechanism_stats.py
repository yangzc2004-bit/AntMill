from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


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

CONDITION_ORDER = ["frozen", "private_fixed", "shared_reviewer", "shared_direct", "shared_oracle"]
CONDITION_COLORS = {
    "frozen": "#8a8f98",
    "private_fixed": "#4c78a8",
    "shared_reviewer": "#54a24b",
    "shared_direct": "#e45756",
    "shared_oracle": "#b279a2",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build mechanism-level statistics for Maze Alpha runs.")
    parser.add_argument("--out-dir", default="./runs_maze_alpha_mechanism_stats_h3_t3_seed0_seed1_seed2")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="Optional condition[:seed]=path/to/result.json. Defaults to the n=3 full matrix.",
    )
    return parser


def _parse_label(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        return raw.strip(), "0"
    condition, seed = raw.split(":", 1)
    return condition.strip(), seed.strip()


def _load_runs(args: argparse.Namespace) -> dict[tuple[str, str], dict[str, Any]]:
    specs = {} if args.run else dict(DEFAULT_RUNS)
    for item in args.run:
        if "=" not in item:
            raise ValueError(f"--run must be label=path, got {item!r}")
        label, path = item.split("=", 1)
        specs[label.strip()] = path.strip()

    runs: dict[tuple[str, str], dict[str, Any]] = {}
    missing: list[str] = []
    for label, path in specs.items():
        condition, seed = _parse_label(label)
        p = Path(path)
        if not p.exists():
            missing.append(f"{label}: {p}")
            continue
        runs[(condition, seed)] = json.loads(p.read_text(encoding="utf-8"))
    if missing:
        raise FileNotFoundError("Missing result files:\n" + "\n".join(missing))
    return runs


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(ys) < 2 or len(xs) != len(ys):
        return 0.0
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    return num / (x_den * y_den) if x_den and y_den else 0.0


def _round_rows(runs: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (condition, seed), result in runs.items():
        for row in result.get("log", []):
            rows.append(
                {
                    "condition": condition,
                    "seed": seed,
                    "t": int(row.get("t", 0)),
                    "success_rate": _float(row.get("success_rate")),
                    "cost_ratio": _float(row.get("cost_ratio")),
                    "loop_rate": _float(row.get("loop_rate")),
                    "route_diversity": _float(row.get("route_diversity")),
                    "stagnation_rate": _float(row.get("stagnation_rate")),
                    "revisit_max": _float(row.get("revisit_max")),
                    "memory_size": _float(row.get("memory_size")),
                    "retrieval_concentration": _float(row.get("retrieval_concentration")),
                }
            )
    return rows


def _source_quality(sources: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [src.get("quality", {}) for src in sources]
    costs = [_float(q.get("cost_ratio")) for q in qualities]
    steps = [_float(q.get("steps")) for q in qualities]
    revisits = [_float(q.get("revisit_max")) for q in qualities]
    stagnation = [_float(q.get("stagnation_rate")) for q in qualities]
    successes = [1.0 if q.get("success") else 0.0 for q in qualities]
    loops = [1.0 if q.get("looped") else 0.0 for q in qualities]
    return {
        "source_count": len(sources),
        "source_success_rate": _mean(successes),
        "source_loop_rate": _mean(loops),
        "source_cost_mean": _mean(costs),
        "source_cost_max": max(costs) if costs else 0.0,
        "source_steps_mean": _mean(steps),
        "source_revisit_max": max(revisits) if revisits else 0.0,
        "source_stagnation_mean": _mean(stagnation),
    }


def _memory_rows(runs: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (condition, seed), result in runs.items():
        for item in result.get("memory_audit", {}).get("memory_items", []):
            sources = item.get("sources", [])
            quality = _source_quality(sources)
            rows.append(
                {
                    "condition": condition,
                    "seed": seed,
                    "kind": item.get("kind", ""),
                    "retrieval_count": int(item.get("retrieval_count", 0)),
                    "text": item.get("text", ""),
                    **quality,
                }
            )
    rows.sort(key=lambda row: (-int(row["retrieval_count"]), str(row["condition"]), str(row["seed"])))
    return rows


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


def _plot_scatter(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib.pyplot as plt

    metrics = [
        ("cost_ratio", "Cost ratio"),
        ("loop_rate", "Loop rate"),
        ("stagnation_rate", "Stagnation rate"),
    ]
    active = [row for row in rows if int(row["t"]) > 0]
    labels = [label for label in CONDITION_ORDER if any(row["condition"] == label for row in active)]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), squeeze=False)
    for ax, (key, title) in zip(axes.flat, metrics):
        for label in labels:
            series = [row for row in active if row["condition"] == label]
            ax.scatter(
                [row["retrieval_concentration"] for row in series],
                [row[key] for row in series],
                s=44,
                alpha=0.78,
                label=label,
                color=CONDITION_COLORS.get(label),
                edgecolor="white",
                linewidth=0.5,
            )
        xs = [row["retrieval_concentration"] for row in active]
        ys = [row[key] for row in active]
        ax.set_title(f"{title}\nr={_pearson(xs, ys):.2f}")
        ax.set_xlabel("Retrieval concentration")
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.25)
    axes.flat[0].legend(fontsize=8, loc="best")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_provenance(memory_rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [row for row in memory_rows if int(row["retrieval_count"]) > 0]
    labels = [label for label in CONDITION_ORDER if any(row["condition"] == label for row in rows)]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), squeeze=False)
    for ax, y_key, title in [
        (axes.flat[0], "source_cost_max", "Max source cost"),
        (axes.flat[1], "source_stagnation_mean", "Mean source stagnation"),
    ]:
        for label in labels:
            series = [row for row in rows if row["condition"] == label]
            ax.scatter(
                [row["retrieval_count"] for row in series],
                [row[y_key] for row in series],
                s=42,
                alpha=0.78,
                label=label,
                color=CONDITION_COLORS.get(label),
                edgecolor="white",
                linewidth=0.5,
            )
        ax.set_title(title)
        ax.set_xlabel("Retrieval count")
        ax.set_ylabel(title)
        ax.grid(True, alpha=0.25)
    axes.flat[0].legend(fontsize=8, loc="best")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_report(
    path: Path,
    *,
    round_rows: list[dict[str, Any]],
    memory_rows: list[dict[str, Any]],
) -> None:
    active = [row for row in round_rows if int(row["t"]) > 0]
    corr_metrics = ["cost_ratio", "loop_rate", "stagnation_rate"]
    lines = [
        "# Maze Mechanism Statistics",
        "",
        "## Retrieval Correlations",
        "",
        "| metric | pearson r vs retrieval_concentration |",
        "|---|---:|",
    ]
    for metric in corr_metrics:
        xs = [row["retrieval_concentration"] for row in active]
        ys = [row[metric] for row in active]
        lines.append(f"| {metric} | {_pearson(xs, ys):.3f} |")
    lines += [
        "",
        "## High-Retrieval Provenance",
        "",
        "| condition | seed | retrievals | source_count | source_success | max_source_cost | mean_source_stagnation | text |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in memory_rows[:12]:
        text = str(row["text"]).replace("|", "/")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["condition"]),
                    str(row["seed"]),
                    str(row["retrieval_count"]),
                    str(row["source_count"]),
                    f"{row['source_success_rate']:.3f}",
                    f"{row['source_cost_max']:.3f}",
                    f"{row['source_stagnation_mean']:.3f}",
                    text,
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Figures",
        "",
        "![Mechanism scatter](mechanism_scatter.png)",
        "",
        "![Provenance scatter](provenance_scatter.png)",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = _parser().parse_args()
    runs = _load_runs(args)
    out_dir = Path(args.out_dir)
    round_rows = _round_rows(runs)
    memory_rows = _memory_rows(runs)
    _write_csv(round_rows, out_dir / "round_metrics.csv")
    _write_csv(memory_rows, out_dir / "memory_provenance.csv")
    _plot_scatter(round_rows, out_dir / "mechanism_scatter.png")
    _plot_provenance(memory_rows, out_dir / "provenance_scatter.png")
    _write_report(out_dir / "mechanism_stats.md", round_rows=round_rows, memory_rows=memory_rows)
    print(f"wrote {out_dir.resolve()}")


if __name__ == "__main__":
    main()
