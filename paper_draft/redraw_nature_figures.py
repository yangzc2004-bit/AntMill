from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["font.size"] = 7
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["legend.frameon"] = False

ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "paper_draft" / "figures"

SUMMARY_T3 = ROOT / "runs_maze_alpha_summary_h3_t3_seed0_seed1_seed2_full" / "summary_mean.csv"
MECH_ROUNDS = ROOT / "runs_maze_alpha_mechanism_stats_h3_t3_seed0_seed1_seed2" / "round_metrics.csv"
MECH_MEMORY = ROOT / "runs_maze_alpha_mechanism_stats_h3_t3_seed0_seed1_seed2" / "memory_provenance.csv"
SUMMARY_T5 = ROOT / "runs_maze_alpha_summary_targeted_t5_seed0" / "summary_mean.csv"
CASE_ROUTES = ROOT / "runs_maze_alpha_mechanism_audit_targeted_t5_seed0" / "case_routes.csv"

TARGETED_RESULTS = {
    "frozen": ROOT
    / "runs_maze_alpha_mas_targeted_t5_seed0_frozen_v1_v3_c4"
    / "n4_gt_false_seed0_maze_mad_frozen_reviewer"
    / "result.json",
    "shared_reviewer": ROOT
    / "runs_maze_alpha_mas_targeted_t5_seed0_shared_reviewer_v1_v3_c4"
    / "n4_gt_false_seed0_maze_mad_shared_reviewer"
    / "result.json",
    "shared_direct": ROOT
    / "runs_maze_alpha_mas_targeted_t5_seed0_shared_direct_v1_v3_c4"
    / "n4_gt_false_seed0_maze_mad_shared_direct"
    / "result.json",
}

COND_ORDER = ["frozen", "private_fixed", "shared_reviewer", "shared_direct", "shared_oracle"]
COND_ORDER_T5 = ["frozen", "shared_reviewer", "shared_direct"]
LABELS = {
    "frozen": "Frozen",
    "private_fixed": "Private",
    "shared_reviewer": "Shared reviewer",
    "shared_direct": "Shared direct",
    "shared_oracle": "Shared oracle",
}
COLORS = {
    "frozen": "#8F8F8F",
    "private_fixed": "#5B7FCA",
    "shared_reviewer": "#42949E",
    "shared_direct": "#D9544D",
    "shared_oracle": "#9A4D8E",
}
STYLES = {
    "frozen": "-",
    "private_fixed": "-",
    "shared_reviewer": "-",
    "shared_direct": "--",
    "shared_oracle": ":",
}
MARKERS = {
    "frozen": "o",
    "private_fixed": "o",
    "shared_reviewer": "o",
    "shared_direct": "s",
    "shared_oracle": "D",
}


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def f(row: dict[str, Any], key: str) -> float:
    value = row.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    xm, ym = mean(xs), mean(ys)
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    xd = sum((x - xm) ** 2 for x in xs) ** 0.5
    yd = sum((y - ym) ** 2 for y in ys) ** 0.5
    return num / (xd * yd) if xd and yd else 0.0


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    xm, ym = mean(xs), mean(ys)
    den = sum((x - xm) ** 2 for x in xs)
    slope = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den if den else 0.0
    return slope, ym - slope * xm


def save(fig: plt.Figure, name: str, *, dpi: int = 450) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    base = FIG_DIR / name
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def add_panel_label(ax: plt.Axes, label: str, *, x: float = -0.12, y: float = 1.04, color: str = "#272727") -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8,
        fontweight="bold",
        color=color,
    )


def style_axis(ax: plt.Axes, *, xlabel: str | None = None, ylabel: str | None = None) -> None:
    if xlabel:
        ax.set_xlabel(xlabel, labelpad=2)
    if ylabel:
        ax.set_ylabel(ylabel, labelpad=2)
    ax.grid(True, axis="y", color="#D8D8D8", alpha=0.55, linewidth=0.55)
    ax.tick_params(axis="both", labelsize=7, length=3, width=0.7)


