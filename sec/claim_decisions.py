from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .epsilon_evidence import PRIMARY_METRICS, SENSITIVITY_ARMS


HARM_METRICS = {
    "success_excess_steps",
    "failure_penalized_steps",
    "looped",
    "stagnation_rate",
}
MMR_DIAGNOSTICS = {
    "final_distinct_active_injected": 1.0,
    "final_distinct_total_injected": 1.0,
    "retrieval_entropy_norm_final": 1.0,
    "retrieval_top1_share_final": -1.0,
    "retrieval_concentration_final": -1.0,
}
SENSITIVITY_LABELS = {
    "epsilon_sens_k3_minus_epsilon_sens_reference": "k=3",
    "epsilon_sens_k10_minus_epsilon_sens_reference": "k=10",
    "epsilon_sens_cap40_minus_epsilon_sens_reference": "cap=40",
    "epsilon_sens_ops3_minus_epsilon_sens_reference": "operations=3",
    "epsilon_sens_ops9_minus_epsilon_sens_reference": "operations=9",
    "epsilon_sens_merge07_minus_epsilon_sens_reference": "merge=0.7",
    "epsilon_sens_merge09_minus_epsilon_sens_reference": "merge=0.9",
    "epsilon_sens_recency1_minus_epsilon_sens_reference": "recency=1",
}


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


def _verify_rules(document_path: Path, freeze_path: Path) -> dict[str, Any]:
    freeze = _load_json(freeze_path)
    expected_path = Path(str(freeze.get("document", "")))
    expected_resolved = (
        expected_path.resolve()
        if expected_path.is_absolute()
        else (freeze_path.parent / expected_path).resolve()
    )
    document_resolved = document_path.resolve()
    expected = str(freeze.get("sha256", ""))
    actual = _sha256(document_path)
    return {
        "document": str(document_resolved),
        "freeze": str(freeze_path),
        "freeze_document": str(expected_resolved),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "match": expected_resolved == document_resolved and bool(expected) and actual == expected,
    }


def _ci_class(row: dict[str, Any]) -> str:
    lo = float(row["ci_lo"])
    hi = float(row["ci_hi"])
    if lo > 0.0:
        return "positive_detected"
    if hi < 0.0:
        return "negative_detected"
    return "not_detected"


def _endpoint_decision(row: dict[str, Any]) -> dict[str, Any]:
    metric = str(row["metric"])
    classification = _ci_class(row)
    improvement_class = (
        "negative_detected" if metric in HARM_METRICS else "positive_detected"
    )
    worsening_class = (
        "positive_detected" if metric in HARM_METRICS else "negative_detected"
    )
    return {
        "metric": metric,
        "mean_diff": float(row["mean_diff"]),
        "ci_lo": float(row["ci_lo"]),
        "ci_hi": float(row["ci_hi"]),
        "classification": classification,
        "improvement_detected": classification == improvement_class,
        "worsening_detected": classification == worsening_class,
    }


def _stats_index(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(row["contrast"]), str(row["metric"])): row
        for row in report.get("stats", [])
    }


def _contrast_decisions(
    index: dict[tuple[str, str], dict[str, Any]],
    contrast: str,
) -> dict[str, dict[str, Any]]:
    missing = [
        metric for metric in PRIMARY_METRICS if (contrast, metric) not in index
    ]
    if missing:
        raise ValueError(f"Missing contrast metrics for {contrast}: {missing}")
    return {
        metric: _endpoint_decision(index[(contrast, metric)])
        for metric in PRIMARY_METRICS
    }


def _memory_by_seed(
    rows: list[dict[str, Any]],
    condition: str,
) -> dict[int, dict[str, Any]]:
    selected = {
        int(row["seed"]): row
        for row in rows
        if row.get("condition") == condition
    }
    if set(selected) != {0, 1, 2, 3, 4}:
        raise ValueError(f"Incomplete memory summary for {condition}")
    return selected


