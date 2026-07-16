from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42

mpl.rcParams.update(
    {
        "font.size": 7,
        "axes.labelsize": 7,
        "axes.titlesize": 8,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "legend.fontsize": 6.5,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.8,
        "lines.linewidth": 1.5,
        "legend.frameon": False,
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }
)


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "generated" / "moa_paper"
OUT = ROOT / "figures" / "moa"

COLORS = {
    "no_transfer": "#4D4D4D",
    "self_report": "#0F4D92",
    "local_acceptance": "#42949E",
    "bounded_recent": "#42949E",
    "bounded_diverse": "#B7792B",
    "manager": "#9A4D8E",
    "good": "#2E9E44",
    "bad": "#B64342",
    "neutral": "#A8A8A8",
    "light": "#E8E8E8",
    "paper": "#F7F7F7",
}

ARM_ORDER = ["no_transfer", "self_report", "local_acceptance"]
ARM_LABELS = {
    "no_transfer": "No transfer",
    "self_report": "Cumulative self-report",
    "local_acceptance": "Local admission",
}
ARM_MARKERS = {
    "no_transfer": "o",
    "self_report": "s",
    "local_acceptance": "^",
}


def panel_label(ax: plt.Axes, label: str, x: float = -0.10, y: float = 1.04) -> None:
    ax.text(
        x,
        y,
        label,
        transform=ax.transAxes,
        fontsize=8,
        fontweight="bold",
        ha="left",
        va="bottom",
    )


def save_figure(fig: plt.Figure, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in {
        "svg": {},
        "pdf": {},
        "tiff": {"dpi": 600},
        "png": {"dpi": 300},
    }.items():
        fig.savefig(
            OUT / f"{stem}.{suffix}",
            bbox_inches="tight",
            pad_inches=0.03,
            **kwargs,
        )
    plt.close(fig)


def box(
    ax: plt.Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    text: str,
    facecolor: str,
    edgecolor: str,
    fontsize: float = 6.5,
    weight: str = "normal",
) -> FancyBboxPatch:
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.015",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=0.9,
    )
    ax.add_patch(patch)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight=weight,
        color="#222222",
    )
    return patch


def arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str = "#666666",
    style: str = "-|>",
    linestyle: str = "-",
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle=style,
            mutation_scale=8,
            linewidth=0.9,
            color=color,
            linestyle=linestyle,
        )
    )


