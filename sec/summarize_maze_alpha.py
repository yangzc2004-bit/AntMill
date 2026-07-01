from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import statistics
from pathlib import Path
from typing import Any


DEFAULT_RUNS = {
    "frozen": "runs_maze_alpha_mas_frozen_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_frozen_reviewer/result.json",
    "shared_reviewer": "runs_maze_alpha_mas_shared_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_reviewer/result.json",
    "private_fixed": "runs_maze_alpha_mas_private_fixed_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_private_reviewer/result.json",
    "shared_direct": "runs_maze_alpha_mas_shared_direct_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_direct/result.json",
    "shared_oracle": "runs_maze_alpha_mas_shared_oracle_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_oracle/result.json",
}

CONDITION_ORDER = ["frozen", "private_fixed", "shared_reviewer", "shared_direct", "shared_oracle"]
CONDITION_COLORS = {
    "frozen": "#8a8f98",
    "private_fixed": "#4c78a8",
    "shared_reviewer": "#54a24b",
    "shared_direct": "#e45756",
    "shared_oracle": "#b279a2",
}
CONDITION_STYLES = {
    "frozen": "-",
    "private_fixed": "-",
    "shared_reviewer": "-",
    "shared_direct": "--",
    "shared_oracle": ":",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Maze Alpha strategy-degradation runs.")
    parser.add_argument("--out-dir", default="./runs_maze_alpha_summary_h3_t3_v1")
    parser.add_argument(
        "--run",
        action="append",
        default=[],
        help="Optional condition[:seed]=path/to/result.json. Defaults to the current h3/t3 seed0 matrix.",
    )
    return parser


def _parse_run_label(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        return raw, "0"
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
    for raw_label, path in specs.items():
        condition, seed = _parse_run_label(raw_label)
        p = Path(path)
        if not p.exists():
            missing.append(f"{raw_label}: {p}")
            continue
        runs[(condition, seed)] = json.loads(p.read_text(encoding="utf-8"))
    if missing:
        raise FileNotFoundError("Missing result files:\n" + "\n".join(missing))
    return runs


def _rows(runs: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (label, seed), result in runs.items():
        for row in result.get("log", []):
            rows.append(
                {
                    "condition": label,
                    "seed": seed,
                    "t": row.get("t"),
                    "success_rate": row.get("success_rate"),
                    "cost_ratio": row.get("cost_ratio"),
                    "loop_rate": row.get("loop_rate"),
                    "route_diversity": row.get("route_diversity"),
                    "stagnation_rate": row.get("stagnation_rate"),
                    "revisit_max": row.get("revisit_max"),
                    "memory_size": row.get("memory_size"),
                    "retrieval_concentration": row.get("retrieval_concentration"),
                }
            )
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "condition",
        "seed",
        "t",
        "success_rate",
        "cost_ratio",
        "loop_rate",
        "route_diversity",
        "stagnation_rate",
        "revisit_max",
        "memory_size",
        "retrieval_concentration",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_any_csv(rows: list[dict[str, Any]], path: Path) -> None:
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


def _mean_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = [
        "success_rate",
        "cost_ratio",
        "loop_rate",
        "route_diversity",
        "stagnation_rate",
        "revisit_max",
        "memory_size",
        "retrieval_concentration",
    ]
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["condition"]), int(row["t"]))].append(row)
    means: list[dict[str, Any]] = []
    for (condition, t), group in sorted(grouped.items()):
        item: dict[str, Any] = {"condition": condition, "seed": "mean", "t": t, "n_seeds": len(group)}
        for metric in metrics:
            vals = [float(row[metric]) for row in group if row.get(metric) is not None]
            item[metric] = statistics.mean(vals) if vals else 0.0
            item[f"{metric}_stdev"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
        means.append(item)
    return means


def _plot_curves(rows: list[dict[str, Any]], path: Path, *, show_error: bool = False) -> None:
    import matplotlib.pyplot as plt

    metrics = [
        ("success_rate", "Success rate"),
        ("cost_ratio", "Cost ratio"),
        ("loop_rate", "Loop rate"),
        ("route_diversity", "Route diversity"),
        ("memory_size", "Memory size"),
        ("retrieval_concentration", "Retrieval concentration"),
    ]
    present = set(str(row["condition"]) for row in rows)
    labels = [label for label in CONDITION_ORDER if label in present] + sorted(present - set(CONDITION_ORDER))
    fig, axes = plt.subplots(2, 3, figsize=(14, 7), squeeze=False)
    for ax, (key, title) in zip(axes.ravel(), metrics):
        for label in labels:
            series = [row for row in rows if row["condition"] == label]
            series.sort(key=lambda row: int(row["t"]))
            ax.plot(
                [row["t"] for row in series],
                [row[key] for row in series],
                marker="o",
                label=label,
                color=CONDITION_COLORS.get(label),
                linestyle=CONDITION_STYLES.get(label, "-"),
            )
            if show_error:
                stdev_key = f"{key}_stdev"
                if any(float(row.get(stdev_key, 0.0)) for row in series):
                    xs = [row["t"] for row in series]
                    ys = [float(row[key]) for row in series]
                    es = [float(row.get(stdev_key, 0.0)) for row in series]
                    lower = [y - e for y, e in zip(ys, es)]
                    upper = [y + e for y, e in zip(ys, es)]
                    if key in {"success_rate", "loop_rate", "route_diversity", "retrieval_concentration"}:
                        lower = [max(0.0, val) for val in lower]
                        upper = [min(1.0, val) for val in upper]
                    ax.fill_between(
                        xs,
                        lower,
                        upper,
                        color=CONDITION_COLORS.get(label),
                        alpha=0.12,
                        linewidth=0,
                    )
        ax.set_title(title)
        ax.set_xlabel("Round")
        ax.grid(True, alpha=0.25)
    axes[0][0].legend(fontsize=8, loc="best")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_final_bars(rows: list[dict[str, Any]], path: Path) -> None:
    import matplotlib.pyplot as plt

    present = set(str(row["condition"]) for row in rows)
    labels = [label for label in CONDITION_ORDER if label in present] + sorted(present - set(CONDITION_ORDER))
    final_rows = []
    for label in labels:
        series = [row for row in rows if row["condition"] == label]
        final_rows.append(max(series, key=lambda row: int(row["t"])))
    metrics = [
        ("success_rate", "Success"),
        ("cost_ratio", "Cost"),
        ("loop_rate", "Loop"),
        ("route_diversity", "Diversity"),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.8), squeeze=False)
    x = range(len(final_rows))
    for ax, (key, title) in zip(axes.ravel(), metrics):
        ax.bar(x, [row[key] for row in final_rows], color=[CONDITION_COLORS.get(row["condition"]) for row in final_rows])
        ax.set_title(f"Final {title}")
        ax.set_xticks(list(x))
        ax.set_xticklabels([row["condition"] for row in final_rows], rotation=35, ha="right")
        ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _memory_rows(runs: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (label, seed), result in runs.items():
        audit = result.get("memory_audit", {})
        for item in audit.get("memory_items", []):
            rows.append(
                {
                    "condition": label,
                    "seed": seed,
                    "kind": item.get("kind", ""),
                    "retrieval_count": item.get("retrieval_count", 0),
                    "sources": len(item.get("sources", [])),
                    "text": item.get("text", ""),
                }
            )
    rows.sort(key=lambda row: (-int(row["retrieval_count"]), str(row["condition"])))
    return rows


def _write_memory_table(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "| condition | kind | retrievals | sources | text |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        text = str(row["text"]).replace("|", "\\|")
        lines.append(
            f"| {row['condition']} | {row['kind']} | {row['retrieval_count']} | {row['sources']} | {text} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _seed_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    seeds: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("seed") != "mean":
            seeds[str(row["condition"])].add(str(row["seed"]))
    return {condition: len(vals) for condition, vals in seeds.items()}


def _write_report(rows: list[dict[str, Any]], mean_rows: list[dict[str, Any]], memory_rows: list[dict[str, Any]], out_dir: Path) -> None:
    final = {}
    for condition in dict.fromkeys(row["condition"] for row in mean_rows):
        series = [row for row in mean_rows if row["condition"] == condition]
        final[condition] = max(series, key=lambda row: int(row["t"]))
    counts = _seed_counts(rows)

    lines = [
        "# Maze Alpha Summary",
        "",
        "## Final Mean Metrics",
        "",
        "| condition | seeds | success | cost | loop | diversity | memory | retrieval concentration |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, row in final.items():
        lines.append(
            f"| {condition} | {counts.get(condition, int(row.get('n_seeds', 0)))} | "
            f"{row['success_rate']:.3f} | {row['cost_ratio']:.3f} | "
            f"{row['loop_rate']:.3f} | {row['route_diversity']:.3f} | "
            f"{row['memory_size']} | {row['retrieval_concentration']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- Frozen memory is the storage-only control: writes occur but retrieval concentration stays zero and behavior is unchanged.",
            "- Shared reviewer improves success and cost while monotonically compressing route diversity.",
            "- Private fixed memory is weaker and less stable, but preserves more diversity than shared reviewer.",
            "- Shared direct/oracle collapse onto one highly retrieved correct strategy and show worse success, cost, loop, stagnation, and revisit metrics.",
            "",
            "## Top Retrieved Memories",
            "",
            "| condition | retrievals | text |",
            "|---|---:|---|",
        ]
    )
    for row in [r for r in memory_rows if int(r["retrieval_count"]) > 0][:12]:
        text = str(row["text"]).replace("|", "\\|")
        lines.append(f"| {row['condition']} | {row['retrieval_count']} | {text} |")
    lines.extend(
        [
            "",
            "## Figures",
            "",
            "![Mean curves](curves_mean.png)",
            "",
            "![Final mean bars](bar_final_mean.png)",
            "",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = _parser().parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = _load_runs(args)
    rows = _rows(runs)
    mean_rows = _mean_rows(rows)
    memories = _memory_rows(runs)
    _write_csv(rows, out_dir / "summary.csv")
    _write_any_csv(mean_rows, out_dir / "summary_mean.csv")
    _write_any_csv(memories, out_dir / "memory_summary.csv")
    _write_memory_table(memories, out_dir / "memory_table.md")
    _plot_curves(rows, out_dir / "curves_by_seed.png")
    _plot_curves(mean_rows, out_dir / "curves_mean.png", show_error=True)
    _plot_final_bars(mean_rows, out_dir / "bar_final_mean.png")
    _write_report(rows, mean_rows, memories, out_dir)
    print(f"wrote {out_dir.resolve()}")


if __name__ == "__main__":
    main()
