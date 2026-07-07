"""Figure 1: the shared-experience feedback loop (mechanism microscope) plus a
case study where the same heldout maze/agent degrades into a silent ant-mill loop
as the write protocol moves from frozen -> private -> shared-append -> consolidated.

Reads the E2 runs directly so the case study is reproducible, not hand-drawn.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


# The monotonic case surfaced by the E2 audit: same maze, same agent, final round.
CASE_SEED = 4
CASE_TASK = "heldout_trap_240025"
CASE_AGENT = 1
CASE_ARMS = [
    ("frozen_reviewer", "Frozen write-only", "#A7ABB3"),
    ("private_reviewer", "Private memory", "#4C78A8"),
    ("shared_append_ga", "Shared append", "#72B7B2"),
    ("shared_consolidated_expel", "Shared consolidated", "#E45756"),
]


def _load_case(runs_dir: Path, seed: int, task_id: str, agent_id: int, arm: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = runs_dir / f"n4_gt_false_seed{seed}_e2_{arm}" / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    for record in result.get("heldout_records", []):
        if int(record["t"]) != int(result["log"][-1]["t"]):
            continue
        for episode in record["episodes"]:
            if episode["task_id"] != task_id:
                continue
            for agent in episode["agents"]:
                if int(agent["agent_id"]) == agent_id:
                    return agent["route"], episode["task"]
    raise KeyError(f"case not found for arm {arm}")


def _draw_maze(ax, task: dict[str, Any], route: dict[str, Any], color: str) -> None:
    import matplotlib.pyplot as plt

    grid = task["grid"]
    h = task["height"]
    w = task["width"]
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell == "#":
                ax.add_patch(plt.Rectangle((x, h - y - 1), 1, 1, color="#2B2F36", linewidth=0))
    path = [tuple(p) for p in route.get("path", [])]
    visits = Counter(path)
    xs = [p[0] + 0.5 for p in path]
    ys = [h - p[1] - 0.5 for p in path]
    ax.plot(xs, ys, color=color, linewidth=1.6, alpha=0.85, zorder=3)
    # Revisit heat: cells visited >=2 times get a marker scaled by visit count.
    for cell, n in visits.items():
        if n >= 2:
            ax.scatter(
                [cell[0] + 0.5], [h - cell[1] - 0.5],
                s=18 + 26 * (n - 1), color=color, alpha=0.35, zorder=2, linewidths=0,
            )
    sx, sy = task["start"]
    gx, gy = task["goal"]
    ax.scatter([sx + 0.5], [h - sy - 0.5], marker="s", s=46, color="#0EA5E9", zorder=5, edgecolors="white", linewidths=0.6)
    ax.scatter([gx + 0.5], [h - gy - 0.5], marker="*", s=120, color="#22C55E", zorder=5, edgecolors="white", linewidths=0.6)
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")


def _draw_schematic(ax) -> None:
    """Compact write -> pool -> retrieve -> act -> reflect -> write feedback cycle."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch

    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    nodes = {
        "agents": (2.2, 7.7, "Multi-agent\nsolvers"),
        "reflect": (7.0, 8.1, "Reviewer\nreflection"),
        "pool": (7.4, 4.5, "Shared\nexperience\npool"),
        "retrieve": (4.6, 2.2, "Retrieve\n+ inject"),
    }
    colors = {"agents": "#4C78A8", "reflect": "#E45756", "pool": "#E45756", "retrieve": "#72B7B2"}
    boxes = {}
    for key, (x, y, label) in nodes.items():
        box = plt.Rectangle((x - 1.25, y - 0.9), 2.5, 1.8, facecolor="white",
                            edgecolor=colors[key], linewidth=1.8, zorder=3)
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center", fontsize=9.5, zorder=4)
        boxes[key] = (x, y)

    def arrow(a, b, text="", rad=0.25, tx=0, ty=0):
        (x0, y0), (x1, y1) = boxes[a], boxes[b]
        ar = FancyArrowPatch((x0, y0), (x1, y1), connectionstyle=f"arc3,rad={rad}",
                             arrowstyle="-|>", mutation_scale=16, linewidth=1.6,
                             color="#6B7280", shrinkA=26, shrinkB=26, zorder=2)
        ax.add_patch(ar)
        if text:
            ax.text((x0 + x1) / 2 + tx, (y0 + y1) / 2 + ty, text, ha="center", va="center",
                    fontsize=8.2, color="#374151", style="italic")

    arrow("agents", "reflect", "trajectories", rad=-0.25, ty=0.7)
    arrow("reflect", "pool", "consolidate", rad=-0.25, tx=1.35)
    arrow("pool", "retrieve", "top-k", rad=-0.25, tx=1.15, ty=-0.2)
    arrow("retrieve", "agents", "guide actions", rad=-0.25, tx=-1.75)
    ax.text(4.7, 5.2, "positive\nfeedback", ha="center", va="center", fontsize=9.5,
            color="#E45756", fontweight="bold")


def build(runs_dir: Path, out_base: Path) -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none"})
    fig = plt.figure(figsize=(13, 6.2))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.05, 1.0], hspace=0.28, wspace=0.12)

    ax_schema = fig.add_subplot(gs[0, 0:2])
    _draw_schematic(ax_schema)
    ax_schema.set_title("a  Shared-experience feedback loop", loc="left", fontsize=12, fontweight="bold")

    ax_text = fig.add_subplot(gs[0, 2:4])
    ax_text.axis("off")
    ax_text.set_title("b  Silent degradation on one held-out maze", loc="left", fontsize=12, fontweight="bold")
    ax_text.text(
        0.0, 0.86,
        "Same maze, same agent, final round (seed 4).\n"
        "Every route is legal — no wall crossing, no false\n"
        "submit — and every arm still reaches the goal.\n"
        "As the write protocol consolidates experience, the\n"
        "agent revisits more cells and finally loops, while\n"
        "shortest path stays 38 steps.",
        ha="left", va="top", fontsize=10.5, linespacing=1.5,
    )

    routes = {}
    task = None
    for arm, _, _ in CASE_ARMS:
        route, tsk = _load_case(runs_dir, CASE_SEED, CASE_TASK, CASE_AGENT, arm)
        routes[arm] = route
        task = tsk

    for col, (arm, label, color) in enumerate(CASE_ARMS):
        ax = fig.add_subplot(gs[1, col])
        _draw_maze(ax, task, routes[arm], color)
        r = routes[arm]
        loop_tag = "  •  LOOP" if r.get("looped") else ""
        ax.set_title(
            f"{label}\nsteps {r['steps']}  ·  cost {r['cost_ratio']:.2f}\n"
            f"max revisit {r['revisit_max']}{loop_tag}",
            fontsize=9.5, color=color if r.get("looped") else "#111827",
            fontweight="bold" if r.get("looped") else "normal",
        )

    fig.suptitle(
        "Figure 1  |  Consensus consolidation turns correct shared experience into a silent ant-mill loop",
        fontsize=13, fontweight="bold", x=0.5, y=0.99,
    )
    out_base.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(out_base.with_suffix(f".{ext}"), dpi=600 if ext == "png" else None, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_base}.{{png,pdf,svg}}")


def main() -> None:
    p = argparse.ArgumentParser(description="Build Figure 1 (mechanism + case study).")
    p.add_argument("--runs-dir", default="./runs_maze_beta_e2")
    p.add_argument("--out-base", default="./runs_maze_beta_e2_evidence/figure1_mechanism")
    args = p.parse_args()
    build(Path(args.runs_dir), Path(args.out_base))


if __name__ == "__main__":
    main()