def legend_handles(conditions: list[str]) -> list[Line2D]:
    return [
        Line2D(
            [0],
            [0],
            color=COLORS[c],
            lw=1.8,
            marker=MARKERS[c],
            markersize=4.5,
            linestyle=STYLES[c],
            label=LABELS[c],
        )
        for c in conditions
    ]


def metric_grid(csv_path: Path, name: str, *, conditions: list[str], show_error: bool, title: str) -> None:
    rows = read_csv(csv_path)
    metrics = [
        ("success_rate", "Success", "success rate"),
        ("cost_ratio", "Path cost", "actual / shortest"),
        ("loop_rate", "Looping", "loop rate"),
        ("route_diversity", "Route diversity", "route diversity"),
        ("memory_size", "Memory size", "items"),
        ("retrieval_concentration", "Retrieval focus", "concentration"),
    ]
    panel_labels = list("abcdef")
    fig, axes = plt.subplots(2, 3, figsize=(7.25, 4.55), sharex=False)
    fig.subplots_adjust(top=0.84, left=0.07, right=0.99, bottom=0.10, hspace=0.55, wspace=0.36)
    for ax, (key, panel_title, ylabel), panel in zip(axes.ravel(), metrics, panel_labels):
        for condition in conditions:
            series = [row for row in rows if row.get("condition") == condition]
            series.sort(key=lambda row: int(float(row["t"])))
            if not series:
                continue
            xs = [int(float(row["t"])) for row in series]
            ys = [f(row, key) for row in series]
            ax.plot(
                xs,
                ys,
                lw=1.65,
                marker=MARKERS[condition],
                markersize=4.2,
                color=COLORS[condition],
                linestyle=STYLES[condition],
                label=LABELS[condition],
                zorder=3,
            )
            stdev_key = f"{key}_stdev"
            if show_error and any(f(row, stdev_key) > 0 for row in series):
                es = [f(row, stdev_key) for row in series]
                lo = [y - e for y, e in zip(ys, es)]
                hi = [y + e for y, e in zip(ys, es)]
                if key in {"success_rate", "loop_rate", "route_diversity", "retrieval_concentration"}:
                    lo = [max(0.0, v) for v in lo]
                    hi = [min(1.0, v) for v in hi]
                ax.fill_between(xs, lo, hi, color=COLORS[condition], alpha=0.10, linewidth=0, zorder=1)
        ax.set_title(panel_title, fontsize=8, pad=4)
        ax.set_xticks(sorted({int(float(row["t"])) for row in rows}))
        style_axis(ax, xlabel="round", ylabel=ylabel)
        add_panel_label(ax, panel)
        if key == "success_rate":
            ax.set_ylim(0.48 if len(conditions) == 3 else 0.82, 1.03)
        elif key in {"loop_rate", "route_diversity", "retrieval_concentration"}:
            ax.set_ylim(bottom=0)
        elif key == "memory_size":
            ax.set_ylim(bottom=0)
    handles = legend_handles(conditions)
    fig.legend(
        handles=handles,
        labels=[h.get_label() for h in handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.965),
        ncol=len(conditions),
        fontsize=7,
        handlelength=2.2,
        columnspacing=1.1,
    )
    fig.suptitle(title, fontsize=9, fontweight="bold", y=0.995)
    save(fig, name)