def figure1_system() -> None:
    fig = plt.figure(figsize=(7.01, 3.23))
    gs = fig.add_gridspec(
        2,
        3,
        width_ratios=[1.55, 1.0, 1.0],
        height_ratios=[1.35, 1.0],
        hspace=0.36,
        wspace=0.30,
    )
    ax_a = fig.add_subplot(gs[:, 0])
    ax_b = fig.add_subplot(gs[0, 1:])
    ax_c = fig.add_subplot(gs[1, 1:])

    for ax in (ax_a, ax_b, ax_c):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    panel_label(ax_a, "a", x=-0.02, y=1.00)
    panel_label(ax_b, "b", x=-0.02, y=1.00)
    panel_label(ax_c, "c", x=-0.02, y=1.00)

    ax_a.text(
        0.02,
        0.96,
        "Layered parallel agent testbed",
        fontsize=8,
        fontweight="bold",
        va="top",
    )
    ax_a.add_patch(
        Rectangle(
            (0.02, 0.44),
            0.96,
            0.42,
            facecolor="#FAFBFC",
            edgecolor="none",
            zorder=0,
        )
    )
    ax_a.add_patch(
        Rectangle(
            (0.02, 0.06),
            0.96,
            0.32,
            facecolor="#FBF7FA",
            edgecolor="none",
            zorder=0,
        )
    )
    ax_a.text(
        0.50,
        0.852,
        "COMMON INPUT",
        ha="center",
        va="center",
        fontsize=4.9,
        fontweight="bold",
        color="#777777",
    )

    task = FancyBboxPatch(
        (0.36, 0.73),
        0.28,
        0.09,
        boxstyle="round,pad=0.010,rounding_size=0.018",
        facecolor=COLORS["paper"],
        edgecolor="#777777",
        linewidth=0.9,
    )
    ax_a.add_patch(task)
    ax_a.text(
        0.50,
        0.785,
        "Shared task",
        ha="center",
        va="center",
        fontsize=6.0,
        fontweight="bold",
    )
    ax_a.text(
        0.50,
        0.750,
        "same prompt",
        ha="center",
        va="center",
        fontsize=4.8,
        color="#666666",
    )

    worker_x = (0.04, 0.365, 0.69)
    worker_centers = tuple(x + 0.135 for x in worker_x)
    arrow(ax_a, (0.50, 0.73), (0.50, 0.67), style="-")
    ax_a.plot(
        [worker_centers[0], worker_centers[-1]],
        [0.67, 0.67],
        color="#777777",
        lw=0.9,
        solid_capstyle="round",
    )
    for i, (x, center_x) in enumerate(zip(worker_x, worker_centers), start=1):
        arrow(ax_a, (center_x, 0.67), (center_x, 0.62))
        card = FancyBboxPatch(
            (x, 0.48),
            0.27,
            0.14,
            boxstyle="round,pad=0.009,rounding_size=0.016",
            facecolor="#F0F5FA",
            edgecolor=COLORS["self_report"],
            linewidth=0.9,
        )
        ax_a.add_patch(card)
        ax_a.text(
            center_x,
            0.568,
            f"Worker {i}",
            ha="center",
            va="center",
            fontsize=5.8,
            fontweight="bold",
        )
        ax_a.text(
            center_x,
            0.518,
            "private workspace",
            ha="center",
            va="center",
            fontsize=4.9,
            color="#555555",
        )
        arrow(ax_a, (center_x, 0.48), (center_x, 0.43), style="-")

    ax_a.plot(
        [worker_centers[0], worker_centers[-1]],
        [0.43, 0.43],
        color="#777777",
        lw=0.9,
        solid_capstyle="round",
    )
    ax_a.plot(
        [0.05, 0.95],
        [0.38, 0.38],
        color="#A9A9A9",
        lw=0.9,
        linestyle=(0, (3, 2)),
    )
    ax_a.text(
        0.79,
        0.388,
        "BLINDING BARRIER",
        ha="center",
        va="bottom",
        fontsize=4.8,
        fontweight="bold",
        color="#777777",
        bbox={"facecolor": "#FBF7FA", "edgecolor": "none", "pad": 0.8},
    )
    arrow(
        ax_a,
        (0.50, 0.43),
        (0.50, 0.32),
        color=COLORS["manager"],
    )

    state = FancyBboxPatch(
        (0.29, 0.195),
        0.42,
        0.13,
        boxstyle="round,pad=0.010,rounding_size=0.018",
        facecolor="#F5EDF4",
        edgecolor=COLORS["manager"],
        linewidth=0.9,
    )
    ax_a.add_patch(state)
    ax_a.text(
        0.50,
        0.278,
        "Blinded experience\nstate",
        ha="center",
        va="center",
        fontsize=5.4,
        fontweight="bold",
        linespacing=0.95,
    )
    ax_a.text(
        0.50,
        0.222,
        "hidden outcomes withheld",
        ha="center",
        va="center",
        fontsize=4.8,
        color="#666666",
    )

    arrow(
        ax_a,
        (0.50, 0.195),
        (0.50, 0.145),
        color=COLORS["manager"],
    )
    ax_a.text(
        0.535,
        0.17,
        "one-way broadcast",
        ha="left",
        va="center",
        fontsize=4.8,
        color=COLORS["manager"],
    )
    next_layer = FancyBboxPatch(
        (0.39, 0.07),
        0.22,
        0.07,
        boxstyle="round,pad=0.009,rounding_size=0.024",
        facecolor="white",
        edgecolor=COLORS["manager"],
        linewidth=0.9,
    )
    ax_a.add_patch(next_layer)
    ax_a.text(
        0.50,
        0.105,
        "Next layer",
        ha="center",
        va="center",
        fontsize=5.2,
        fontweight="bold",
        color=COLORS["manager"],
    )

    ax_b.text(
        0.02,
        0.96,
        "What enters the shared state?",
        fontsize=8,
        fontweight="bold",
        va="top",
    )
    policy_specs = [
        (
            0.01,
            "No transfer\nno context",
            COLORS["no_transfer"],
            "#ECECEC",
        ),
        (
            0.175,
            "Cumulative\nself-report",
            COLORS["self_report"],
            "#E8EFF7",
        ),
        (
            0.34,
            "Bounded recent\nlatest 3",
            COLORS["bounded_recent"],
            "#E4F1F2",
        ),
        (
            0.505,
            "Diversity router\n3 local identities",
            COLORS["bounded_diverse"],
            "#F7EFE3",
        ),
        (
            0.67,
            "Local gate\nsuccess + >=t",
            COLORS["good"],
            "#EAF4EA",
        ),
        (
            0.835,
            "Recursive\nmanager playbook",
            COLORS["manager"],
            "#F1E8F0",
        ),
    ]
    for x, text, edge, face in policy_specs:
        box(
            ax_b,
            (x, 0.38),
            0.145,
            0.30,
            text,
            face,
            edge,
            fontsize=4.35,
        )
    ax_b.text(
        0.02,
        0.16,
        "External pass counts and hidden-test outcomes are withheld from all recipients.",
        fontsize=6.3,
        color="#555555",
    )

    ax_c.text(
        0.02,
        0.96,
        "Independent external audit",
        fontsize=8,
        fontweight="bold",
        va="top",
    )
    box(
        ax_c,
        (0.03, 0.48),
        0.23,
        0.25,
        "Hidden evaluator\nCore + all tests",
        "#F7E6E4",
        COLORS["bad"],
        weight="bold",
    )
    ax_c.plot(
        [0.31, 0.31],
        [0.18, 0.82],
        color="#A0A0A0",
        linestyle=(0, (3, 2)),
        lw=0.9,
    )
    ax_c.text(
        0.295,
        0.50,
        "isolation",
        ha="center",
        va="center",
        rotation=90,
        fontsize=6,
        color="#777777",
    )
    outcomes = [
        ("Score collapse", "external score falls", COLORS["bad"]),
        ("Implementation lock-in", "same snapshot hash", COLORS["self_report"]),
        ("Behavioral lock-in", "same failed-test set", COLORS["manager"]),
    ]
    for i, (title, detail, color) in enumerate(outcomes):
        y = 0.68 - i * 0.25
        ax_c.scatter([0.39], [y], s=22, color=color, zorder=3)
        ax_c.text(0.44, y + 0.035, title, fontsize=6.8, fontweight="bold")
        ax_c.text(0.44, y - 0.045, detail, fontsize=6.1, color="#555555")

    save_figure(fig, "figure1_moa_system")


