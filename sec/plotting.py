from __future__ import annotations

from pathlib import Path
from typing import Any


def plot_condition(result: dict[str, Any], out_dir: Path) -> Path:
    import matplotlib.pyplot as plt

    log = result["log"]
    t = [row["t"] for row in log]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for key in ["A_t", "C_t", "G_t"]:
        ax.plot(t, [row[key] for row in log], marker="o", label=key)
    ax.set_xlabel("t")
    ax.set_ylabel("value")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title(result["summary"]["condition"])
    ax.legend()
    ax.grid(True, alpha=0.25)
    path = out_dir / "curves.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_compare(results: list[dict[str, Any]], out_dir: Path) -> Path:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for result in results:
        log = result["log"]
        ax.plot([row["t"] for row in log], [row["A_t"] for row in log], marker="o", label=result["summary"]["condition"])
    ax.set_xlabel("t")
    ax.set_ylabel("A_t")
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Held-out accuracy comparison")
    ax.legend()
    ax.grid(True, alpha=0.25)
    path = out_dir / "compare_A_t.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
