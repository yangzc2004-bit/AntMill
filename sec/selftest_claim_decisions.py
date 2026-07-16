from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .epsilon_evidence import PRIMARY_METRICS, SENSITIVITY_ARMS
from .claim_decisions import build_claim_decisions


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _stat(contrast: str, metric: str, mean: float, lo: float, hi: float) -> dict:
    return {
        "contrast": contrast,
        "metric": metric,
        "mean_diff": mean,
        "ci_lo": lo,
        "ci_hi": hi,
    }


def _controls() -> dict:
    stats = []
    for contrast in [
        "shared_consolidated_minus_private_consolidated",
        "append_cap14_minus_shared_consolidated",
        "mmr_minus_shared_consolidated",
    ]:
        for metric in PRIMARY_METRICS:
            if contrast == "shared_consolidated_minus_private_consolidated" and metric == "looped":
                stats.append(_stat(contrast, metric, 0.05, 0.01, 0.09))
            elif contrast == "mmr_minus_shared_consolidated" and metric == "looped":
                stats.append(_stat(contrast, metric, -0.04, -0.08, -0.01))
            else:
                stats.append(_stat(contrast, metric, 0.0, -0.02, 0.02))
    memory = []
    for seed in range(5):
        standard = {
            "condition": "epsilon_shared_consolidated",
            "seed": seed,
            "final_distinct_active_injected": 10,
            "final_distinct_total_injected": 12,
            "retrieval_entropy_norm_final": 0.7,
            "retrieval_top1_share_final": 0.3,
            "retrieval_concentration_final": 0.4,
        }
        mmr = {
            "condition": "epsilon_shared_consolidated_mmr",
            "seed": seed,
            "final_distinct_active_injected": 12,
            "final_distinct_total_injected": 14,
            "retrieval_entropy_norm_final": 0.8,
            "retrieval_top1_share_final": 0.2,
            "retrieval_concentration_final": 0.3,
        }
        memory.extend([standard, mmr])
    return {"stats": stats, "memory_summary": memory}


def _sensitivity() -> dict:
    stats = []
    for arm in SENSITIVITY_ARMS:
        if arm == "epsilon_sens_reference":
            continue
        contrast = f"{arm}_minus_epsilon_sens_reference"
        for metric in PRIMARY_METRICS:
            stats.append(_stat(contrast, metric, 0.0, -0.02, 0.02))
    return {"stats": stats}


def _zeta() -> dict:
    contrast = "zeta_exact_yoke_minus_epsilon_shared_consolidated"
    return {
        "decision": "zeta_supply_yoke_evaluable",
        "stats": [
            (
                _stat(contrast, metric, 0.04, 0.01, 0.07)
                if metric == "looped"
                else _stat(contrast, metric, 0.0, -0.02, 0.02)
            )
            for metric in PRIMARY_METRICS
        ],
    }


def _p3(intervention: str) -> dict:
    return {
        "intervention": intervention,
        "decision": "p3_phenomenon_pass" if intervention == "consolidated" else "p3_not_detected_or_underpowered",
        "formal_data_quality": {"status": "quality_clear"},
    }


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="antmill-claim-decisions-") as raw:
        root = Path(raw)
        paths = {
            "gate": root / "gate.json",
            "controls": root / "controls.json",
            "sensitivity": root / "sensitivity.json",
            "zeta": root / "zeta.json",
            "primary": root / "primary.json",
            "append": root / "append.json",
        }
        _write(paths["gate"], {"status": "ready_for_paper_revision"})
        _write(paths["controls"], _controls())
        _write(paths["sensitivity"], _sensitivity())
        _write(paths["zeta"], _zeta())
        _write(paths["primary"], _p3("consolidated"))
        _write(paths["append"], _p3("append"))
        result = build_claim_decisions(
            revision_gate_path=paths["gate"],
            controls_path=paths["controls"],
            sensitivity_path=paths["sensitivity"],
            zeta_path=paths["zeta"],
            p3_primary_path=paths["primary"],
            p3_append_path=paths["append"],
            rules_document_path=repo / "CLAIM_DECISION_RULES.md",
            rules_freeze_path=repo / "CLAIM_DECISION_RULES.freeze.json",
            out_dir=root / "out",
        )
        assert result["status"] == "claim_decisions_ready"
        assert (
            result["shared_vs_private"]["endpoints"]["looped"]["classification"]
            == "positive_detected"
        )
        assert (
            "associated with added loop burden"
            in result["shared_vs_private"]["allowed_statement"]
        )
        assert (
            "does not identify sharing alone"
            in result["shared_vs_private"]["allowed_statement"]
        )
        assert result["mmr_vs_consolidated"]["manipulation"]["status"] == "direction_observed"
        assert result["mmr_vs_consolidated"]["endpoint_specific_mitigation_allowed"] == ["looped"]
        assert (
            result["zeta_exact_yoke"]["interpretation"]
            == "candidate_pool_size_alone_insufficient_for_loop_separation"
        )
        assert result["p3"]["interpretation"] == "scoped_six_family_replication"
        assert result["sensitivity"]["loop_rate_setting_groups"] == {
            "positive_detected": [],
            "negative_detected": [],
            "not_detected": [
                "k=3",
                "k=10",
                "cap=40",
                "operations=3",
                "operations=9",
                "merge=0.7",
                "merge=0.9",
                "recency=1",
            ],
        }
        assert any(
            "eight prespecified sensitivity settings" in claim
            and "not detected for k=3" in claim
            for claim in result["allowed_claims"]
        )
        assert any(
            "equal-family pooled" in claim
            and "not uniform replication" in claim
            for claim in result["allowed_claims"]
        )
        assert any(
            "not uniform replication across every task family" in caveat
            for caveat in result["required_caveats"]
        )
        assert any(
            "not an established cause" in caveat
            for caveat in result["required_caveats"]
        )
        assert any(
            "reviewer-call allocation" in caveat
            and "does not identify sharing alone" in caveat
            for caveat in result["required_caveats"]
        )
        assert "cap-14 is an exact pool-size control" in result["disallowed_claims"]
        assert (
            "shared-versus-private identifies sharing alone"
            in result["disallowed_claims"]
        )
        assert (root / "out" / "claim_decisions.json").exists()
        assert (root / "out" / "claim_decisions.md").exists()

        warning_primary = _p3("consolidated")
        warning_append = _p3("append")
        for report in [warning_primary, warning_append]:
            report["decision"] = (
                "p3_not_behaviorally_interpretable_quality_warning"
            )
            report["formal_data_quality"]["status"] = (
                "quality_warning_review_required"
            )
        _write(paths["primary"], warning_primary)
        _write(paths["append"], warning_append)
        warning_result = build_claim_decisions(
            revision_gate_path=paths["gate"],
            controls_path=paths["controls"],
            sensitivity_path=paths["sensitivity"],
            zeta_path=paths["zeta"],
            p3_primary_path=paths["primary"],
            p3_append_path=paths["append"],
            rules_document_path=repo / "CLAIM_DECISION_RULES.md",
            rules_freeze_path=repo / "CLAIM_DECISION_RULES.freeze.json",
            out_dir=root / "warning-out",
        )
        assert (
            warning_result["p3"]["interpretation"]
            == "not_behaviorally_interpretable_quality_warning"
        )
        assert any(
            "not behaviorally interpretable" in claim
            for claim in warning_result["allowed_claims"]
        )
        assert not any(
            "six-family MiniWoB evaluation" in claim
            for claim in warning_result["allowed_claims"]
        )
    print("selftest_claim_decisions OK")


if __name__ == "__main__":
    main()