def plot_arm_lines(
    ax: plt.Axes,
    frame: pd.DataFrame,
    y_col: str,
    ylabel: str,
    ylim: tuple[float, float] | None = None,
) -> None:
    for arm in ARM_ORDER:
        subset = frame.loc[frame["arm"] == arm].sort_values("layer")
        ax.plot(
            subset["layer"],
            subset[y_col],
            color=COLORS[arm],
            marker=ARM_MARKERS[arm],
            ms=3.5,
            label=ARM_LABELS[arm],
            zorder=3,
        )
    ax.set_xlabel("Layer")
    ax.set_ylabel(ylabel)
    ax.set_xticks([1, 3, 5, 7, 9, 12])
    if ylim:
        ax.set_ylim(*ylim)
    ax.tick_params(direction="out", length=2.5)


def figure2_main_result() -> None:
    curves = pd.read_csv(DATA / "main_depth12_curves.csv")
    replications = pd.read_csv(DATA / "lockin_replication_layers.csv")
    mitigation_layers = pd.read_csv(DATA / "mitigation_three_arm_layers.csv")
    mitigation_summary = pd.read_csv(
        DATA / "mitigation_three_arm_summary.csv"
    )
    boundary_summary = pd.read_csv(DATA / "log_query_boundary_summary.csv")

    fig = plt.figure(figsize=(7.01, 5.12))
    gs = fig.add_gridspec(
        2,
        3,
        width_ratios=[1.08, 1.0, 1.12],
        height_ratios=[1.42, 1.0],
        hspace=0.48,
        wspace=0.47,
    )
    ax_a = fig.add_subplot(gs[0, :])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[1, 1])
    ax_d = fig.add_subplot(gs[1, 2])

    ax_a.axvspan(
        4.5,
        12.5,
        color=COLORS["self_report"],
        alpha=0.035,
        linewidth=0,
        zorder=0,
    )
    for arm in ARM_ORDER:
        subset = curves.loc[curves["arm"] == arm].sort_values("layer")
        x = subset["layer"].to_numpy()
        y = subset["mean_all_score"].to_numpy()
        lo = subset["min_all_score"].to_numpy()
        hi = subset["max_all_score"].to_numpy()
        ax_a.vlines(
            x,
            lo,
            hi,
            color=COLORS[arm],
            linewidth=3.2,
            alpha=0.15,
            zorder=1,
        )
        ax_a.plot(
            x,
            y,
            color=COLORS[arm],
            marker=ARM_MARKERS[arm],
            ms=3.8,
            lw=1.45,
            label=ARM_LABELS[arm],
            zorder=3,
        )
    ax_a.axhline(33 / 37, color="#A0A0A0", lw=0.8, ls=(0, (3, 2)))
    ax_a.text(
        12.15,
        33 / 37,
        "33/37",
        va="center",
        fontsize=6,
        color="#777777",
    )
    ax_a.axvline(
        5,
        color=COLORS["self_report"],
        lw=0.8,
        ls=(0, (2, 2)),
        alpha=0.35,
        zorder=0,
    )
    ax_a.text(
        8.5,
        0.985,
        "Main run: exact convergence (L5-L12)",
        ha="center",
        va="top",
        fontsize=5.8,
        fontweight="bold",
        color=COLORS["self_report"],
    )
    ax_a.text(
        0.012,
        0.035,
        "Worker min-max; one coupled trajectory per arm ($n=3$ workers/layer)",
        transform=ax_a.transAxes,
        fontsize=5.2,
        color="#666666",
    )
    ax_a.set_xlim(0.7, 12.5)
    ax_a.set_ylim(-0.02, 1.02)
    ax_a.set_xticks(range(1, 13))
    ax_a.set_xlabel("Layer")
    ax_a.set_ylabel("External all-test score")
    ax_a.legend(
        ncol=3,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        handlelength=2.0,
        columnspacing=1.5,
    )
    ax_a.tick_params(direction="out", length=2.5)
    panel_label(ax_a, "a", x=-0.055, y=1.06)

    heat_specs = [
        ("Coding r2", "kimi-coding-self-report-r2"),
        ("MaaS r1", "kimi-maas-self-report-r1"),
        ("MaaS main", "kimi-maas-self-report-r2"),
    ]
    matrix = np.full((len(heat_specs), 12), np.nan)
    for row_index, (_, run_id) in enumerate(heat_specs):
        subset = replications.loc[
            replications["run_id"] == run_id
        ].sort_values("layer")
        for item in subset.itertuples():
            matrix[row_index, int(item.layer) - 1] = int(
                item.unique_valid_snapshots
            )
    cmap = mpl.colors.ListedColormap(
        [COLORS["self_report"], "#AFC7E1", "white"]
    )
    cmap.set_bad("#EFEFEF")
    norm = mpl.colors.BoundaryNorm([0.5, 1.5, 2.5, 3.5], cmap.N)
    ax_b.imshow(
        np.ma.masked_invalid(matrix),
        aspect="auto",
        interpolation="nearest",
        cmap=cmap,
        norm=norm,
    )
    ax_b.set_xticks(
        [0, 2, 4, 6, 8, 11],
        ["1", "3", "5", "7", "9", "12"],
    )
    ax_b.set_yticks(
        np.arange(len(heat_specs)),
        [label for label, _ in heat_specs],
    )
    ax_b.set_xlabel("Layer")
    ax_b.set_title(
        "Independent lock-in audits",
        loc="left",
        fontsize=7.2,
        fontweight="bold",
        pad=11,
    )
    ax_b.tick_params(axis="both", length=0)
    ax_b.set_xticks(np.arange(-0.5, 12, 1), minor=True)
    ax_b.set_yticks(np.arange(-0.5, len(heat_specs), 1), minor=True)
    ax_b.grid(which="minor", color="#D8D8D8", linewidth=0.45)
    ax_b.tick_params(which="minor", bottom=False, left=False)
    ax_b.text(
        1.0,
        1.025,
        "unique repository snapshots",
        transform=ax_b.transAxes,
        ha="right",
        va="bottom",
        fontsize=5.0,
        color="#666666",
    )
    panel_label(ax_b, "b", x=-0.18, y=1.10)

    cfgpipe_styles = [
        ("no_transfer", "No transfer", COLORS["no_transfer"], "o"),
        (
            "bounded_recent",
            "Recent 3",
            COLORS["bounded_recent"],
            "s",
        ),
        (
            "bounded_diverse",
            "Distinct 3",
            COLORS["bounded_diverse"],
            "^",
        ),
    ]
    for arm, label, color, marker in cfgpipe_styles:
        subset = mitigation_layers.loc[
            mitigation_layers["arm"] == arm
        ].sort_values("layer")
        ax_c.plot(
            subset["layer"],
            subset["unique_primary_implementations"],
            color=color,
            marker=marker,
            ms=3.6,
            lw=1.45,
            label=label,
            zorder=3,
        )
    ax_c.axvspan(
        2.0,
        3.0,
        color=COLORS["bounded_diverse"],
        alpha=0.07,
        linewidth=0,
    )
    ax_c.annotate(
        "one-layer delay",
        xy=(2.55, 1.55),
        xytext=(4.0, 2.35),
        fontsize=5.2,
        color=COLORS["bounded_diverse"],
        arrowprops={
            "arrowstyle": "-|>",
            "color": COLORS["bounded_diverse"],
            "lw": 0.7,
        },
    )
    ax_c.set_xlim(0.8, 6.2)
    ax_c.set_ylim(0.8, 3.25)
    ax_c.set_xticks(range(1, 7))
    ax_c.set_yticks([1, 2, 3])
    ax_c.set_xlabel("Layer")
    ax_c.set_ylabel("Unique primary implementations")
    ax_c.set_title(
        "cfgpipe: local routing delays",
        loc="left",
        fontsize=7.2,
        fontweight="bold",
        pad=4,
    )
    ax_c.legend(
        loc="upper right",
        fontsize=5.0,
        handlelength=1.4,
        borderaxespad=0.2,
    )
    ax_c.text(
        0.02,
        0.03,
        "Mean score: 30.0, 34.0, 34.0 / 37",
        transform=ax_c.transAxes,
        fontsize=4.8,
        color="#666666",
    )
    ax_c.tick_params(direction="out", length=2.5)
    panel_label(ax_c, "c", x=-0.16, y=1.10)

    task_specs = [
        (
            "cfgpipe",
            mitigation_summary,
            37.0,
            15.0,
            "o",
        ),
        (
            "log_query",
            boundary_summary,
            134.0,
            6.0,
            "s",
        ),
    ]
    arm_colors = {
        "no_transfer": COLORS["no_transfer"],
        "bounded_recent": COLORS["bounded_recent"],
        "bounded_diverse": COLORS["bounded_diverse"],
    }
    point_labels = {
        "no_transfer": "No",
        "bounded_recent": "Recent",
        "bounded_diverse": "Distinct",
    }
    for task, frame, score_total, diversity_total, marker in task_specs:
        auc_column = (
            "diversity_auc_layers_2_6"
            if task == "cfgpipe"
            else "diversity_auc_layers_2_3"
        )
        for row in frame.itertuples():
            x_value = float(row.mean_all_passed) / score_total
            y_value = float(getattr(row, auc_column)) / diversity_total
            color = arm_colors[str(row.arm)]
            ax_d.scatter(
                [x_value],
                [y_value],
                marker=marker,
                s=31,
                facecolor=color,
                edgecolor="white",
                linewidth=0.55,
                zorder=4,
            )
            offset = {
                ("cfgpipe", "no_transfer"): (-1, -11),
                ("cfgpipe", "bounded_recent"): (-21, -9),
                ("cfgpipe", "bounded_diverse"): (5, 5),
                ("log_query", "no_transfer"): (-2, 7),
                ("log_query", "bounded_recent"): (-27, 7),
                ("log_query", "bounded_diverse"): (4, 7),
            }[(task, str(row.arm))]
            ax_d.annotate(
                point_labels[str(row.arm)],
                (x_value, y_value),
                xytext=offset,
                textcoords="offset points",
                fontsize=4.8,
                color=color,
            )
    ax_d.axhline(1.0, color="#D0D0D0", lw=0.7, ls=(0, (3, 2)))
    ax_d.set_xlim(0.78, 0.995)
    ax_d.set_ylim(0.25, 1.08)
    ax_d.set_xticks([0.80, 0.90, 1.00])
    ax_d.set_yticks([1 / 3, 2 / 3, 1.0], ["0.33", "0.67", "1.00"])
    ax_d.set_xlabel("Mean normalized all-test score")
    ax_d.set_ylabel("Normalized implementation diversity")
    ax_d.set_title(
        "Quality-diversity effect is task-bound",
        loc="left",
        fontsize=7.2,
        fontweight="bold",
        pad=4,
    )
    ax_d.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#777777",
                markeredgecolor="white",
                markersize=5,
                label="cfgpipe",
            ),
            Line2D(
                [0],
                [0],
                marker="s",
                color="none",
                markerfacecolor="#777777",
                markeredgecolor="white",
                markersize=5,
                label="log_query",
            ),
        ],
        loc="lower right",
        fontsize=4.8,
        handletextpad=0.3,
        borderaxespad=0.2,
    )
    ax_d.tick_params(direction="out", length=2.5)
    panel_label(ax_d, "d", x=-0.17, y=1.10)

    save_figure(fig, "figure2_depth12_lockin")


