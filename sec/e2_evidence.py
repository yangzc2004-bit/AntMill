from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .maze_stats import paired_diff, route_rows


CONDITIONS = {
    "mas_nomem": "e2_mas_nomem",
    "frozen": "e2_frozen_reviewer",
    "private": "e2_private_reviewer",
    "shared_append": "e2_shared_append_ga",
    "shared_consolidated": "e2_shared_consolidated_expel",
}

DISPLAY = {
    "mas_nomem": "MAS no memory",
    "frozen": "Frozen write-only",
    "private": "Private memory",
    "shared_append": "Shared append",
    "shared_consolidated": "Shared consolidated",
}

DISPLAY_SHORT = {
    "mas_nomem": "No\nmemory",
    "frozen": "Frozen\nwrite-only",
    "private": "Private",
    "shared_append": "Shared\nappend",
    "shared_consolidated": "Shared\nconsol.",
}

COLORS = {
    "mas_nomem": "#8A8F98",
    "frozen": "#A7ABB3",
    "private": "#4C78A8",
    "shared_append": "#72B7B2",
    "shared_consolidated": "#E45756",
}

FIG_METRICS = [
    ("success_excess_steps", "Success-only excess steps", "steps"),
    ("looped", "Looped routes", "rate"),
    ("stagnation_rate", "Stagnation rate", "rate"),
    ("revisit_max", "Max revisits", "cells"),
]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build the E2 5-seed evidence package.")
    p.add_argument("--runs-dir", default="./runs_maze_beta_e2")
    p.add_argument("--stats-dir", default="./runs_maze_beta_e2_stats_5seed")
    p.add_argument("--stats-vs-private-dir", default="./runs_maze_beta_e2_stats_5seed_vs_private")
    p.add_argument("--out-dir", default="./runs_maze_beta_e2_evidence")
    p.add_argument("--seeds", default="0,1,2,3,4")
    return p


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


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


def _fmt(x: Any, digits: int = 3) -> str:
    if x is None or x == "":
        return "n/a"
    try:
        return f"{float(x):.{digits}f}"
    except (TypeError, ValueError):
        return str(x)


def _stats_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["condition"], row["metric"]): row for row in rows}


def _result_path(runs_dir: Path, condition: str, seed: int) -> Path:
    run_id = CONDITIONS[condition]
    return runs_dir / f"n4_gt_false_seed{seed}_{run_id}" / "result.json"


def _audit_path(runs_dir: Path, condition: str, seed: int) -> Path:
    run_id = CONDITIONS[condition]
    return runs_dir / f"n4_gt_false_seed{seed}_{run_id}" / "memory_audit.json"


def _final_log(result: dict[str, Any]) -> dict[str, Any]:
    log = result.get("log", [])
    return dict(log[-1]) if log else {}


def _top_share(counts: list[int], k: int) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    return float(sum(sorted(counts, reverse=True)[:k]) / total)


