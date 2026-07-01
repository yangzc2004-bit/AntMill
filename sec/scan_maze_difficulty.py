from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median, quantiles
from typing import Any

from .maze_env import make_maze_tasks, maze_static_metrics


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline difficulty scan for generated maze benchmarks.")
    p.add_argument("--sizes", default="9,11,13,15")
    p.add_argument("--families", default="trap,phase_shift")
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--split", default="heldout")
    p.add_argument("--out-dir", default="./runs_maze_difficulty")
    return p


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0}
    if len(values) < 4:
        return {
            "min": min(values),
            "p25": min(values),
            "median": median(values),
            "p75": max(values),
            "max": max(values),
        }
    qs = quantiles(values, n=4, method="inclusive")
    return {"min": min(values), "p25": qs[0], "median": median(values), "p75": qs[2], "max": max(values)}


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["family"]), int(row["width"])), []).append(row)

    summaries: list[dict[str, Any]] = []
    for (family, size), group in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][0])):
        shortest = [float(row["shortest_path_length"]) for row in group]
        branch = [float(row["branch_cells"]) for row in group]
        dead = [float(row["dead_ends"]) for row in group]
        off_path = [float(row["off_path_open_cells"]) for row in group]
        choice = [float(row["choice_points_on_shortest"]) for row in group]
        summaries.append(
            {
                "family": family,
                "size": size,
                "n": len(group),
                "shortest": _percentiles(shortest),
                "branch_cells_mean": mean(branch) if branch else 0.0,
                "dead_ends_mean": mean(dead) if dead else 0.0,
                "off_path_open_mean": mean(off_path) if off_path else 0.0,
                "choice_points_on_shortest_mean": mean(choice) if choice else 0.0,
                "recommended_role": _recommend_role(size, shortest, branch, off_path),
            }
        )
    return summaries


def _recommend_role(size: int, shortest: list[float], branch: list[float], off_path: list[float]) -> str:
    med_shortest = median(shortest) if shortest else 0.0
    mean_branch = mean(branch) if branch else 0.0
    mean_off_path = mean(off_path) if off_path else 0.0
    if size <= 9 or med_shortest < 18:
        return "debug/smoke"
    if 18 <= med_shortest <= 35 and mean_branch >= 8 and mean_off_path >= 20:
        return "pilot"
    if med_shortest > 35 and mean_branch >= 12 and mean_off_path >= 35:
        return "formal_candidate"
    return "needs_review"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _plot(path: Path, summaries: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    labels = [f"{row['size']} {row['family']}" for row in summaries]
    med = [row["shortest"]["median"] for row in summaries]
    p25 = [row["shortest"]["p25"] for row in summaries]
    p75 = [row["shortest"]["p75"] for row in summaries]
    branch = [row["branch_cells_mean"] for row in summaries]
    x = list(range(len(labels)))
    fig, axes = plt.subplots(1, 2, figsize=(max(8, len(labels) * 1.2), 4))
    axes[0].bar(x, med, color="#2563eb")
    axes[0].errorbar(x, med, yerr=[[m - a for m, a in zip(med, p25)], [b - m for b, m in zip(p75, med)]], fmt="none", ecolor="#111827")
    axes[0].set_title("Shortest path length")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=35, ha="right")
    axes[1].bar(x, branch, color="#16a34a")
    axes[1].set_title("Mean branch cells")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=35, ha="right")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def scan(args: argparse.Namespace) -> dict[str, Any]:
    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    families = [s.strip() for s in args.families.split(",") if s.strip()]
    rows: list[dict[str, Any]] = []
    for size in sizes:
        for family in families:
            tasks = make_maze_tasks(split=args.split, n=args.n, seed=args.seed, width=size, height=size, family=family)
            rows.extend(maze_static_metrics(task) for task in tasks)

    summaries = _summarize(rows)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "maze_difficulty_rows.csv", rows)
    (out_dir / "maze_difficulty_summary.json").write_text(
        json.dumps({"args": vars(args), "summary": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _plot(out_dir / "maze_difficulty.png", summaries)
    return {"rows": rows, "summary": summaries, "out_dir": str(out_dir)}


def main() -> None:
    result = scan(_parser().parse_args())
    for row in result["summary"]:
        shortest = row["shortest"]
        print(
            f"{row['size']}x{row['size']} {row['family']}: "
            f"shortest median={shortest['median']:.1f} p25={shortest['p25']:.1f} p75={shortest['p75']:.1f} "
            f"branches={row['branch_cells_mean']:.1f} off_path={row['off_path_open_mean']:.1f} "
            f"role={row['recommended_role']}",
            flush=True,
        )
    print(f"ARTIFACTS {Path(result['out_dir']).resolve()}", flush=True)


if __name__ == "__main__":
    main()