def _mmr_manipulation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mmr = _memory_by_seed(rows, "epsilon_shared_consolidated_mmr")
    standard = _memory_by_seed(rows, "epsilon_shared_consolidated")
    diagnostics: dict[str, Any] = {}
    supported: list[str] = []
    for field, intended_sign in MMR_DIAGNOSTICS.items():
        diffs = {
            str(seed): float(mmr[seed].get(field, 0.0))
            - float(standard[seed].get(field, 0.0))
            for seed in range(5)
        }
        signed = {seed: intended_sign * value for seed, value in diffs.items()}
        mean_diff = sum(diffs.values()) / len(diffs)
        mean_signed = intended_sign * mean_diff
        direction_count = sum(1 for value in signed.values() if value > 0.0)
        direction_supported = mean_signed > 0.0 and direction_count >= 3
        if direction_supported:
            supported.append(field)
        diagnostics[field] = {
            "intended_direction": "increase" if intended_sign > 0 else "decrease",
            "mean_diff": mean_diff,
            "seed_diffs": diffs,
            "intended_direction_seed_count": direction_count,
            "direction_supported": direction_supported,
        }
    status = "direction_observed" if supported else "direction_not_observed"
    return {
        "status": status,
        "supported_diagnostics": supported,
        "diagnostics": diagnostics,
        "classification_note": (
            "descriptive direction check; not a significance test"
        ),
    }


def _source_hashes(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in paths.items()
    }


