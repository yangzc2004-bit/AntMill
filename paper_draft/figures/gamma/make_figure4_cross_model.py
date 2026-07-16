"""Figure 4: cross-model forest plot (DeepSeek-V3 vs Qwen3-32B, consolidated - frozen).

Data sources:
- DeepSeek-V3: runs_maze_beta_e2_stats_5seed (E2, 5 seeds, t=5).
- Qwen3-32B: runs_maze_gamma_p2_qwen256_stats/p2_gate_report.json (3 seeds, t=3).
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PANELS = [
    {
        "title": "Success-only excess steps",
        "rows": [
            ("DeepSeek-V3", 11.84, 7.66, 16.02, True),
            ("Qwen3-32B", 5.83, -3.75, 15.20, False),
        ],
    },
    {
        "title": "Loop rate",
        "rows": [
            ("DeepSeek-V3", 0.138, 0.092, 0.188, True),
            ("Qwen3-32B", -0.076, -0.153, 0.000, False),
        ],
    },
    {
        "title": "Success",
        "rows": [
            ("DeepSeek-V3", -0.171, -0.242, -0.100, True),
            ("Qwen3-32B", 0.042, -0.049, 0.132, False),
        ],
    },
]

COLORS = {"DeepSeek-V3": "#b2182b", "Qwen3-32B": "#2166ac"}

fig, axes = plt.subplots(1, 3, figsize=(9.2, 2.4))
for ax, panel in zip(axes, PANELS):
    for y, (model, mean, lo, hi, sig) in enumerate(panel["rows"]):
        color = COLORS[model]
        ax.plot([lo, hi], [y, y], color=color, lw=1.8, solid_capstyle="butt")
        ax.plot(
            mean,
            y,
            marker="o" if sig else "o",
            markerfacecolor=color if sig else "white",
            markeredgecolor=color,
            markersize=7,
            markeredgewidth=1.6,
        )
    ax.axvline(0.0, color="0.45", lw=0.9, ls="--", zorder=0)
    ax.set_yticks(range(len(panel["rows"])))
    ax.set_yticklabels([row[0] for row in panel["rows"]], fontsize=9)
    ax.set_ylim(-0.6, len(panel["rows"]) - 0.4)
    ax.invert_yaxis()
    ax.set_title(panel["title"], fontsize=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

axes[0].annotate(
    "worse →",
    xy=(0.97, 0.06),
    xycoords="axes fraction",
    ha="right",
    fontsize=8,
    color="0.35",
)
axes[2].annotate(
    "← worse",
    xy=(0.05, 0.06),
    xycoords="axes fraction",
    ha="left",
    fontsize=8,
    color="0.35",
)
fig.suptitle("")
fig.tight_layout()
out = Path(__file__).parent
fig.savefig(out / "figure4_cross_model.pdf", bbox_inches="tight")
fig.savefig(out / "figure4_cross_model.png", dpi=200, bbox_inches="tight")
print("wrote", out / "figure4_cross_model.pdf")
