from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .epsilon_evidence import PRIMARY_METRICS, SENSITIVITY_ARMS
from .miniwob_stats import P3_METRICS, PRIMARY_METRICS as P3_PRIMARY_METRICS


CONTROL_ORDER = [
    ("shared_consolidated_minus_private_consolidated", "Shared consol. $-$ private consol."),
    ("append_cap14_minus_shared_consolidated", "Cap-14 append $-$ shared consol."),
    ("mmr_minus_shared_consolidated", "MMR consol. $-$ standard consol."),
]
ZETA_CONTRAST = "zeta_exact_yoke_minus_epsilon_shared_consolidated"
SENSITIVITY_ORDER = [
    (f"{arm}_minus_epsilon_sens_reference", label)
    for arm, label in [
        ("epsilon_sens_k3", "$k=3$"),
        ("epsilon_sens_k10", "$k=10$"),
        ("epsilon_sens_cap40", "Pool cap $40$"),
        ("epsilon_sens_ops3", "Operation budget $3$"),
        ("epsilon_sens_ops9", "Operation budget $9$"),
        ("epsilon_sens_merge07", "Merge threshold $0.7$"),
        ("epsilon_sens_merge09", "Merge threshold $0.9$"),
        ("epsilon_sens_recency1", "Recency weight $1$"),
    ]
]
CONTROL_MACRO_PREFIXES = {
    "shared_consolidated_minus_private_consolidated": "SharedPrivate",
    "append_cap14_minus_shared_consolidated": "CapFourteenConsolidated",
    "mmr_minus_shared_consolidated": "MmrConsolidated",
}
SENSITIVITY_MACRO_PREFIXES = {
    f"{arm}_minus_epsilon_sens_reference": token
    for arm, token in [
        ("epsilon_sens_k3", "SensKThree"),
        ("epsilon_sens_k10", "SensKTen"),
        ("epsilon_sens_cap40", "SensCapForty"),
        ("epsilon_sens_ops3", "SensOpsThree"),
        ("epsilon_sens_ops9", "SensOpsNine"),
        ("epsilon_sens_merge07", "SensMergeZeroSeven"),
        ("epsilon_sens_merge09", "SensMergeZeroNine"),
        ("epsilon_sens_recency1", "SensRecencyOne"),
    ]
}
SENSITIVITY_TEXT_LABELS = {
    f"{arm}_minus_epsilon_sens_reference": label
    for arm, label in [
        ("epsilon_sens_k3", "k=3"),
        ("epsilon_sens_k10", "k=10"),
        ("epsilon_sens_cap40", "cap=40"),
        ("epsilon_sens_ops3", "operations=3"),
        ("epsilon_sens_ops9", "operations=9"),
        ("epsilon_sens_merge07", "merge=0.7"),
        ("epsilon_sens_merge09", "merge=0.9"),
        ("epsilon_sens_recency1", "recency=1"),
    ]
}
METRIC_MACRO_TOKENS = {
    "success": "Success",
    "success_excess_steps": "SuccessExcessSteps",
    "failure_penalized_steps": "FailurePenalizedSteps",
    "looped": "LoopRate",
    "stagnation_rate": "StagnationRate",
    "steps": "Steps",
    "failure_penalized_cost": "FailurePenalizedCost",
    "repeated_action_same_state": "RepeatedActionSameState",
    "nontermination": "Nontermination",
    "loop_stall_burden": "LoopStallBurden",
}
MAZE_METRIC_LABELS = {
    "success": "Success",
    "success_excess_steps": "Succ.-only excess",
    "failure_penalized_steps": "Failure-pen. steps",
    "looped": "Loop rate",
    "stagnation_rate": "Stagnation",
}
P3_METRIC_LABELS = {
    "success": "Success",
    "steps": "Steps",
    "failure_penalized_steps": "Failure-pen. steps",
    "failure_penalized_cost": "Failure-pen. cost",
    "repeated_action_same_state": "Repeated action",
    "nontermination": "Nontermination",
    "loop_stall_burden": "Loop/stall burden",
}
P3_FAMILY_LABELS = {
    "click-button": "Click",
    "choose-list": "Choose",
    "enter-text": "Enter",
    "click-checkboxes": "Checkbox",
    "login-user": "Login",
    "use-autocomplete-nodelay": "Autocomplete",
}
MEMORY_FIELDS = [
    "final_memory_size",
    "final_distinct_total_injected",
    "final_distinct_active_injected",
    "final_mean_injected_per_prompt",
    "retrieval_entropy_norm_final",
    "retrieval_top1_share_final",
    "retrieval_concentration_final",
]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row["contrast"]), str(row["metric"])): row
        for row in rows
        if "contrast" in row and "metric" in row
    }


def _p3_stat_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        metric: dict(value)
        for metric, value in report.get("paired_stats", {}).items()
    }


def _effect_index(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str, int], dict[str, Any]]:
    return {
        (str(row["contrast"]), str(row["metric"]), int(row["seed"])): row
        for row in rows
        if {"contrast", "metric", "seed"} <= set(row)
    }


def _ci_excludes_zero(row: dict[str, Any]) -> bool:
    lo = float(row["ci_lo"])
    hi = float(row["ci_hi"])
    return lo > 0.0 or hi < 0.0


def _latex_cell(row: dict[str, Any]) -> str:
    mean = float(row["mean_diff"])
    lo = float(row["ci_lo"])
    hi = float(row["ci_hi"])
    marker = "^{\\ast}" if _ci_excludes_zero(row) else ""
    return (
        "\\shortstack{"
        f"${mean:+.3f}{marker}$"
        "\\\\[-2pt]"
        f"{{\\scriptsize $[{lo:+.3f},{hi:+.3f}]$}}"
        "}"
    )


def _markdown_cell(row: dict[str, Any]) -> str:
    marker = "*" if _ci_excludes_zero(row) else ""
    return (
        f"{float(row['mean_diff']):+.4f}{marker} "
        f"[{float(row['ci_lo']):+.4f}, {float(row['ci_hi']):+.4f}]"
    )


def _require_stats(
    index: dict[tuple[str, str], dict[str, Any]],
    *,
    contrast: str,
    metrics: list[str],
) -> list[dict[str, Any]]:
    missing = [metric for metric in metrics if (contrast, metric) not in index]
    if missing:
        raise ValueError(f"Missing statistics for {contrast}: {missing}")
    return [index[(contrast, metric)] for metric in metrics]