def build_claim_decisions(
    *,
    revision_gate_path: Path,
    controls_path: Path,
    sensitivity_path: Path,
    zeta_path: Path,
    p3_primary_path: Path,
    p3_append_path: Path,
    rules_document_path: Path,
    rules_freeze_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    paths = {
        "revision_gate": revision_gate_path,
        "epsilon_controls": controls_path,
        "epsilon_sensitivity": sensitivity_path,
        "zeta_exact_yoke": zeta_path,
        "p3_primary": p3_primary_path,
        "p3_append": p3_append_path,
        "claim_rules": rules_document_path,
        "claim_rules_freeze": rules_freeze_path,
    }
    loaded = {
        name: _load_json(path)
        for name, path in paths.items()
        if name not in {"claim_rules"}
    }
    gate = loaded["revision_gate"]
    if gate.get("status") != "ready_for_paper_revision":
        raise RuntimeError("Unified evidence gate is not ready.")
    rules = _verify_rules(rules_document_path, rules_freeze_path)
    if not rules["match"]:
        raise RuntimeError("Frozen claim-decision rules do not match.")

    controls = loaded["epsilon_controls"]
    sensitivity = loaded["epsilon_sensitivity"]
    zeta = loaded["zeta_exact_yoke"]
    p3_primary = loaded["p3_primary"]
    p3_append = loaded["p3_append"]

    controls_index = _stats_index(controls)
    shared_private = _contrast_decisions(
        controls_index,
        "shared_consolidated_minus_private_consolidated",
    )
    cap14 = _contrast_decisions(
        controls_index,
        "append_cap14_minus_shared_consolidated",
    )
    mmr_behavior = _contrast_decisions(
        controls_index,
        "mmr_minus_shared_consolidated",
    )
    mmr_manipulation = _mmr_manipulation(controls.get("memory_summary", []))
    mmr_improved_endpoints = [
        metric
        for metric, decision in mmr_behavior.items()
        if decision["improvement_detected"]
    ]
    mmr_mitigation_endpoints = (
        mmr_improved_endpoints
        if mmr_manipulation["status"] == "direction_observed"
        else []
    )

    zeta_decision = str(zeta.get("decision", "missing"))
    zeta_endpoints: dict[str, dict[str, Any]] = {}
    if zeta_decision == "zeta_supply_yoke_evaluable":
        zeta_index = _stats_index(zeta)
        zeta_endpoints = _contrast_decisions(
            zeta_index,
            "zeta_exact_yoke_minus_epsilon_shared_consolidated",
        )
    zeta_loop = zeta_endpoints.get("looped")
    if not zeta_loop:
        zeta_interpretation = "not_evaluable"
    elif zeta_loop["classification"] == "not_detected":
        zeta_interpretation = "candidate_supply_size_remains_plausible"
    else:
        zeta_interpretation = "candidate_pool_size_alone_insufficient_for_loop_separation"

    sensitivity_index = _stats_index(sensitivity)
    sensitivity_decisions: dict[str, Any] = {}
    for arm in SENSITIVITY_ARMS:
        if arm == "epsilon_sens_reference":
            continue
        contrast = f"{arm}_minus_epsilon_sens_reference"
        sensitivity_decisions[contrast] = _contrast_decisions(
            sensitivity_index,
            contrast,
        )
    sensitivity_loop_groups = {
        "positive_detected": [],
        "negative_detected": [],
        "not_detected": [],
    }
    for contrast, decisions in sensitivity_decisions.items():
        classification = str(decisions["looped"]["classification"])
        sensitivity_loop_groups[classification].append(
            SENSITIVITY_LABELS[contrast]
        )

    p3_quality = str(
        p3_primary.get("formal_data_quality", {}).get("status", "missing")
    )
    p3_decision = str(p3_primary.get("decision", "missing"))
    if p3_quality != "quality_clear":
        p3_interpretation = "not_behaviorally_interpretable_quality_warning"
    elif p3_decision == "p3_phenomenon_pass":
        p3_interpretation = "scoped_six_family_replication"
    else:
        p3_interpretation = "not_detected_under_frozen_design"

    loop_class = shared_private["looped"]["classification"]
    if loop_class == "positive_detected":
        sharing_claim = (
            "The tested shared joint-reviewer consolidation protocol is associated "
            "with added loop burden relative to the per-agent-consolidated protocol. "
            "Because reviewer-call allocation, prompt composition, and operation "
            "opportunity differ, this protocol-level contrast does not identify "
            "sharing alone."
        )
    elif loop_class == "negative_detected":
        sharing_claim = (
            "The tested shared joint-reviewer consolidation protocol has lower loop "
            "burden than the per-agent-consolidated protocol. Because reviewer-call "
            "allocation, prompt composition, and operation opportunity differ, this "
            "protocol-level contrast does not identify sharing alone."
        )
    else:
        sharing_claim = (
            "The fresh study does not isolate a shared-specific loop effect; reviewer-"
            "call allocation, prompt composition, and operation opportunity differ "
            "between the tested shared and per-agent protocols."
        )

    allowed_claims = [sharing_claim]
    if mmr_mitigation_endpoints:
        allowed_claims.append(
            "The tested MMR intervention changes diversity diagnostics in the "
            "intended direction and improves only these detected endpoints: "
            + ", ".join(mmr_mitigation_endpoints)
            + "."
        )
    elif mmr_manipulation["status"] == "direction_not_observed":
        allowed_claims.append(
            "The tested MMR arm does not establish its intended diversity "
            "manipulation, so its behavior cannot judge diversity-aware retrieval generally."
        )
    else:
        allowed_claims.append(
            "The tested MMR arm changes at least one diversity diagnostic, but "
            "no endpoint-specific mitigation with an excluding-zero CI is detected."
        )
    if zeta_interpretation == "candidate_pool_size_alone_insufficient_for_loop_separation":
        allowed_claims.append(
            "The exact-size yoke remains separated on loop rate, so candidate-pool "
            "size alone is insufficient for that separation."
        )
    elif zeta_interpretation == "candidate_supply_size_remains_plausible":
        allowed_claims.append(
            "The exact-size yoke does not detect a loop separation, leaving "
            "candidate-supply size plausible."
        )
    else:
        allowed_claims.append(
            "The exact-size yoke is not behaviorally evaluable."
        )
    if p3_interpretation == "scoped_six_family_replication":
        allowed_claims.append(
            "In the six-family MiniWoB evaluation, the equal-family pooled "
            "failure-penalized-cost and loop/stall-burden gate passes; this is "
            "not uniform replication in every task family."
        )
    elif p3_interpretation == "not_detected_under_frozen_design":
        allowed_claims.append(
            "Task-family replication is not detected under the frozen MiniWoB "
            "design and sample size."
        )
    else:
        allowed_claims.append(
            "The MiniWoB formal evaluation is not behaviorally interpretable "
            "because its quality status is not clear."
        )
    allowed_claims.append(
        "Across the eight prespecified sensitivity settings, loop rate relative "
        "to the shared-consolidated reference is higher with excluding-zero "
        "intervals for "
        + (", ".join(sensitivity_loop_groups["positive_detected"]) or "none")
        + "; lower for "
        + (", ".join(sensitivity_loop_groups["negative_detected"]) or "none")
        + "; and not detected for "
        + (", ".join(sensitivity_loop_groups["not_detected"]) or "none")
        + ". This is a descriptive envelope, not best-setting selection."
    )

    result = {
        "status": "claim_decisions_ready",
        "rules_provenance": rules,
        "source_hashes": _source_hashes(paths),
        "shared_vs_private": {
            "endpoints": shared_private,
            "allowed_statement": sharing_claim,
        },
        "cap14_vs_consolidated": {
            "endpoints": cap14,
            "scope": "fixed terminal-capacity control only",
        },
        "mmr_vs_consolidated": {
            "manipulation": mmr_manipulation,
            "behavioral_endpoints": mmr_behavior,
            "endpoint_specific_mitigation_allowed": mmr_mitigation_endpoints,
        },
        "zeta_exact_yoke": {
            "decision": zeta_decision,
            "interpretation": zeta_interpretation,
            "endpoints": zeta_endpoints,
        },
        "sensitivity": {
            "scope": "descriptive envelope; no best-setting selection",
            "contrasts": sensitivity_decisions,
            "loop_rate_setting_groups": sensitivity_loop_groups,
        },
        "p3": {
            "quality_status": p3_quality,
            "primary_decision": p3_decision,
            "append_secondary_decision": p3_append.get("decision", "missing"),
            "interpretation": p3_interpretation,
        },
        "allowed_claims": allowed_claims,
        "required_caveats": [
            "Every endpoint is interpreted separately.",
            "Cap-14 is not an exact round-by-round pool-size control.",
            "Equal candidate-pool size does not equal equal item content or write dynamics.",
            "MMR does not identify write-side compression as causal.",
            "Strategy-supply compression remains a correlate or candidate channel, not an established cause.",
            "Sensitivity settings are all reported and no best setting is selected.",
            "Per-seed and per-family heterogeneity accompanies pooled estimates.",
            "A MiniWoB pooled pass is not uniform replication across every task family.",
            "The shared-versus-private contrast does not identify sharing alone because reviewer-call allocation, prompt composition, and operation opportunity differ.",
        ],
        "disallowed_claims": [
            "shared memory fails",
            "consensus consolidation is generally harmful",
            "strategy compression causes looping",
            "strategy-supply compression drives looping",
            "cap-14 is an exact pool-size control",
            "sensitivity identifies the best setting",
            "MiniWoB replication is uniform across task families",
            "generalizes to web agents",
            "shared-versus-private identifies sharing alone",
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "claim_decisions.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Frozen Claim Decisions",
        "",
        f"Status: **{result['status']}**",
        "",
        "## Allowed Claims",
        "",
    ]
    lines.extend(f"- {claim}" for claim in allowed_claims)
    lines.extend(["", "## Required Caveats", ""])
    lines.extend(f"- {claim}" for claim in result["required_caveats"])
    lines.extend(["", "## Disallowed Claims", ""])
    lines.extend(f"- {claim}" for claim in result["disallowed_claims"])
    lines.extend(
        [
            "",
            "## Branch Summary",
            "",
            f"- shared-versus-private loop: `{loop_class}`",
            f"- MMR manipulation: `{mmr_manipulation['status']}`",
            f"- Zeta: `{zeta_interpretation}`",
            f"- MiniWoB P3: `{p3_interpretation}`",
            "",
        ]
    )
    (out_dir / "claim_decisions.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply frozen outcome-to-claim rules to the complete revision evidence."
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
    parser.add_argument("--rules", default="CLAIM_DECISION_RULES.md")
    parser.add_argument(
        "--rules-freeze",
        default="CLAIM_DECISION_RULES.freeze.json",
    )
    parser.add_argument(
        "--out-dir",
        default="paper_draft/generated/revision_results",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_claim_decisions(
        revision_gate_path=Path(args.revision_gate),
        controls_path=Path(args.controls),
        sensitivity_path=Path(args.sensitivity),
        zeta_path=Path(args.zeta),
        p3_primary_path=Path(args.p3_primary),
        p3_append_path=Path(args.p3_append),
        rules_document_path=Path(args.rules),
        rules_freeze_path=Path(args.rules_freeze),
        out_dir=Path(args.out_dir),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