def _effective_count(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    probs = [c / total for c in counts if c > 0]
    return float(math.exp(-sum(p * math.log(p) for p in probs)))


def _op_counts(writes: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for write in writes:
        mode = str(write.get("write_mode", ""))
        if ":" in mode:
            counts[mode.split(":", 1)[1]] += 1
        elif mode:
            counts[mode] += 1
    return counts


MAZE_ID_RE = re.compile(r"\b(?:train|heldout)_(?:trap|benign|phase_shift)_\d+\b", re.I)
COORD_RE = re.compile(r"(\(\s*\d+\s*,\s*\d+\s*\)|\b(?:row|column|col|cell|coordinate)\s*\(?\s*\d+)", re.I)
LONG_ACTION_RE = re.compile(
    r"\b(?:up|down|left|right|north|south|east|west|u|d|l|r)\b"
    r"(?:[\s,;>\-]+(?:up|down|left|right|north|south|east|west|u|d|l|r)\b){5,}",
    re.I,
)


def _leak_flags(text: str) -> list[str]:
    flags: list[str] = []
    if MAZE_ID_RE.search(text):
        flags.append("maze_id")
    if COORD_RE.search(text):
        flags.append("coordinate")
    if LONG_ACTION_RE.search(text):
        flags.append("long_action_sequence")
    return flags


def _source_summary(item: dict[str, Any]) -> dict[str, Any]:
    sources = item.get("sources") or []
    qualities = [src.get("quality") or {} for src in sources]
    if not qualities:
        return {
            "source_count": 0,
            "source_success_rate": "",
            "source_loop_rate": "",
            "source_mean_cost": "",
            "source_mean_stagnation": "",
        }
    return {
        "source_count": len(qualities),
        "source_success_rate": np.mean([1.0 if q.get("success") else 0.0 for q in qualities]),
        "source_loop_rate": np.mean([1.0 if q.get("looped") else 0.0 for q in qualities]),
        "source_mean_cost": np.mean([float(q.get("cost_ratio") or 0.0) for q in qualities]),
        "source_mean_stagnation": np.mean([float(q.get("stagnation_rate") or 0.0) for q in qualities]),
    }


def _collect_memory_rows(runs_dir: Path, seeds: list[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    leak_rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        for seed in seeds:
            result = _read_json(_result_path(runs_dir, condition, seed))
            audit = _read_json(_audit_path(runs_dir, condition, seed))
            final = _final_log(result)
            items = list(audit.get("memory_items", []))
            retrieval_counts = [int(item.get("retrieval_count", 0) or 0) for item in items]
            retrieved_items = [item for item in items if int(item.get("retrieval_count", 0) or 0) > 0]
            final_round_items = []
            for item in items:
                if any(int(hit.get("t", -1)) == int(final.get("t", 5)) for hit in item.get("retrieved_by", []) or []):
                    final_round_items.append(item)
            ops = _op_counts(audit.get("writes", []))
            summary_rows.append(
                {
                    "condition": condition,
                    "seed": seed,
                    "memory_mode": result.get("config", {}).get("memory_mode", ""),
                    "write_protocol": result.get("config", {}).get("memory_write_protocol", ""),
                    "final_success": final.get("success_rate", ""),
                    "final_success_excess_steps": final.get("success_excess_steps", ""),
                    "final_loop_rate": final.get("loop_rate", ""),
                    "final_stagnation_rate": final.get("stagnation_rate", ""),
                    "final_revisit_max": final.get("revisit_max", ""),
                    "final_memory_size": final.get("memory_size", len(items)),
                    "memory_items": len(items),
                    "retrieval_total": sum(retrieval_counts),
                    "retrieved_distinct": len(retrieved_items),
                    "final_round_retrieved_distinct": len(final_round_items),
                    "top1_retrieval_share": _top_share(retrieval_counts, 1),
                    "top3_retrieval_share": _top_share(retrieval_counts, 3),
                    "top5_retrieval_share": _top_share(retrieval_counts, 5),
                    "retrieval_entropy_norm": final.get("retrieval_entropy_norm", audit.get("retrieval_entropy_norm", "")),
                    "memory_effective_size": final.get("memory_effective_size", _effective_count(retrieval_counts)),
                    "writes": len(audit.get("writes", [])),
                    "op_ADD": ops.get("ADD", 0),
                    "op_EDIT": ops.get("EDIT", 0),
                    "op_UPVOTE": ops.get("UPVOTE", 0),
                    "op_DOWNVOTE": ops.get("DOWNVOTE", 0),
                    "op_append": ops.get("append", 0),
                    "op_agree": ops.get("agree", 0),
                    "sanitizer_reject_count": len(audit.get("sanitizer_rejects", [])),
                    "llm_error_count": int(audit.get("llm_error_count", 0) or 0),
                }
            )
            for rank, item in enumerate(sorted(items, key=lambda x: int(x.get("retrieval_count", 0) or 0), reverse=True)[:8], start=1):
                source = _source_summary(item)
                top_rows.append(
                    {
                        "condition": condition,
                        "seed": seed,
                        "rank": rank,
                        "kind": item.get("kind", ""),
                        "votes": item.get("votes", ""),
                        "retrieval_count": int(item.get("retrieval_count", 0) or 0),
                        **source,
                        "text": item.get("text", ""),
                    }
                )
            for item in items:
                text = str(item.get("text", ""))
                flags = _leak_flags(text)
                if flags:
                    leak_rows.append(
                        {
                            "condition": condition,
                            "seed": seed,
                            "flags": ",".join(flags),
                            "retrieval_count": int(item.get("retrieval_count", 0) or 0),
                            "text": text,
                        }
                    )
    return summary_rows, top_rows, leak_rows


def _mean(rows: list[dict[str, Any]], condition: str, key: str) -> float:
    vals = [float(row[key]) for row in rows if row["condition"] == condition and row.get(key) not in {"", None}]
    return float(np.mean(vals)) if vals else 0.0


def _sem(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return float(np.std(values, ddof=1) / math.sqrt(len(values)))


def _plot_figure2(stats_rows: list[dict[str, str]], out_base: Path) -> None:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )
    lookup = _stats_lookup(stats_rows)
    conditions = ["mas_nomem", "private", "shared_append", "shared_consolidated"]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.8), squeeze=False)
    for ax, (metric, title, unit) in zip(axes.ravel(), FIG_METRICS):
        y_positions = np.arange(len(conditions))
        for y, condition in zip(y_positions, conditions):
            row = lookup[(condition, metric)]
            mean = float(row["mean_diff"])
            lo = float(row["ci_lo"])
            hi = float(row["ci_hi"])
            ax.errorbar(
                mean,
                y,
                xerr=[[mean - lo], [hi - mean]],
                fmt="o",
                color=COLORS[condition],
                ecolor=COLORS[condition],
                capsize=2.5,
                markersize=4,
            )
        ax.axvline(0, color="#6F7378", linewidth=0.8, linestyle="--")
        ax.set_yticks(y_positions)
        ax.set_yticklabels([DISPLAY[c] for c in conditions])
        ax.invert_yaxis()
        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_xlabel(f"Mean difference vs frozen ({unit})")
        ax.grid(axis="x", color="#E7E9EC", linewidth=0.7)
    fig.suptitle("E2: active consolidated memory degrades efficiency and increases loops", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(out_base.with_suffix(f".{ext}"), dpi=600 if ext == "png" else None, bbox_inches="tight")
    plt.close(fig)


def _plot_figure3(summary_rows: list[dict[str, Any]], out_base: Path) -> None:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )
    panels = [
        ("memory_items", "Final memory pool size", "items"),
        ("retrieved_distinct", "Distinct memories injected", "items"),
        ("top1_retrieval_share", "Top-1 retrieval share", "share"),
    ]
    conditions = ["frozen", "private", "shared_append", "shared_consolidated"]
    fig, axes = plt.subplots(1, 3, figsize=(8.0, 2.7), squeeze=False)
    for ax, (key, title, ylabel) in zip(axes.ravel(), panels):
        xs = np.arange(len(conditions))
        means: list[float] = []
        sems: list[float] = []
        for condition in conditions:
            vals = [float(row[key]) for row in summary_rows if row["condition"] == condition]
            means.append(float(np.mean(vals)))
            sems.append(_sem(vals))
        ax.bar(xs, means, yerr=sems, color=[COLORS[c] for c in conditions], width=0.68, capsize=2.0)
        for x, condition in zip(xs, conditions):
            vals = [float(row[key]) for row in summary_rows if row["condition"] == condition]
            jitter = np.linspace(-0.12, 0.12, len(vals)) if len(vals) > 1 else [0.0]
            ax.scatter([x + j for j in jitter], vals, color="#222222", s=8, zorder=3, linewidths=0)
        ax.set_xticks(xs)
        ax.set_xticklabels([DISPLAY_SHORT[c] for c in conditions])
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontweight="bold")
        ax.grid(axis="y", color="#E7E9EC", linewidth=0.7)
    fig.suptitle("E2 mechanism audit: consolidation compresses the strategy supply", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    for ext in ("png", "pdf", "svg"):
        fig.savefig(out_base.with_suffix(f".{ext}"), dpi=600 if ext == "png" else None, bbox_inches="tight")
    plt.close(fig)


def _write_top_memories(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Top Retrieved Memories",
        "",
        "Sorted within each condition/seed by retrieval count. These are audit excerpts, not prompt recommendations.",
        "",
        "| condition | seed | rank | retrievals | votes | sources | source success | source loop | text |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        text = str(row["text"]).replace("|", "\\|")
        lines.append(
            "| {condition} | {seed} | {rank} | {retrieval_count} | {votes} | {source_count} | {source_success_rate} | {source_loop_rate} | {text} |".format(
                condition=row["condition"],
                seed=row["seed"],
                rank=row["rank"],
                retrieval_count=row["retrieval_count"],
                votes=row["votes"],
                source_count=row["source_count"],
                source_success_rate=_fmt(row["source_success_rate"]),
                source_loop_rate=_fmt(row["source_loop_rate"]),
                text=text,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_audit_findings(summary_rows: list[dict[str, Any]], leak_rows: list[dict[str, Any]], path: Path) -> None:
    def range_text(condition: str, key: str) -> str:
        vals = [float(row[key]) for row in summary_rows if row["condition"] == condition]
        return f"{min(vals):.1f}-{max(vals):.1f}" if vals else "n/a"

    append_distinct = _mean(summary_rows, "shared_append", "retrieved_distinct")
    cons_distinct = _mean(summary_rows, "shared_consolidated", "retrieved_distinct")
    compression = append_distinct / cons_distinct if cons_distinct else 0.0
    lines = [
        "# E2 Memory Audit Findings",
        "",
        "## Main Audit Result",
        "",
        "- `shared_consolidated` keeps much smaller final pools than `shared_append` while remaining actively injected.",
        f"- Mean distinct injected memories: append `{append_distinct:.1f}` vs consolidated `{cons_distinct:.1f}` (about `{compression:.2f}x` fewer distinct strategy items under consolidation).",
        f"- Final memory pool ranges: append `{range_text('shared_append', 'memory_items')}`, consolidated `{range_text('shared_consolidated', 'memory_items')}`.",
        f"- Final-round injected distinct ranges: append `{range_text('shared_append', 'final_round_retrieved_distinct')}`, consolidated `{range_text('shared_consolidated', 'final_round_retrieved_distinct')}`.",
        "",
        "## Claim Boundary",
        "",
        "- The audit uses cross-task and cross-round memory concentration only.",
        "- Same-task cross-agent retrieval convergence is not used as mechanism evidence because shared-memory queries are not agent-specific in this implementation.",
        "",
        "## Leakage Scan",
        "",
    ]
    if not leak_rows:
        lines.append("- No high-risk maze id, coordinate, or long fixed action-sequence leakage was detected in final memory texts.")
    else:
        lines.append(f"- High-risk candidates detected: `{len(leak_rows)}`. Review the table below before using these runs for claims.")
        lines.extend(["", "| condition | seed | flags | retrievals | text |", "|---|---:|---|---:|---|"])
        for row in leak_rows:
            text = str(row["text"]).replace("|", "\\|")
            lines.append(f"| {row['condition']} | {row['seed']} | {row['flags']} | {row['retrieval_count']} | {text} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _paired_per_seed_diff(
    runs_dir: Path, seeds: list[int], condition: str, baseline: str, metric: str, t: int = 5
) -> list[tuple[int, float]]:
    """Per-seed diff using the preregistered PAIRED method (same maze/agent), not a
    difference of unpaired per-seed means.

    Unpaired seed-mean diffs on success_excess_steps compare different task subsets
    (each arm's own successes), which can flip a sign when the harder mazes that one
    arm completes differ from the other's. The prereg (phase-beta S0) mandates the
    paired route-level bootstrap, so per-seed direction must be paired too.
    """
    diffs: list[tuple[int, float]] = []
    for seed in seeds:
        cond_rows = route_rows(
            _read_json(_result_path(runs_dir, condition, seed)), condition=condition, seed=str(seed)
        )
        base_rows = route_rows(
            _read_json(_result_path(runs_dir, baseline, seed)), condition=baseline, seed=str(seed)
        )
        stat = paired_diff(cond_rows, base_rows, metric, t=t, n_boot=1)
        if stat["n_pairs"] > 0:
            diffs.append((seed, stat["mean_diff"]))
    return diffs


def _write_verdict(
    stats_rows: list[dict[str, str]],
    stats_vs_private_rows: list[dict[str, str]],
    per_seed_diffs: list[tuple[int, float]],
    summary_rows: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    frozen = _stats_lookup(stats_rows)
    private = _stats_lookup(stats_vs_private_rows)
    sxs = frozen[("shared_consolidated", "success_excess_steps")]
    loop = frozen[("shared_consolidated", "looped")]
    stag = frozen[("shared_consolidated", "stagnation_rate")]
    revisit = frozen[("shared_consolidated", "revisit_max")]
    priv_frozen_sxs = frozen[("private", "success_excess_steps")]
    priv_frozen_loop = frozen[("private", "looped")]
    vs_priv_sxs = private[("shared_consolidated", "success_excess_steps")]
    vs_priv_loop = private[("shared_consolidated", "looped")]
    diffs = per_seed_diffs
    worse = sum(1 for _, value in diffs if value > 0)
    append_distinct = _mean(summary_rows, "shared_append", "retrieved_distinct")
    cons_distinct = _mean(summary_rows, "shared_consolidated", "retrieved_distinct")
    compression = append_distinct / cons_distinct if cons_distinct else 0.0
    lines = [
        "# E2 5-Seed Verdict",
        "",
        "## Frozen Claim",
        "",
        "E2 5-seed data support the preregistered degradation claim for `shared_consolidated` relative to `frozen` write-only memory.",
        "",
        "| metric | mean diff vs frozen | 95% CI | significant |",
        "|---|---:|---:|---|",
        f"| success_excess_steps | {_fmt(sxs['mean_diff'])} | [{_fmt(sxs['ci_lo'])}, {_fmt(sxs['ci_hi'])}] | {sxs['ci_excludes_zero']} |",
        f"| looped | {_fmt(loop['mean_diff'])} | [{_fmt(loop['ci_lo'])}, {_fmt(loop['ci_hi'])}] | {loop['ci_excludes_zero']} |",
        f"| stagnation_rate | {_fmt(stag['mean_diff'])} | [{_fmt(stag['ci_lo'])}, {_fmt(stag['ci_hi'])}] | {stag['ci_excludes_zero']} |",
        f"| revisit_max | {_fmt(revisit['mean_diff'])} | [{_fmt(revisit['ci_lo'])}, {_fmt(revisit['ci_hi'])}] | {revisit['ci_excludes_zero']} |",
        "",
        f"Per-seed `success_excess_steps` direction (paired, prereg method): `{worse}/5` seeds are "
        "worse than frozen: "
        + ", ".join(f"seed{seed} {value:+.2f}" for seed, value in diffs)
        + ".",
        "",
        "## Private Boundary",
        "",
        "`private` memory is also worse than frozen on the main endpoint "
        f"(sxs {_fmt(priv_frozen_sxs['mean_diff'])}, CI [{_fmt(priv_frozen_sxs['ci_lo'])}, {_fmt(priv_frozen_sxs['ci_hi'])}]; "
        f"looped {_fmt(priv_frozen_loop['mean_diff'])}, CI [{_fmt(priv_frozen_loop['ci_lo'])}, {_fmt(priv_frozen_loop['ci_hi'])}]). "
        "Thus the broad risk is active memory injection, while the shared-consolidated-specific evidence is narrower.",
        "",
        "The same data do not establish that `shared_consolidated` is broadly worse than `private` on the main efficiency endpoint.",
        "",
        "| metric | mean diff vs private | 95% CI | significant |",
        "|---|---:|---:|---|",
        f"| success_excess_steps | {_fmt(vs_priv_sxs['mean_diff'])} | [{_fmt(vs_priv_sxs['ci_lo'])}, {_fmt(vs_priv_sxs['ci_hi'])}] | {vs_priv_sxs['ci_excludes_zero']} |",
        f"| looped | {_fmt(vs_priv_loop['mean_diff'])} | [{_fmt(vs_priv_loop['ci_lo'])}, {_fmt(vs_priv_loop['ci_hi'])}] | {vs_priv_loop['ci_excludes_zero']} |",
        "",
        "## Mechanism Readout",
        "",
        f"`shared_consolidated` compresses active strategy supply: mean distinct injected memories are `{cons_distinct:.1f}` vs `{append_distinct:.1f}` for `shared_append` (`{compression:.2f}x` append/consolidated ratio).",
        "This supports a write-side consolidation account, not the E3 append-side lambda dose-response account.",
        "",
        "## Recommended Manuscript Wording",
        "",
        "> Active consolidated memory, compared with a write-only frozen control, significantly increases successful-route excess steps and loop signatures. The current E2 evidence does not show a broad shared-vs-private efficiency separation; shared-specific risk should be framed through loop amplification and write-side strategy-supply compression.",
    ]
    (out_dir / "e2_verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_inputs(runs_dir: Path, stats_dir: Path, stats_vs_private_dir: Path, seeds: list[int]) -> None:
    missing: list[str] = []
    for condition in CONDITIONS:
        for seed in seeds:
            for path in (_result_path(runs_dir, condition, seed), _audit_path(runs_dir, condition, seed)):
                if not path.exists():
                    missing.append(str(path))
    for path in (
        stats_dir / "paired_stats.csv",
        stats_dir / "per_seed.csv",
        stats_vs_private_dir / "paired_stats.csv",
    ):
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing E2 evidence inputs:\n" + "\n".join(missing))


def main() -> None:
    args = _parser().parse_args()
    runs_dir = Path(args.runs_dir)
    stats_dir = Path(args.stats_dir)
    stats_vs_private_dir = Path(args.stats_vs_private_dir)
    out_dir = Path(args.out_dir)
    seeds = [int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    _validate_inputs(runs_dir, stats_dir, stats_vs_private_dir, seeds)
    out_dir.mkdir(parents=True, exist_ok=True)

    stats_rows = _read_csv(stats_dir / "paired_stats.csv")
    stats_vs_private_rows = _read_csv(stats_vs_private_dir / "paired_stats.csv")
    per_seed_diffs = _paired_per_seed_diff(
        runs_dir, seeds, "shared_consolidated", "frozen", "success_excess_steps"
    )
    summary_rows, top_rows, leak_rows = _collect_memory_rows(runs_dir, seeds)

    _write_csv(summary_rows, out_dir / "memory_summary.csv")
    _write_csv(top_rows, out_dir / "top_retrieved_memories.csv")
    _write_csv(leak_rows, out_dir / "leakage_candidates.csv")
    _write_top_memories(top_rows, out_dir / "top_retrieved_memories.md")
    _write_audit_findings(summary_rows, leak_rows, out_dir / "memory_audit_findings.md")
    _write_verdict(stats_rows, stats_vs_private_rows, per_seed_diffs, summary_rows, out_dir)
    _plot_figure2(stats_rows, out_dir / "figure2_e2_main")
    _plot_figure3(summary_rows, out_dir / "figure3_write_side_compression")
    print(f"wrote {out_dir.resolve()}")


if __name__ == "__main__":
    main()