def _require_p3_stats(
    index: dict[str, dict[str, Any]],
    *,
    metrics: list[str],
    intervention: str,
) -> list[dict[str, Any]]:
    missing = [metric for metric in metrics if metric not in index]
    if missing:
        raise ValueError(f"Missing P3 statistics for {intervention}: {missing}")
    return [index[metric] for metric in metrics]


def _render_maze_table(
    *,
    rows: list[tuple[str, list[dict[str, Any]]]],
    caption: str,
    label: str,
    terminal_t: int,
    seed_note: str,
) -> str:
    columns = "l" + "c" * len(PRIMARY_METRICS)
    lines = [
        "% Generated by sec.paper_results; do not transcribe values manually.",
        "\\begin{table*}[t]",
        "\\centering",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{3pt}",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{@{{}}{columns}@{{}}}}",
        "\\toprule",
        "Contrast & " + " & ".join(MAZE_METRIC_LABELS[metric] for metric in PRIMARY_METRICS) + " \\\\",
        "\\midrule",
    ]
    for label_text, stats in rows:
        lines.append(label_text + " & " + " & ".join(_latex_cell(row) for row in stats) + " \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\vspace{2pt}",
            "\\parbox{0.98\\textwidth}{\\scriptsize "
            "Cells are paired mean differences with seed-clustered 95\\% bootstrap CIs. "
            "$^\\ast$ indicates that the CI excludes zero. Positive success is better; "
            "positive cost, loop, and stagnation effects are worse. "
            f"Terminal round $t={terminal_t}$; {seed_note}. "
            "Intervals are endpoint-wise and not multiplicity-adjusted; they do not "
            "define a joint performance test.}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _render_p3_table(
    *,
    rows: list[tuple[str, list[dict[str, Any]]]],
    caption: str,
    family_effects: list[dict[str, Any]],
    decisions: dict[str, str],
    quality_status: str,
) -> str:
    family_index = {
        (str(row.get("family")), str(row.get("metric"))): row
        for row in family_effects
    }
    families = [
        family
        for family in P3_FAMILY_LABELS
        if (family, "failure_penalized_cost") in family_index
        and (family, "loop_stall_burden") in family_index
    ]

    def pair_count(stats: list[dict[str, Any]]) -> str:
        values = sorted({int(row.get("n_pairs", 0)) for row in stats})
        if not values:
            return "0"
        if len(values) == 1:
            return str(values[0])
        return f"{values[0]}--{values[-1]}"

    def decision_label(value: str) -> str:
        if value == "p3_phenomenon_pass":
            return "pass"
        if value == "p3_not_detected_or_underpowered":
            return "not detected/underpowered"
        return value.replace("_", " ")

    quality_label = {
        "quality_clear": "clear",
        "quality_warning_review_required": "warning/review required",
    }.get(quality_status, quality_status.replace("_", " "))
    columns = "l" + "c" * len(P3_METRICS)
    lines = [
        "% Generated by sec.paper_results; do not transcribe values manually.",
        "\\begin{table*}[t]",
        "\\centering",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{2.5pt}",
        f"\\caption{{{caption}}}",
        "\\label{tab:p3-boundary}",
        f"\\begin{{tabular}}{{@{{}}{columns}@{{}}}}",
        "\\toprule",
        "Contrast & " + " & ".join(P3_METRIC_LABELS[metric] for metric in P3_METRICS) + " \\\\",
        "\\midrule",
    ]
    for label_text, stats in rows:
        lines.append(label_text + " & " + " & ".join(_latex_cell(row) for row in stats) + " \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\vspace{3pt}",
            "\\begin{tabular}{@{}lrr@{}}",
            "\\toprule",
            "Consolidated family & $\\Delta$ failure cost & $\\Delta$ loop/stall \\\\",
            "\\midrule",
        ]
    )
    for family in families:
        cost = family_index.get((family, "failure_penalized_cost"), {})
        burden = family_index.get((family, "loop_stall_burden"), {})
        lines.append(
            f"{P3_FAMILY_LABELS.get(family, family)} & "
            f"${float(cost.get('mean_diff', 0.0)):+.4f}$ & "
            f"${float(burden.get('mean_diff', 0.0)):+.4f}$ \\\\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\vspace{2pt}",
            "\\parbox{0.98\\textwidth}{\\scriptsize "
            "Cells are equal-family paired mean differences with seed-clustered 95\\% "
            "bootstrap CIs at terminal $t=3$. $^\\ast$ indicates that the CI excludes zero. "
            f"Consolidated: {decision_label(decisions.get('consolidated', 'missing'))}, "
            f"quality {quality_label}, $n={pair_count(rows[0][1])}$ paired routes per endpoint; "
            f"append: {decision_label(decisions.get('append', 'missing'))}, "
            f"$n={pair_count(rows[1][1])}$. "
            "The six-family block is descriptive consolidated-minus-frozen heterogeneity, "
            "not six independent confirmatory tests. Only failure-penalized cost and "
            "loop/stall burden determine the preregistered consolidated gate; remaining "
            "intervals are endpoint-wise descriptive estimates.}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _macro_records(
    *,
    rows: list[dict[str, Any]],
    prefix_by_contrast: dict[str, str],
    source: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        contrast = str(row.get("contrast", ""))
        metric = str(row.get("metric", ""))
        if contrast not in prefix_by_contrast or metric not in METRIC_MACRO_TOKENS:
            continue
        base = "Rev" + prefix_by_contrast[contrast] + METRIC_MACRO_TOKENS[metric]
        values = {
            "Mean": f"{float(row['mean_diff']):+.4f}",
            "CILo": f"{float(row['ci_lo']):+.4f}",
            "CIHi": f"{float(row['ci_hi']):+.4f}",
            "CI": (
                f"[{float(row['ci_lo']):+.4f},"
                f"{float(row['ci_hi']):+.4f}]"
            ),
        }
        for field, value in values.items():
            records.append(
                {
                    "macro": base + field,
                    "source": source,
                    "contrast": contrast,
                    "metric": metric,
                    "field": field,
                    "value": value,
                }
            )
    return records


def _p3_macro_records(
    *,
    report: dict[str, Any],
    intervention_token: str,
    source: str,
) -> list[dict[str, Any]]:
    rows = []
    contrast = f"p3_{intervention_token.lower()}_minus_frozen"
    for metric, stat in report.get("paired_stats", {}).items():
        rows.append({"contrast": contrast, "metric": metric, **stat})
    return _macro_records(
        rows=rows,
        prefix_by_contrast={contrast: "PThree" + intervention_token},
        source=source,
    )


def _p3_seed_sign_records(
    *,
    report: dict[str, Any],
    intervention_token: str,
    source: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    contrast = f"p3_{intervention_token.lower()}_minus_frozen"
    checks = report.get("checks", {})
    for metric in P3_METRICS:
        if metric not in P3_PRIMARY_METRICS:
            continue
        summary = checks.get(f"{metric}_same_sign_seeds", {})
        diffs = {
            str(seed): float(value)
            for seed, value in summary.get("diffs", {}).items()
        }
        if set(diffs) != {"0", "1", "2"}:
            raise ValueError(
                f"Incomplete P3 seed directions for {intervention_token}/{metric}: "
                f"{sorted(diffs)}"
            )
        signs = [
            "+" if diffs[str(seed)] > 0.0 else "-" if diffs[str(seed)] < 0.0 else "0"
            for seed in range(3)
        ]
        records.append(
            {
                "macro": (
                    "RevPThree"
                    + intervention_token
                    + METRIC_MACRO_TOKENS[metric]
                    + "SeedSigns"
                ),
                "source": source,
                "contrast": contrast,
                "metric": metric,
                "field": "SeedSigns",
                "value": ",".join(signs),
            }
        )
    return records


def _sensitivity_loop_setting_records(
    *,
    report: dict[str, Any],
    source: str,
) -> list[dict[str, Any]]:
    index = _stat_index(report.get("stats", []))
    groups = {
        "PositiveDetectedSettings": [],
        "NegativeDetectedSettings": [],
        "NotDetectedSettings": [],
    }
    for contrast, _label in SENSITIVITY_ORDER:
        row = index.get((contrast, "looped"))
        if row is None:
            raise ValueError(f"Missing loop-rate sensitivity result for {contrast}.")
        lo = float(row["ci_lo"])
        hi = float(row["ci_hi"])
        if lo > 0.0:
            field = "PositiveDetectedSettings"
        elif hi < 0.0:
            field = "NegativeDetectedSettings"
        else:
            field = "NotDetectedSettings"
        groups[field].append(SENSITIVITY_TEXT_LABELS[contrast])
    return [
        {
            "macro": "RevSensitivityLoopRate" + field,
            "source": source,
            "contrast": "epsilon_sensitivity_envelope",
            "metric": "looped",
            "field": field,
            "value": ", ".join(labels) if labels else "none",
        }
        for field, labels in groups.items()
    ]


def _write_revision_macros(
    *,
    out_dir: Path,
    controls: dict[str, Any],
    sensitivity: dict[str, Any],
    zeta: dict[str, Any],
    zeta_evaluable: bool,
    p3_primary: dict[str, Any],
    p3_append: dict[str, Any],
    p3_quality_clear: bool,
    source_paths: dict[str, Path],
) -> list[dict[str, Any]]:
    records = _macro_records(
        rows=controls.get("stats", []),
        prefix_by_contrast=CONTROL_MACRO_PREFIXES,
        source=str(source_paths["epsilon_controls"]),
    )
    records.extend(
        _macro_records(
            rows=sensitivity.get("stats", []),
            prefix_by_contrast=SENSITIVITY_MACRO_PREFIXES,
            source=str(source_paths["epsilon_sensitivity"]),
        )
    )
    records.extend(
        _sensitivity_loop_setting_records(
            report=sensitivity,
            source=str(source_paths["epsilon_sensitivity"]),
        )
    )
    if zeta_evaluable:
        records.extend(
            _macro_records(
                rows=zeta.get("stats", []),
                prefix_by_contrast={
                    ZETA_CONTRAST: "ZetaConsolidated",
                },
                source=str(source_paths["zeta_exact_yoke"]),
            )
        )
    if p3_quality_clear:
        records.extend(
            _p3_macro_records(
                report=p3_primary,
                intervention_token="Consolidated",
                source=str(source_paths["p3_primary"]),
            )
        )
        records.extend(
            _p3_seed_sign_records(
                report=p3_primary,
                intervention_token="Consolidated",
                source=str(source_paths["p3_primary"]),
            )
        )
        records.extend(
            _p3_macro_records(
                report=p3_append,
                intervention_token="Append",
                source=str(source_paths["p3_append"]),
            )
        )
    macro_names = [record["macro"] for record in records]
    if len(macro_names) != len(set(macro_names)):
        raise ValueError("Generated revision macro names are not unique.")
    lines = [
        "% Generated by sec.paper_results; values map to macro_manifest.json.",
    ]
    lines.extend(
        f"\\newcommand{{\\{record['macro']}}}{{{record['value']}}}"
        for record in records
    )
    lines.append("")
    (out_dir / "revision_macros.tex").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    (out_dir / "macro_manifest.json").write_text(
        json.dumps(
            {
                "macro_count": len(records),
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return records


def _render_seed_effect_table(
    *,
    rows: list[tuple[str, str, list[float]]],
    seeds: list[int],
    caption: str,
    label: str,
) -> str:
    columns = "ll" + "r" * len(seeds)
    lines = [
        "% Generated by sec.paper_results; do not transcribe values manually.",
        "\\begin{table*}[p]",
        "\\centering",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{5pt}",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{@{{}}{columns}@{{}}}}",
        "\\toprule",
        "Contrast & Metric & " + " & ".join(f"Seed {seed}" for seed in seeds) + " \\\\",
        "\\midrule",
    ]
    previous = None
    for contrast, metric, values in rows:
        shown_contrast = contrast if contrast != previous else ""
        lines.append(
            f"{shown_contrast} & {metric} & "
            + " & ".join(f"${value:+.4f}$" for value in values)
            + " \\\\"
        )
        previous = contrast
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\vspace{2pt}",
            "\\parbox{0.96\\textwidth}{\\scriptsize "
            "Values are descriptive seed-level paired mean differences. Seeds are the "
            "outer resampling unit in pooled intervals and are not independent "
            "confirmatory replications.}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _seed_rows(
    *,
    effects: list[dict[str, Any]],
    contrasts: list[tuple[str, str]],
    metrics: list[str],
    metric_labels: dict[str, str],
    seeds: list[int],
) -> list[tuple[str, str, list[float]]]:
    index = _effect_index(effects)
    rows: list[tuple[str, str, list[float]]] = []
    for contrast, label in contrasts:
        for metric in metrics:
            keys = [(contrast, metric, seed) for seed in seeds]
            missing = [key for key in keys if key not in index]
            if missing:
                raise ValueError(f"Missing seed-level effects: {missing}")
            rows.append(
                (
                    label,
                    metric_labels[metric],
                    [float(index[key]["mean_diff"]) for key in keys],
                )
            )
    return rows


def _p3_seed_rows(
    reports: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, str, list[float]]]:
    rows: list[tuple[str, str, list[float]]] = []
    for label, report in reports:
        checks = report.get("checks", {})
        for metric in ["failure_penalized_cost", "loop_stall_burden"]:
            summary = checks.get(f"{metric}_same_sign_seeds", {})
            diffs = {str(seed): float(value) for seed, value in summary.get("diffs", {}).items()}
            if set(diffs) != {"0", "1", "2"}:
                raise ValueError(f"Missing P3 seed effects for {label}, {metric}")
            rows.append(
                (
                    label,
                    P3_METRIC_LABELS[metric],
                    [diffs[str(seed)] for seed in range(3)],
                )
            )
    return rows


def _render_p3_family_table(
    reports: list[tuple[str, dict[str, Any]]],
) -> str:
    families = list(P3_FAMILY_LABELS)
    lines = [
        "% Generated by sec.paper_results; do not transcribe values manually.",
        "\\begin{table*}[p]",
        "\\centering",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\caption{MiniWoB per-family paired mean differences at terminal $t=3$. "
        "Seeds are weighted equally within each family; these descriptive effects "
        "accompany the equal-family pooled intervals.}",
        "\\label{tab:p3-family-effects}",
        "\\begin{tabular}{@{}llrrrrrr@{}}",
        "\\toprule",
        "Contrast & Metric & "
        + " & ".join(P3_FAMILY_LABELS[family] for family in families)
        + " \\\\",
        "\\midrule",
    ]
    previous = None
    for label, report in reports:
        index = {
            (str(row.get("family")), str(row.get("metric"))): row
            for row in report.get("per_family_effects", [])
        }
        for metric in P3_METRICS:
            keys = [(family, metric) for family in families]
            missing = [key for key in keys if key not in index]
            if missing:
                raise ValueError(f"Missing P3 family effects for {label}: {missing}")
            shown_label = label if label != previous else ""
            lines.append(
                f"{shown_label} & {P3_METRIC_LABELS[metric]} & "
                + " & ".join(f"${float(index[key]['mean_diff']):+.4f}$" for key in keys)
                + " \\\\"
            )
            previous = label
        lines.append("\\addlinespace")
    lines[-1] = "\\bottomrule"
    lines.extend(["\\end{tabular}", "\\end{table*}", ""])
    return "\n".join(lines)


def _render_appendix_heterogeneity(
    *,
    controls: dict[str, Any],
    sensitivity: dict[str, Any],
    zeta: dict[str, Any],
    zeta_evaluable: bool,
    p3_primary: dict[str, Any],
    p3_append: dict[str, Any],
    p3_quality_clear: bool,
) -> str:
    control_contrasts = list(CONTROL_ORDER)
    if zeta_evaluable:
        control_contrasts.append(
            (ZETA_CONTRAST, "Exact-size append yoke $-$ shared consol.")
        )
    control_effects = list(controls.get("per_seed_effects", []))
    if zeta_evaluable:
        control_effects.extend(zeta.get("per_seed_effects", []))
    sections = [
        _render_seed_effect_table(
            rows=_seed_rows(
                effects=control_effects,
                contrasts=control_contrasts,
                metrics=PRIMARY_METRICS,
                metric_labels=MAZE_METRIC_LABELS,
                seeds=[0, 1, 2, 3, 4],
            ),
            seeds=[0, 1, 2, 3, 4],
            caption=(
                "Seed-level effects for the fresh mechanism controls. Zeta is included "
                "only if all exact-size manipulation checks pass."
            ),
            label="tab:epsilon-control-seeds",
        )
    ]
    for part, contrast_chunk in enumerate(
        [SENSITIVITY_ORDER[:4], SENSITIVITY_ORDER[4:]],
        start=1,
    ):
        sections.append(
            _render_seed_effect_table(
                rows=_seed_rows(
                    effects=sensitivity.get("per_seed_effects", []),
                    contrasts=contrast_chunk,
                    metrics=PRIMARY_METRICS,
                    metric_labels=MAZE_METRIC_LABELS,
                    seeds=[0, 1, 2],
                ),
                seeds=[0, 1, 2],
                caption=(
                    f"Seed-level effects for the prespecified Epsilon sensitivity "
                    f"envelope (part {part} of 2)."
                ),
                label=f"tab:epsilon-sensitivity-seeds-{part}",
            )
        )
    if p3_quality_clear:
        reports = [
            ("Consolidated $-$ frozen", p3_primary),
            ("Append $-$ frozen", p3_append),
        ]
        sections.extend(
            [
                _render_seed_effect_table(
                    rows=_p3_seed_rows(reports),
                    seeds=[0, 1, 2],
                    caption=(
                        "MiniWoB seed-level effects for the two preregistered primary "
                        "burden metrics."
                    ),
                    label="tab:p3-seed-effects",
                ),
                _render_p3_family_table(reports),
            ]
        )
    else:
        sections.append(
            "% MiniWoB heterogeneity tables withheld because formal data quality is not clear.\n"
        )
    return "\n".join(sections)


def _latex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _latex_hash(value: Any) -> str:
    text = str(value or "")
    if not text:
        return "--"
    chunks = [text[index : index + 8] for index in range(0, len(text), 8)]
    return "{\\scriptsize\\ttfamily " + "\\allowbreak{}".join(chunks) + "}"


def _aggregate_quality(report: dict[str, Any]) -> dict[str, int]:
    rows = list(report.get("data_quality", []))
    return {
        "runs": len(rows),
        "routes": sum(int(row.get("route_count_final", 0)) for row in rows),
        "expected": sum(int(row.get("expected_route_count_final", 0)) for row in rows),
        "api_errors": sum(int(row.get("llm_error_count", 0)) for row in rows),
        "retries": sum(int(row.get("llm_retry_count", 0)) for row in rows),
        "filter_hits": sum(int(row.get("content_filter_hits", 0)) for row in rows),
        "exhausted_calls": sum(
            int(row.get("exhausted_llm_call_count", 0)) for row in rows
        ),
        "route_llm_errors_all": sum(
            int(
                row.get(
                    "route_llm_error_count_all_rounds",
                    row.get("route_llm_error_count_final", 0),
                )
            )
            for row in rows
        ),
        "route_llm_errors_final": sum(
            int(row.get("route_llm_error_count_final", 0)) for row in rows
        ),
        "parse_failures_all": sum(
            int(
                row.get(
                    "parse_failure_count_all_rounds",
                    row.get("parse_failure_count_final", 0),
                )
            )
            for row in rows
        ),
        "parse_failures_final": sum(
            int(row.get("parse_failure_count_final", 0)) for row in rows
        ),
        "configurations": sum(bool(row.get("configuration_pass")) for row in rows),
        "manifests": sum(bool(row.get("manifest_pass")) for row in rows),
    }


def _render_quality_tables(
    *,
    controls: dict[str, Any],
    sensitivity: dict[str, Any],
    zeta: dict[str, Any],
    p3_primary: dict[str, Any],
    p3_append: dict[str, Any],
) -> str:
    lines = [
        "\\begin{table*}[t]",
        "\\centering",
        "\\tiny",
        "\\setlength{\\tabcolsep}{2.5pt}",
        "\\caption{Maze-suite data quality aggregated over completed formal runs. "
        "Routes reports observed/expected terminal routes. API failures are separated "
        "from route-level LLM and parse failures, each shown as all-round/terminal "
        "counts; Config and Manifest report validated runs/total runs.}",
        "\\label{tab:revision-maze-quality}",
        "\\begin{tabular}{@{}lrrrrrrrrrr@{}}",
        "\\toprule",
        "Suite & Runs & Routes & API err. & Retries & Filter & Exhausted & Route LLM all/final & Parse all/final "
        "& Config & Manifest \\\\",
        "\\midrule",
    ]
    for label, report in [
        ("Epsilon controls", controls),
        ("Epsilon sensitivity", sensitivity),
        ("Zeta exact yoke", zeta),
    ]:
        row = _aggregate_quality(report)
        lines.append(
            f"{label} & {row['runs']} & {row['routes']}/{row['expected']} & "
            f"{row['api_errors']} & {row['retries']} & {row['filter_hits']} & "
            f"{row['exhausted_calls']} & "
            f"{row['route_llm_errors_all']}/{row['route_llm_errors_final']} & "
            f"{row['parse_failures_all']}/{row['parse_failures_final']} & "
            f"{row['configurations']}/{row['runs']} & "
            f"{row['manifests']}/{row['runs']} \\\\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table*}",
            "",
            "\\begin{table*}[t]",
            "\\centering",
            "\\tiny",
            "\\setlength{\\tabcolsep}{2.2pt}",
            "\\caption{MiniWoB formal-quality summaries. Both contrast reports must "
            "carry an identical quality digest before behavioral interpretation. "
            "API counts are failed attempts/retries/content-filter hits/exhausted calls; "
            "route LLM errors are all-round/terminal counts. Non-HO exhausted calls "
            "cover training or reviewer contexts not represented by held-out routes. "
            "LLM path, Config, Manifest, and Env. are all-run validation gates.}",
            "\\label{tab:revision-p3-quality}",
            "\\begin{tabular}{@{}lcrrrrrccc@{}}",
            "\\toprule",
            "Report & Status & Runs & Routes & API e/r/f/x & Route LLM all/final "
            "& Non-HO x & Parse/Infra/Bid & LLM path & Config/Manifest/Env. \\\\",
            "\\midrule",
        ]
    )
    for label, report in [
        ("Consolidated primary", p3_primary),
        ("Append secondary", p3_append),
    ]:
        quality = report.get("formal_data_quality", {})
        aggregate = quality.get("aggregate", {})
        checks = quality.get("checks", {})
        quality_label = (
            "clear"
            if quality.get("status") == "quality_clear"
            else "warning"
        )
        lines.append(
            f"{label} & {quality_label} & "
            f"{int(aggregate.get('run_count', 0))} & "
            f"{int(aggregate.get('route_count', 0))} & "
            f"{int(aggregate.get('api_error_count', 0))}/"
            f"{int(aggregate.get('retry_count', 0))}/"
            f"{int(aggregate.get('content_filter_hits', 0))}/"
            f"{int(aggregate.get('exhausted_llm_call_count', 0))} & "
            f"{int(aggregate.get('route_llm_error_count_all_rounds', 0))}/"
            f"{int(aggregate.get('route_llm_error_count_final', 0))} & "
            f"{int(aggregate.get('nonheldout_exhausted_llm_call_count', 0))} & "
            f"{float(aggregate.get('parse_rate', 0.0)):.4f}/"
            f"{float(aggregate.get('infrastructure_error_route_rate', 0.0)):.4f}/"
            f"{float(aggregate.get('bid_error_rate', 0.0)):.4f} & "
            f"{'pass' if checks.get('all_llm_behavioral_paths') else 'fail'} & "
            f"{'pass' if checks.get('all_configurations') else 'fail'}/"
            f"{'pass' if checks.get('all_manifests') else 'fail'}/"
            f"{'pass' if checks.get('all_environments_consistent') else 'fail'} \\\\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _memory_mean_rows(
    reports: list[dict[str, Any]],
) -> list[tuple[str, dict[str, float], int]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        for row in report.get("memory_summary", []):
            grouped.setdefault(str(row.get("condition", "missing")), []).append(row)
    output: list[tuple[str, dict[str, float], int]] = []
    for condition in sorted(grouped):
        rows = grouped[condition]
        means = {
            field: sum(float(row.get(field, 0.0)) for row in rows) / len(rows)
            for field in MEMORY_FIELDS
        }
        output.append((condition, means, len(rows)))
    return output


def _render_memory_table(
    *,
    controls: dict[str, Any],
    sensitivity: dict[str, Any],
    zeta: dict[str, Any],
) -> str:
    lines = [
        "\\begin{table*}[t]",
        "\\centering",
        "\\tiny",
        "\\setlength{\\tabcolsep}{2.5pt}",
        "\\caption{Final-round memory and retrieval summaries, averaged over seeds. "
        "These are manipulation diagnostics and are not themselves behavioral outcomes.}",
        "\\label{tab:revision-memory-summary}",
        "\\begin{tabular}{@{}lrrrrrrrr@{}}",
        "\\toprule",
        "Condition & Seeds & Pool & Distinct total & Distinct active & Inj./prompt & "
        "Entropy & Top-1 & Concentration \\\\",
        "\\midrule",
    ]
    for condition, means, seeds in _memory_mean_rows([controls, sensitivity, zeta]):
        label = condition.removeprefix("epsilon_").removeprefix("zeta_")
        lines.append(
            f"{_latex_escape(label)} & {seeds} & "
            f"{means['final_memory_size']:.2f} & "
            f"{means['final_distinct_total_injected']:.2f} & "
            f"{means['final_distinct_active_injected']:.2f} & "
            f"{means['final_mean_injected_per_prompt']:.2f} & "
            f"{means['retrieval_entropy_norm_final']:.3f} & "
            f"{means['retrieval_top1_share_final']:.3f} & "
            f"{means['retrieval_concentration_final']:.3f} \\\\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _render_zeta_checks(zeta: dict[str, Any]) -> str:
    index = {
        (int(row.get("seed", -1)), int(row.get("t", -1))): row
        for row in zeta.get("manipulation_checks", [])
        if "seed" in row and "t" in row
    }
    lines = [
        "\\begin{table*}[t]",
        "\\centering",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\caption{All 30 exact supply-yoke manipulation checks. Each cell is "
        "target/budget/selected/retrieval-candidate range; a check passes only "
        "when all three observed supply counts equal the frozen target.}",
        "\\label{tab:zeta-yoke-checks}",
        "\\begin{tabular}{@{}lcccccc@{}}",
        "\\toprule",
        "Seed & $t=0$ & $t=1$ & $t=2$ & $t=3$ & $t=4$ & $t=5$ \\\\",
        "\\midrule",
    ]
    for seed in range(5):
        cells = []
        for t in range(6):
            row = index.get((seed, t), {})
            marker = "pass" if row.get("passed") else "fail"
            cells.append(
                f"{int(row.get('target', -1))}/"
                f"{int(row.get('budget', -1))}/"
                f"{int(row.get('selected', -1))}/"
                f"{int(row.get('retrieval_candidate_min', -1))}"
                f"--{int(row.get('retrieval_candidate_max', -1))} {marker}"
            )
        lines.append(f"{seed} & " + " & ".join(cells) + " \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _provenance_rows(
    *,
    controls: dict[str, Any],
    zeta: dict[str, Any],
    p3_primary: dict[str, Any],
) -> list[tuple[str, str, str, bool]]:
    rows: list[tuple[str, str, str, bool]] = []
    provenance = controls.get("provenance", {})
    prereg = provenance.get("preregistration", {})
    if prereg:
        rows.append(
            (
                "Epsilon preregistration",
                str(prereg.get("expected_sha256", "")),
                str(prereg.get("actual_sha256", "")),
                bool(prereg.get("match")),
            )
        )
    for source in provenance.get("runtime_source", {}).get("files", []):
        rows.append(
            (
                "Runtime: " + str(source.get("path", "")),
                str(source.get("expected_sha256", "")),
                str(source.get("actual_sha256", "")),
                bool(source.get("match")),
            )
        )
    schedule = zeta.get("schedule", {})
    schedule_prereg = schedule.get("preregistration", {})
    if schedule_prereg:
        rows.append(
            (
                "Zeta preregistration",
                str(schedule_prereg.get("expected_sha256", "")),
                str(schedule_prereg.get("actual_sha256", "")),
                bool(schedule_prereg.get("match")),
            )
        )
    if schedule.get("sha256"):
        rows.append(
            (
                "Zeta frozen schedule",
                str(schedule.get("sha256")),
                str(schedule.get("sha256")),
                True,
            )
        )
    for source in p3_primary.get("preregistration_provenance", {}).get("files", []):
        rows.append(
            (
                "MiniWoB: " + str(source.get("document", "")),
                str(source.get("expected_sha256", "")),
                str(source.get("actual_sha256", "")),
                bool(source.get("match")),
            )
        )
    for source in (
        p3_primary.get("preregistration_provenance", {})
        .get("runtime_source", {})
        .get("files", [])
    ):
        rows.append(
            (
                "MiniWoB runtime: " + str(source.get("path", "")),
                str(source.get("expected_sha256", "")),
                str(source.get("actual_sha256", "")),
                bool(source.get("match")),
            )
        )
    return rows


def _render_provenance_table(
    *,
    controls: dict[str, Any],
    zeta: dict[str, Any],
    p3_primary: dict[str, Any],
) -> str:
    rows = _provenance_rows(
        controls=controls,
        zeta=zeta,
        p3_primary=p3_primary,
    )
    lines = [
        "\\begin{table*}[t]",
        "\\centering",
        "\\tiny",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\caption{Frozen preregistration, schedule, and runtime-source provenance. "
        "The machine-readable manifests retain the same exact SHA-256 values.}",
        "\\label{tab:revision-provenance}",
        "\\begin{tabular}{@{}p{0.27\\textwidth}p{0.29\\textwidth}p{0.29\\textwidth}c@{}}",
        "\\toprule",
        "Artifact & Expected SHA-256 & Actual SHA-256 & Match \\\\",
        "\\midrule",
    ]
    if rows:
        for label, expected, actual, matched in rows:
            lines.append(
                f"{_latex_escape(label)} & {_latex_hash(expected)} & "
                f"{_latex_hash(actual)} & {'yes' if matched else 'no'} \\\\"
            )
    else:
        lines.append("No provenance records & -- & -- & no \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def _render_appendix_diagnostics(
    *,
    controls: dict[str, Any],
    sensitivity: dict[str, Any],
    zeta: dict[str, Any],
    p3_primary: dict[str, Any],
    p3_append: dict[str, Any],
) -> str:
    return "\n".join(
        [
            _render_zeta_checks(zeta),
            _render_memory_table(
                controls=controls,
                sensitivity=sensitivity,
                zeta=zeta,
            ),
            _render_quality_tables(
                controls=controls,
                sensitivity=sensitivity,
                zeta=zeta,
                p3_primary=p3_primary,
                p3_append=p3_append,
            ),
            _render_provenance_table(
                controls=controls,
                zeta=zeta,
                p3_primary=p3_primary,
            ),
        ]
    )


def _mean_memory(
    rows: list[dict[str, Any]],
    condition: str,
) -> dict[str, float]:
    selected = [row for row in rows if row.get("condition") == condition]
    if not selected:
        raise ValueError(f"Missing memory summary for {condition}")
    return {
        field: sum(float(row.get(field, 0.0)) for row in selected) / len(selected)
        for field in MEMORY_FIELDS
    }


def _memory_delta(
    rows: list[dict[str, Any]],
    *,
    intervention: str,
    baseline: str,
) -> dict[str, Any]:
    intervention_mean = _mean_memory(rows, intervention)
    baseline_mean = _mean_memory(rows, baseline)
    return {
        "intervention": intervention,
        "baseline": baseline,
        "intervention_mean": intervention_mean,
        "baseline_mean": baseline_mean,
        "difference": {
            field: intervention_mean[field] - baseline_mean[field]
            for field in MEMORY_FIELDS
        },
    }


def _write_markdown_summary(
    *,
    path: Path,
    mechanism_rows: list[tuple[str, list[dict[str, Any]]]],
    sensitivity_rows: list[tuple[str, list[dict[str, Any]]]],
    p3_rows: list[tuple[str, list[dict[str, Any]]]],
    zeta_decision: str,
    zeta_checks: tuple[int, int],
    p3_quality: str,
    p3_decisions: dict[str, str],
) -> None:
    lines = [
        "# Generated Revision Results",
        "",
        "This file is generated from frozen evidence artifacts. Asterisks mark CIs "
        "that exclude zero; they do not combine endpoints into a single claim.",
        "",
        "## Mechanism-Separating Controls",
        "",
        "| contrast | " + " | ".join(MAZE_METRIC_LABELS[metric] for metric in PRIMARY_METRICS) + " |",
        "|---|" + "|".join("---:" for _ in PRIMARY_METRICS) + "|",
    ]
    for label, stats in mechanism_rows:
        lines.append(f"| {label} | " + " | ".join(_markdown_cell(row) for row in stats) + " |")
    lines.extend(
        [
            "",
            f"Zeta decision: **{zeta_decision}**; exact-size checks: "
            f"**{zeta_checks[0]}/{zeta_checks[1]}**.",
            "",
            "## Sensitivity Envelope",
            "",
            "| setting | " + " | ".join(MAZE_METRIC_LABELS[metric] for metric in PRIMARY_METRICS) + " |",
            "|---|" + "|".join("---:" for _ in PRIMARY_METRICS) + "|",
        ]
    )
    for label, stats in sensitivity_rows:
        lines.append(f"| {label} | " + " | ".join(_markdown_cell(row) for row in stats) + " |")
    lines.extend(
        [
            "",
            "## MiniWoB Boundary",
            "",
            f"Formal quality: **{p3_quality}**.",
            f"Primary decision: **{p3_decisions['consolidated']}**.",
            f"Append secondary decision: **{p3_decisions['append']}**.",
            "",
        ]
    )
    if p3_rows:
        lines.extend(
            [
                "| contrast | " + " | ".join(P3_METRIC_LABELS[metric] for metric in P3_METRICS) + " |",
                "|---|" + "|".join("---:" for _ in P3_METRICS) + "|",
            ]
        )
        for label, stats in p3_rows:
            lines.append(f"| {label} | " + " | ".join(_markdown_cell(row) for row in stats) + " |")
    else:
        lines.append("Behavioral estimates are withheld because formal quality is not clear.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_paper_results(
    *,
    revision_gate_path: Path,
    controls_path: Path,
    sensitivity_path: Path,
    zeta_path: Path,
    p3_primary_path: Path,
    p3_append_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    inputs = {
        "revision_gate": revision_gate_path,
        "epsilon_controls": controls_path,
        "epsilon_sensitivity": sensitivity_path,
        "zeta_exact_yoke": zeta_path,
        "p3_primary": p3_primary_path,
        "p3_append": p3_append_path,
    }
    loaded = {name: _load_json(path) for name, path in inputs.items()}
    gate = loaded["revision_gate"]
    if gate.get("status") != "ready_for_paper_revision":
        raise RuntimeError("Unified evidence gate is not ready for paper revision.")

    controls = loaded["epsilon_controls"]
    sensitivity = loaded["epsilon_sensitivity"]
    zeta = loaded["zeta_exact_yoke"]
    p3_primary = loaded["p3_primary"]
    p3_append = loaded["p3_append"]

    control_index = _stat_index(controls.get("stats", []))
    mechanism_rows = [
        (label, _require_stats(control_index, contrast=contrast, metrics=PRIMARY_METRICS))
        for contrast, label in CONTROL_ORDER
    ]
    zeta_checks = zeta.get("manipulation_checks", [])
    zeta_passed = sum(1 for row in zeta_checks if row.get("passed"))
    zeta_decision = str(zeta.get("decision", "missing"))
    zeta_evaluable = (
        zeta_decision == "zeta_supply_yoke_evaluable"
        and len(zeta_checks) == 30
        and zeta_passed == 30
    )
    if zeta_evaluable:
        zeta_index = _stat_index(zeta.get("stats", []))
        mechanism_rows.append(
            (
                "Exact-size append yoke $-$ shared consol.",
                _require_stats(zeta_index, contrast=ZETA_CONTRAST, metrics=PRIMARY_METRICS),
            )
        )

    sensitivity_index = _stat_index(sensitivity.get("stats", []))
    expected_sensitivity_contrasts = {
        f"{arm}_minus_epsilon_sens_reference"
        for arm in SENSITIVITY_ARMS
        if arm != "epsilon_sens_reference"
    }
    actual_sensitivity_contrasts = {
        contrast for contrast, _metric in sensitivity_index
    }
    if actual_sensitivity_contrasts != expected_sensitivity_contrasts:
        raise ValueError(
            "Sensitivity contrasts do not match the frozen suite: "
            f"expected {sorted(expected_sensitivity_contrasts)}, "
            f"found {sorted(actual_sensitivity_contrasts)}"
        )
    sensitivity_rows = [
        (label, _require_stats(sensitivity_index, contrast=contrast, metrics=PRIMARY_METRICS))
        for contrast, label in SENSITIVITY_ORDER
    ]

    primary_quality = str(p3_primary.get("formal_data_quality", {}).get("status", "missing"))
    append_quality = str(p3_append.get("formal_data_quality", {}).get("status", "missing"))
    p3_quality_clear = primary_quality == "quality_clear" and append_quality == "quality_clear"
    p3_quality = primary_quality if primary_quality == append_quality else f"{primary_quality}/{append_quality}"
    p3_rows: list[tuple[str, list[dict[str, Any]]]] = []
    if p3_quality_clear:
        p3_rows = [
            (
                "Consolidated $-$ frozen",
                _require_p3_stats(
                    _p3_stat_index(p3_primary),
                    metrics=P3_METRICS,
                    intervention="consolidated",
                ),
            ),
            (
                "Append $-$ frozen",
                _require_p3_stats(
                    _p3_stat_index(p3_append),
                    metrics=P3_METRICS,
                    intervention="append",
                ),
            ),
        ]

    memory_rows = controls.get("memory_summary", [])
    intervention_checks = {
        "mmr_vs_standard_consolidated": _memory_delta(
            memory_rows,
            intervention="epsilon_shared_consolidated_mmr",
            baseline="epsilon_shared_consolidated",
        ),
        "cap14_vs_standard_consolidated": _memory_delta(
            memory_rows,
            intervention="epsilon_shared_append_cap14",
            baseline="epsilon_shared_consolidated",
        ),
        "zeta": {
            "decision": zeta_decision,
            "evaluable": zeta_evaluable,
            "passed_checks": zeta_passed,
            "total_checks": len(zeta_checks),
        },
    }
    p3_decisions = {
        "consolidated": str(p3_primary.get("decision", "missing")),
        "append": str(p3_append.get("decision", "missing")),
    }
    source_hashes = {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in inputs.items()
    }
    result = {
        "status": "paper_results_generated",
        "source_hashes": source_hashes,
        "gates": {
            "revision_evidence": gate.get("status"),
            "zeta_evaluable": zeta_evaluable,
            "p3_quality_clear": p3_quality_clear,
        },
        "intervention_checks": intervention_checks,
        "p3": {
            "quality_status": p3_quality,
            "decisions": p3_decisions,
            "primary_checks": p3_primary.get("checks", {}),
            "append_checks": p3_append.get("checks", {}),
            "primary_per_family_effects": p3_primary.get("per_family_effects", []),
            "append_per_family_effects": p3_append.get("per_family_effects", []),
        },
        "heterogeneity": {
            "epsilon_controls": controls.get("per_seed_effects", []),
            "epsilon_sensitivity": sensitivity.get("per_seed_effects", []),
            "zeta": zeta.get("per_seed_effects", []) if zeta_evaluable else [],
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mechanism_controls.tex").write_text(
        _render_maze_table(
            rows=mechanism_rows,
            caption=(
                "Fresh mechanism-separating controls at the terminal maze round. "
                "Rows retain their explicit subtraction direction; Zeta appears only "
                "after all exact-size manipulation checks pass."
            ),
            label="tab:epsilon-controls",
            terminal_t=int(controls.get("final_t", 5)),
            seed_note="five seeds per contrast",
        ),
        encoding="utf-8",
    )
    (out_dir / "sensitivity_envelope.tex").write_text(
        _render_maze_table(
            rows=sensitivity_rows,
            caption=(
                "Prespecified sensitivity envelope relative to the Epsilon reference "
                "configuration. All settings are reported without selecting a best point."
            ),
            label="tab:epsilon-sensitivity",
            terminal_t=int(sensitivity.get("final_t", 5)),
            seed_note="three seeds per contrast",
        ),
        encoding="utf-8",
    )
    if p3_rows:
        p3_tex = _render_p3_table(
            rows=p3_rows,
            caption=(
                "MiniWoB task-family boundary. Seeds are weighted equally within "
                "each task family and task families are weighted equally; "
                "the consolidated contrast is primary, append is secondary, and the "
                "compact family block exposes primary-contrast heterogeneity."
            ),
            family_effects=p3_primary.get("per_family_effects", []),
            decisions=p3_decisions,
            quality_status=p3_quality,
        )
    else:
        p3_tex = (
            "% Generated by sec.paper_results.\n"
            "% MiniWoB behavioral estimates withheld: formal data quality is not clear.\n"
        )
    (out_dir / "miniwob_boundary.tex").write_text(p3_tex, encoding="utf-8")
    (out_dir / "appendix_heterogeneity.tex").write_text(
        _render_appendix_heterogeneity(
            controls=controls,
            sensitivity=sensitivity,
            zeta=zeta,
            zeta_evaluable=zeta_evaluable,
            p3_primary=p3_primary,
            p3_append=p3_append,
            p3_quality_clear=p3_quality_clear,
        ),
        encoding="utf-8",
    )
    (out_dir / "appendix_diagnostics.tex").write_text(
        _render_appendix_diagnostics(
            controls=controls,
            sensitivity=sensitivity,
            zeta=zeta,
            p3_primary=p3_primary,
            p3_append=p3_append,
        ),
        encoding="utf-8",
    )
    macro_records = _write_revision_macros(
        out_dir=out_dir,
        controls=controls,
        sensitivity=sensitivity,
        zeta=zeta,
        zeta_evaluable=zeta_evaluable,
        p3_primary=p3_primary,
        p3_append=p3_append,
        p3_quality_clear=p3_quality_clear,
        source_paths=inputs,
    )
    result["revision_macro_count"] = len(macro_records)
    _write_markdown_summary(
        path=out_dir / "revision_results.md",
        mechanism_rows=mechanism_rows,
        sensitivity_rows=sensitivity_rows,
        p3_rows=p3_rows,
        zeta_decision=zeta_decision,
        zeta_checks=(zeta_passed, len(zeta_checks)),
        p3_quality=p3_quality,
        p3_decisions=p3_decisions,
    )
    generated_paths = [
        out_dir / "mechanism_controls.tex",
        out_dir / "sensitivity_envelope.tex",
        out_dir / "miniwob_boundary.tex",
        out_dir / "appendix_heterogeneity.tex",
        out_dir / "appendix_diagnostics.tex",
        out_dir / "revision_results.md",
        out_dir / "revision_macros.tex",
        out_dir / "macro_manifest.json",
    ]
    result["generated_hashes"] = {
        path.name: {"path": str(path), "sha256": _sha256(path)}
        for path in generated_paths
    }
    (out_dir / "paper_results_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate paper-ready tables directly from the complete revision evidence."
    )
    parser.add_argument(
        "--revision-gate",
        default="runs_revision_evidence/revision_evidence.json",
    )
    parser.add_argument(
        "--controls",
        default="runs_maze_epsilon_controls_stats/evidence_manifest.json",
    )
    parser.add_argument(
        "--sensitivity",
        default="runs_maze_epsilon_sensitivity_stats/evidence_manifest.json",
    )
    parser.add_argument(
        "--zeta",
        default="runs_maze_zeta_exact_yoke_stats/evidence_manifest.json",
    )
    parser.add_argument(
        "--p3-primary",
        default="runs_miniwob_gamma_p3e_stats/p3_gate_report.json",
    )
    parser.add_argument(
        "--p3-append",
        default="runs_miniwob_gamma_p3e_stats/append_secondary/p3_gate_report.json",
    )
    parser.add_argument(
        "--out-dir",
        default="paper_draft/generated/revision_results",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_paper_results(
        revision_gate_path=Path(args.revision_gate),
        controls_path=Path(args.controls),
        sensitivity_path=Path(args.sensitivity),
        zeta_path=Path(args.zeta),
        p3_primary_path=Path(args.p3_primary),
        p3_append_path=Path(args.p3_append),
        out_dir=Path(args.out_dir),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