def figure3_boundaries() -> None:
    gate = pd.read_csv(DATA / "local_gate_threshold_replay.csv")
    cross = pd.read_csv(DATA / "raw_append_cross_model.csv")
    recursive = pd.read_csv(DATA / "recursive_manager_boundaries.csv")

    fig = plt.figure(figsize=(7.01, 4.05))
    gs = fig.add_gridspec(
        2,
        5,
        width_ratios=[1.16, 1.16, 0.10, 1.0, 1.0],
        height_ratios=[1.0, 1.0],
        hspace=0.58,
        wspace=0.54,
    )
    ax_a = fig.add_subplot(gs[:, :2])
    ax_b = fig.add_subplot(gs[0, 3:])
    ax_c = fig.add_subplot(gs[1, 3:])

    ax_a.axvspan(
        0.75,
        2.25,
        color=COLORS["good"],
        alpha=0.07,
        linewidth=0,
        zorder=0,
    )
    ax_a.plot(
        gate["minimum_successful_commands"],
        gate["catastrophic_recall"],
        color=COLORS["bad"],
        marker="s",
        ms=4.2,
        lw=1.45,
        drawstyle="steps-post",
        zorder=3,
    )
    ax_a.plot(
        gate["minimum_successful_commands"],
        gate["high_quality_retention"],
        color=COLORS["self_report"],
        marker="o",
        ms=4.2,
        lw=1.45,
        drawstyle="steps-post",
        zorder=3,
    )
    ax_a.axvline(3, color=COLORS["neutral"], lw=0.9, ls=(0, (3, 2)))
    ax_a.text(
        1.5,
        0.55,
        "sample-specific\nPareto region",
        ha="center",
        va="center",
        fontsize=5.8,
        color=COLORS["good"],
    )
    ax_a.annotate(
        "Prospectively frozen arm $t=3$\n29/34 high-quality outputs retained",
        xy=(3, gate.loc[gate["minimum_successful_commands"] == 3, "high_quality_retention"].iloc[0]),
        xytext=(3.35, 0.72),
        fontsize=5.2,
        color="#555555",
        arrowprops={
            "arrowstyle": "-|>",
            "color": "#777777",
            "lw": 0.7,
        },
    )
    ax_a.text(
        4.05,
        1.015,
        "False-completion rejection",
        ha="left",
        va="bottom",
        fontsize=5.3,
        color=COLORS["bad"],
    )
    ax_a.text(
        4.55,
        0.43,
        "High-quality retention",
        ha="left",
        va="center",
        fontsize=5.3,
        color=COLORS["self_report"],
    )
    ax_a.set_xlim(-0.2, 6.35)
    ax_a.set_ylim(-0.02, 1.04)
    ax_a.set_xlabel("Minimum successful commands required")
    ax_a.set_ylabel("Fraction of outputs")
    ax_a.set_yticks([0, 0.5, 1.0])
    ax_a.set_title(
        "Admission threshold trade-off",
        loc="left",
        fontsize=8.0,
        fontweight="bold",
    )
    ax_a.text(
        0.98,
        0.035,
        "Replay curve retrospective; $t=3$ arm prospective ($n=36$)",
        transform=ax_a.transAxes,
        fontsize=5.3,
        color="#666666",
        ha="right",
        va="bottom",
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8},
    )
    panel_label(ax_a, "a", x=-0.10, y=1.04)

    cross = cross.copy()
    cross["label"] = [
        "DeepSeek\nr1",
        "GLM-5\nr1",
        "Kimi\ncoding r1",
        "Kimi\ncoding r2",
        "Kimi\nMaaS r2",
    ]
    x = np.arange(len(cross))
    for xi, row in zip(x, cross.itertuples()):
        positive = row.zero_score_rate > 0
        color = COLORS["bad"] if positive else COLORS["self_report"]
        if positive:
            ax_b.vlines(
                xi,
                0,
                row.zero_score_rate,
                color=color,
                linewidth=1.8,
            )
        ax_b.scatter(
            [xi],
            [row.zero_score_rate],
            facecolor=color if positive else "white",
            edgecolor=color,
            linewidth=1.0,
            s=24,
            zorder=3,
        )
        ax_b.text(
            xi,
            row.zero_score_rate + 0.006,
            f"{int(row.zero_score_events)}/{int(row.worker_outcomes)}",
            ha="center",
            va="bottom",
            fontsize=5.8,
        )
    ax_b.set_xticks(x, cross["label"])
    ax_b.set_ylim(-0.005, 0.085)
    ax_b.set_yticks([0, 0.04, 0.08], ["0", "4%", "8%"])
    ax_b.set_ylabel("Zero-score outcomes")
    ax_b.set_title(
        "Zero-score tails are intermittent",
        loc="left",
        fontsize=7.5,
        fontweight="bold",
    )
    ax_b.tick_params(axis="x", length=0)
    panel_label(ax_b, "b", x=-0.13, y=1.04)

    plot_rows = recursive.loc[
        recursive["terminal_control"].notna()
        & ~recursive["confirmatory_status"].str.contains("invalid")
    ].copy()
    plot_rows = plot_rows.iloc[[0, 1, 2, 3]]
    labels = [
        "cfgpipe\nfixed task",
        "log_query\nfixed task",
        "xjq\nfixed task",
        "cfgpipe\nsequential*",
    ]
    effects = plot_rows["treatment_minus_control"].to_numpy()
    y = np.arange(len(effects))[::-1]
    effect_colors = [
        COLORS["bad"] if value < 0 else COLORS["good"] for value in effects
    ]
    ax_c.axvspan(-0.10, 0, color=COLORS["bad"], alpha=0.045, linewidth=0)
    ax_c.axvspan(0, 0.60, color=COLORS["good"], alpha=0.035, linewidth=0)
    ax_c.axvline(0, color="#777777", lw=0.8, ls=(0, (3, 2)))
    for idx, (yi, value, color) in enumerate(zip(y, effects, effect_colors)):
        exploratory = idx == len(effects) - 1
        ax_c.plot([0, value], [yi, yi], color=color, lw=1.8)
        ax_c.scatter(
            [value],
            [yi],
            marker="D" if exploratory else "o",
            facecolor="white" if exploratory else color,
            edgecolor=color,
            linewidth=1.0,
            s=26,
            zorder=3,
        )
        if value >= 0:
            ax_c.text(
                value + 0.012,
                yi,
                f"{value:+.3f}",
                ha="left",
                va="center",
                fontsize=5.8,
            )
        else:
            ax_c.annotate(
                f"{value:+.3f}",
                xy=(value, yi),
                xytext=(0, -8),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=5.8,
            )
    ax_c.set_yticks(y, labels)
    ax_c.set_xlim(-0.10, 0.60)
    ax_c.set_xlabel("Terminal score difference (manager - no transfer)")
    ax_c.set_title(
        "Manager direction depends on task",
        loc="left",
        fontsize=7.5,
        fontweight="bold",
    )
    panel_label(ax_c, "c", x=-0.13, y=1.04)

    save_figure(fig, "figure3_admission_boundaries")


def main() -> None:
    figure1_system()
    figure2_main_result()
    figure3_boundaries()
    print(f"Wrote figures to {OUT}")


if __name__ == "__main__":
    main()