def mechanism_scatter() -> None:
    rows = [row for row in read_csv(MECH_ROUNDS) if int(float(row["t"])) > 0]
    panels = [
        ("cost_ratio", "Path cost", "actual / shortest"),
        ("loop_rate", "Looping", "loop rate"),
        ("stagnation_rate", "Stagnation", "stagnation rate"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.45))
    fig.subplots_adjust(top=0.76, left=0.07, right=0.99, bottom=0.22, wspace=0.36)
    for ax, (key, title, ylabel), panel in zip(axes, panels, "abc"):
        xs_all = [f(row, "retrieval_concentration") for row in rows]
        ys_all = [f(row, key) for row in rows]
        ax.axvspan(0.7, 1.02, color="#F6CFCB", alpha=0.28, linewidth=0)
        for condition in COND_ORDER:
            series = [row for row in rows if row["condition"] == condition]
            if not series:
                continue
            ax.scatter(
                [f(row, "retrieval_concentration") for row in series],
                [f(row, key) for row in series],
                s=34,
                color=COLORS[condition],
                alpha=0.86,
                edgecolor="white",
                linewidth=0.5,
                marker=MARKERS[condition],
                zorder=3,
            )
        if len(xs_all) > 1:
            slope, intercept = linear_fit(xs_all, ys_all)
            x0, x1 = min(xs_all), max(xs_all)
            ax.plot([x0, x1], [slope * x0 + intercept, slope * x1 + intercept], color="#272727", lw=1.0, alpha=0.55)
        ax.text(
            0.97,
            0.08,
            f"r = {pearson(xs_all, ys_all):.2f}",
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=7,
            color="#272727",
        )
        ax.set_title(title, fontsize=8, pad=4)
        ax.set_xlim(-0.03, 1.03)
        ax.set_ylim(bottom=0 if key != "cost_ratio" else None)
        style_axis(ax, xlabel="retrieval concentration", ylabel=ylabel)
        add_panel_label(ax, panel)
    handles = legend_handles(COND_ORDER)
    fig.legend(
        handles=handles,
        labels=[h.get_label() for h in handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=5,
        fontsize=7,
        handlelength=2.0,
        columnspacing=0.9,
    )
    fig.suptitle("High retrieval concentration tracks inefficient behavior", fontsize=9, fontweight="bold", y=1.06)
    save(fig, "mechanism_scatter")


def provenance_scatter() -> None:
    rows = [row for row in read_csv(MECH_MEMORY) if int(float(row["retrieval_count"])) > 0]
    panels = [
        ("source_cost_max", "Worst source trajectory", "max source cost"),
        ("source_stagnation_mean", "Stagnant source trajectories", "mean source stagnation"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 2.65))
    fig.subplots_adjust(top=0.78, left=0.09, right=0.99, bottom=0.22, wspace=0.35)
    max_x = max(f(row, "retrieval_count") for row in rows)
    for ax, (key, title, ylabel), panel in zip(axes, panels, "ab"):
        ax.axvspan(20, max_x + 1.5, color="#F6CFCB", alpha=0.28, linewidth=0)
        for condition in COND_ORDER:
            series = [row for row in rows if row["condition"] == condition]
            if not series:
                continue
            ax.scatter(
                [f(row, "retrieval_count") for row in series],
                [f(row, key) for row in series],
                s=[26 + 5 * f(row, "source_count") for row in series],
                color=COLORS[condition],
                alpha=0.82,
                edgecolor="white",
                linewidth=0.5,
                marker=MARKERS[condition],
                zorder=3,
            )
        ax.set_title(title, fontsize=8, pad=4)
        ax.set_xlim(0, max_x + 1.5)
        ax.set_ylim(bottom=0)
        style_axis(ax, xlabel="retrieval count", ylabel=ylabel)
        add_panel_label(ax, panel)
        ax.text(
            0.98,
            0.92,
            "highly reused",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=6.5,
            color="#B64342",
        )
    handles = legend_handles([c for c in COND_ORDER if any(row["condition"] == c for row in rows)])
    fig.legend(
        handles=handles,
        labels=[h.get_label() for h in handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=4,
        fontsize=7,
        handlelength=2.0,
        columnspacing=0.9,
    )
    fig.suptitle("Memory provenance separates correct text from good source trajectories", fontsize=9, fontweight="bold", y=1.05)
    save(fig, "provenance_scatter")


def load_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def record_for(result: dict[str, Any], t: int) -> dict[str, Any]:
    for record in result.get("heldout_records", []):
        if int(record["t"]) == t:
            return record
    raise KeyError(t)


def episode_for(result: dict[str, Any], t: int, task_id: str) -> dict[str, Any]:
    for episode in record_for(result, t).get("episodes", []):
        if episode.get("task_id") == task_id:
            return episode
    raise KeyError(task_id)


def agent_for(episode: dict[str, Any], agent_id: int) -> dict[str, Any]:
    for agent in episode.get("agents", []):
        if int(agent.get("agent_id", -1)) == agent_id:
            return agent
    raise KeyError(agent_id)


def draw_case() -> None:
    case = read_csv(CASE_ROUTES)[0]
    t = int(float(case["round"]))
    task_id = case["task_id"]
    agent_id = int(float(case["agent_id"]))
    results = {condition: load_result(path) for condition, path in TARGETED_RESULTS.items()}
    fig, axes = plt.subplots(1, 3, figsize=(7.25, 2.85))
    fig.subplots_adjust(top=0.78, bottom=0.07, left=0.02, right=0.99, wspace=0.05)
    cmap = ListedColormap(["#FFFFFF", "#272727"])
    for ax, condition, panel in zip(axes, COND_ORDER_T5, "abc"):
        episode = episode_for(results[condition], t, task_id)
        task = episode["task"]
        agent = agent_for(episode, agent_id)
        route = agent["route"]
        grid = [[1 if cell == "#" else 0 for cell in row] for row in task["grid"]]
        ax.imshow(grid, cmap=cmap, origin="upper", interpolation="nearest", vmin=0, vmax=1)
        path = [tuple(cell) for cell in route.get("path", [])]
        if path:
            xs = [cell[0] for cell in path]
            ys = [cell[1] for cell in path]
            ax.plot(xs, ys, color=COLORS[condition], lw=1.35, alpha=0.88, solid_capstyle="round", zorder=3)
            counts = Counter(path)
            hot = [(cell, count) for cell, count in counts.items() if count >= 3]
            if hot:
                ax.scatter(
                    [cell[0] for cell, _ in hot],
                    [cell[1] for cell, _ in hot],
                    s=[10 + 2.2 * count for _, count in hot],
                    color=COLORS[condition],
                    alpha=0.28,
                    edgecolor="none",
                    zorder=2,
                )
        sx, sy = task["start"]
        gx, gy = task["goal"]
        ax.scatter([sx], [sy], marker="s", s=25, color="#22D7E6", edgecolor="white", linewidth=0.35, zorder=4)
        ax.scatter([gx], [gy], marker="*", s=58, color="#2E9E44", edgecolor="white", linewidth=0.35, zorder=4)
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        add_panel_label(ax, panel, x=0.02, y=0.96, color="white")
        title = LABELS[condition]
        subtitle = (
            f"steps {int(route.get('steps', 0))} | cost {float(route.get('cost_ratio', 0.0)):.2f} | "
            f"loop {'yes' if route.get('looped') else 'no'}"
        )
        ax.set_title(f"{title}\n{subtitle}", fontsize=7.3, pad=4)
    fig.suptitle("Same heldout maze, same agent: shared direct memory forms a silent loop", fontsize=9, fontweight="bold", y=0.98)
    save(fig, "targeted_t5_case", dpi=500)


def main() -> None:
    metric_grid(
        SUMMARY_T3,
        "full_matrix_curves",
        conditions=COND_ORDER,
        show_error=True,
        title="Short-horizon memory matrix (T=3): shared reviewer helps, high concentration raises risk",
    )
    mechanism_scatter()
    provenance_scatter()
    metric_grid(
        SUMMARY_T5,
        "targeted_t5_curves",
        conditions=COND_ORDER_T5,
        show_error=False,
        title="Longer feedback horizon (T=5): direct shared memory collapses late",
    )
    draw_case()


if __name__ == "__main__":
    main()
