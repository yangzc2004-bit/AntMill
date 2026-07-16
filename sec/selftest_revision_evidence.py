from __future__ import annotations

import json
import hashlib
import tempfile
from pathlib import Path

from .epsilon_evidence import CONTROL_ARMS, CONTROL_CONTRASTS, SENSITIVITY_ARMS
from .maze_stats import PAIRED_METRICS
from .miniwob_stats import P3_METRICS, PRIMARY_METRICS as P3_PRIMARY_METRICS
from .revision_evidence import P3_CONDITIONS, P3_FAMILIES, build_revision_evidence


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _source_result(
    root: Path,
    *,
    condition: str,
    seed: int,
    family: str | None = None,
) -> dict:
    suffix = f"_{family}" if family else ""
    path = root / "sources" / f"{condition}_{seed}{suffix}.json"
    _write(
        path,
        {
            "condition": condition,
            "seed": seed,
            "family": family,
        },
    )
    return {
        "condition": condition,
        "seed": seed,
        **({"family": family} if family else {}),
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _source_manifest(
    root: Path,
    *,
    condition: str,
    seed: int,
    family: str | None = None,
) -> dict:
    suffix = f"_{family}" if family else ""
    path = root / "manifests" / f"{condition}_{seed}{suffix}.json"
    _write(
        path,
        {
            "condition": condition,
            "seed": seed,
            "family": family,
            "kind": "manifest",
        },
    )
    return {
        "condition": condition,
        "seed": seed,
        **({"family": family} if family else {}),
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _epsilon(*, suite: str, root: Path) -> dict:
    if suite == "controls":
        seeds = [0, 1, 2, 3, 4]
        contrasts = CONTROL_CONTRASTS
        arms = CONTROL_ARMS
    else:
        seeds = [0, 1, 2]
        contrasts = [
            (f"{arm}_minus_epsilon_sens_reference", arm, "epsilon_sens_reference")
            for arm in SENSITIVITY_ARMS
            if arm != "epsilon_sens_reference"
        ]
        arms = SENSITIVITY_ARMS
    stats = [
        {
            "contrast": contrast,
            "metric": metric,
            "t": 5,
            "analysis_method": "seed_clustered_paired_bootstrap",
            "n_pairs": len(seeds) * 48,
            "n_dropped": 0,
            "n_seeds": len(seeds),
        }
        for contrast, _intervention, _baseline in contrasts
        for metric in PAIRED_METRICS
    ]
    effects = [
        {
            "contrast": contrast,
            "metric": metric,
            "seed": seed,
            "t": 5,
            "n_pairs": 48,
        }
        for contrast, _intervention, _baseline in contrasts
        for metric in PAIRED_METRICS
        for seed in seeds
    ]
    return {
        "suite": suite,
        "seeds": seeds,
        "final_t": 5,
        "contrasts": contrasts,
        "analysis_method": "seed_clustered_paired_bootstrap",
        "stats": stats,
        "per_seed_effects": effects,
        "data_quality": [
            {
                "condition": arm,
                "seed": seed,
                "route_count_pass": True,
                "terminal_t": 5,
                "expected_terminal_t": 5,
                "terminal_round_pass": True,
                "configuration_pass": True,
                "manifest_pass": True,
            }
            for arm in arms
            for seed in seeds
        ],
        "memory_summary": [
            {"condition": arm, "seed": seed}
            for arm in arms
            for seed in seeds
        ],
        "source_results": [
            _source_result(root, condition=arm, seed=seed)
            for arm in arms
            for seed in seeds
        ],
        "source_manifests": [
            _source_manifest(root, condition=arm, seed=seed)
            for arm in arms
            for seed in seeds
        ],
        "provenance": {
            "preregistration": {"match": True},
            "runtime_source": {"all_match": True},
        },
    }


def _p3(*, intervention: str, root: Path) -> dict:
    return {
        "kind": "p3",
        "intervention": intervention,
        "baseline": "frozen",
        "t": 3,
        "decision": "p3_not_detected_or_underpowered",
        "paired_stats": {
            metric: {
                "metric": metric,
                "n_pairs": 864,
                "n_dropped": 0,
            }
            for metric in P3_METRICS
        },
        "per_family_effects": [
            {
                "family": family,
                "metric": metric,
                "n_pairs": 144,
                "n_dropped": 0,
            }
            for family in P3_FAMILIES
            for metric in P3_METRICS
        ],
        "checks": {
            f"{metric}_same_sign_seeds": {
                "n": 3,
                "diffs": {"0": 0.0, "1": 0.0, "2": 0.0},
            }
            for metric in P3_PRIMARY_METRICS
        },
        "formal_data_quality": {
            "status": "quality_clear",
            "aggregate": {"run_count": 54, "route_count": 10_368},
            "checks": {
                "complete_matrix": True,
                "all_route_counts": True,
                "all_parse_rates": True,
                "all_llm_behavioral_paths": True,
                "all_infrastructure_error_rates": True,
                "all_bid_error_rates": True,
                "all_reviewer_summary_schemas": True,
                "all_configurations": True,
                "all_manifests": True,
                "all_environments_consistent": True,
            },
            "runs": [
                {
                    "condition": condition,
                    "seed": str(seed),
                    "family": family,
                    "configuration_pass": True,
                    "manifest_pass": True,
                }
                for condition in P3_CONDITIONS
                for seed in range(3)
                for family in P3_FAMILIES
            ],
        },
        "preregistration_provenance": {
            "all_match": True,
            "runtime_source": {"all_match": True},
        },
        "source_results": [
            _source_result(root, condition=condition, seed=seed, family=family)
            for condition in P3_CONDITIONS
            for seed in range(3)
            for family in P3_FAMILIES
        ],
        "source_manifests": [
            _source_manifest(root, condition=condition, seed=seed, family=family)
            for condition in P3_CONDITIONS
            for seed in range(3)
            for family in P3_FAMILIES
        ],
    }


def _zeta(*, root: Path) -> dict:
    conditions = (
        "epsilon_shared_consolidated",
        "zeta_shared_append_exact_yoke",
    )
    schedule_path = root / "zeta_schedule.json"
    _write(
        schedule_path,
        {
            "phase": "zeta_exact_supply_yoke",
            "schedule_name": "gamma_consolidated_active_cummax",
        },
    )
    return {
        "suite": "zeta_exact_supply_yoke",
        "decision": "zeta_supply_yoke_evaluable",
        "seeds": [0, 1, 2, 3, 4],
        "final_t": 5,
        "analysis_method": "seed_clustered_paired_bootstrap",
        "stats": [
            {
                "metric": metric,
                "t": 5,
                "analysis_method": "seed_clustered_paired_bootstrap",
                "n_pairs": 240,
                "n_dropped": 0,
                "n_seeds": 5,
            }
            for metric in PAIRED_METRICS
        ],
        "per_seed_effects": [
            {
                "metric": metric,
                "seed": seed,
                "t": 5,
                "n_pairs": 48,
            }
            for metric in PAIRED_METRICS
            for seed in range(5)
        ],
        "manipulation_checks": [
            {
                "seed": seed,
                "t": t,
                "target": 4,
                "budget": 4,
                "selected": 4,
                "retrieval_record_count": 48,
                "retrieval_candidate_min": 4,
                "retrieval_candidate_max": 4,
                "budget_match": True,
                "selected_match": True,
                "retrieval_candidate_match": True,
                "passed": True,
            }
            for seed in range(5)
            for t in range(6)
        ],
        "data_quality": [
            {
                "condition": condition,
                "seed": seed,
                "route_count_pass": True,
                "terminal_t": 5,
                "expected_terminal_t": 5,
                "terminal_round_pass": True,
                "configuration_pass": True,
                "manifest_pass": True,
            }
            for condition in conditions
            for seed in range(5)
        ],
        "memory_summary": [
            {"condition": condition, "seed": seed}
            for condition in conditions
            for seed in range(5)
        ],
        "source_results": [
            _source_result(root, condition=condition, seed=seed)
            for condition in conditions
            for seed in range(5)
        ],
        "source_manifests": [
            _source_manifest(root, condition=condition, seed=seed)
            for condition in conditions
            for seed in range(5)
        ],
        "schedule": {
            "path": str(schedule_path),
            "sha256": hashlib.sha256(schedule_path.read_bytes()).hexdigest(),
            "preregistration": {"match": True},
            "phase": "zeta_exact_supply_yoke",
            "schedule_name": "gamma_consolidated_active_cummax",
            "source_arm": "epsilon_shared_consolidated",
            "target_definition": "active_pool_size at the matching evaluation round",
            "source_count": 5,
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-revision-evidence-") as raw:
        root = Path(raw)
        controls = root / "controls.json"
        sensitivity = root / "sensitivity.json"
        zeta = root / "zeta.json"
        primary = root / "primary.json"
        append = root / "append.json"
        _write(controls, _epsilon(suite="controls", root=root))
        _write(sensitivity, _epsilon(suite="sensitivity", root=root))
        _write(zeta, _zeta(root=root))
        _write(primary, _p3(intervention="consolidated", root=root))
        _write(append, _p3(intervention="append", root=root))
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "out",
        )
        assert result["status"] == "ready_for_paper_revision", result
        assert result["p3_quality_clear"]
        assert result["p3_reports_same_quality"]
        assert (root / "out" / "revision_evidence.json").exists()
        assert (root / "out" / "revision_evidence.md").exists()

        early_controls = _epsilon(suite="controls", root=root)
        early_controls["final_t"] = 4
        for row in early_controls["data_quality"]:
            row["terminal_t"] = 4
            row["terminal_round_pass"] = False
        _write(controls, early_controls)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "early-controls",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["epsilon_controls"]["checks"]["terminal_round"]
        _write(controls, _epsilon(suite="controls", root=root))

        controls_with_sources = _epsilon(suite="controls", root=root)
        _write(controls, controls_with_sources)
        raw_source = Path(controls_with_sources["source_results"][0]["path"])
        raw_source.write_text("tampered", encoding="utf-8")
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "tampered-source",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["epsilon_controls"]["checks"]["source_result_hashes"]
        _write(controls, _epsilon(suite="controls", root=root))

        controls_with_manifests = _epsilon(suite="controls", root=root)
        _write(controls, controls_with_manifests)
        raw_manifest = Path(controls_with_manifests["source_manifests"][0]["path"])
        raw_manifest.write_text("tampered", encoding="utf-8")
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "tampered-manifest",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["epsilon_controls"]["checks"][
            "source_manifest_hashes"
        ]
        _write(controls, _epsilon(suite="controls", root=root))

        broken_controls = _epsilon(suite="controls", root=root)
        broken_controls["memory_summary"][-1] = dict(broken_controls["memory_summary"][0])
        _write(controls, broken_controls)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-controls",
        )
        assert result["status"] == "evidence_incomplete"
        assert result["sections"]["epsilon_controls"]["status"] == "incomplete_or_invalid"
        _write(controls, _epsilon(suite="controls", root=root))

        broken_pairing = _epsilon(suite="controls", root=root)
        broken_pairing["stats"][0]["n_pairs"] = 239
        _write(controls, broken_pairing)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-control-pairing",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["epsilon_controls"]["checks"][
            "stats_pairing_complete"
        ]
        _write(controls, _epsilon(suite="controls", root=root))

        broken_primary = _p3(intervention="consolidated", root=root)
        broken_primary["per_family_effects"][-1] = dict(broken_primary["per_family_effects"][0])
        _write(primary, broken_primary)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-p3",
        )
        assert result["status"] == "evidence_incomplete"
        assert result["sections"]["p3_primary"]["status"] == "incomplete_or_invalid"
        _write(primary, _p3(intervention="consolidated", root=root))

        broken_p3_pairing = _p3(intervention="consolidated", root=root)
        broken_p3_pairing["paired_stats"][P3_METRICS[0]]["n_pairs"] = 0
        _write(primary, broken_p3_pairing)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-p3-pairing",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["p3_primary"]["checks"][
            "paired_route_coverage"
        ]
        _write(primary, _p3(intervention="consolidated", root=root))

        broken_p3_manifest = _p3(intervention="consolidated", root=root)
        p3_manifest_path = Path(broken_p3_manifest["source_manifests"][0]["path"])
        p3_manifest_path.write_text("tampered", encoding="utf-8")
        _write(primary, broken_p3_manifest)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-p3-manifest",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["p3_primary"]["checks"][
            "source_manifest_hashes"
        ]
        _write(primary, _p3(intervention="consolidated", root=root))

        broken_zeta = _zeta(root=root)
        broken_zeta["manipulation_checks"][0][
            "retrieval_candidate_max"
        ] = 5
        _write(zeta, broken_zeta)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-zeta",
        )
        assert result["status"] == "evidence_incomplete"
        assert result["sections"]["zeta_exact_supply_yoke"]["status"] == "incomplete_or_invalid"
        assert not result["sections"]["zeta_exact_supply_yoke"]["checks"][
            "retrieval_candidate_supply_audited"
        ]

        nonevaluable_zeta = _zeta(root=root)
        nonevaluable_zeta["manipulation_checks"][0][
            "retrieval_candidate_max"
        ] = 5
        nonevaluable_zeta["manipulation_checks"][0][
            "retrieval_candidate_match"
        ] = False
        nonevaluable_zeta["manipulation_checks"][0]["passed"] = False
        nonevaluable_zeta["decision"] = "zeta_supply_yoke_not_evaluable"
        _write(zeta, nonevaluable_zeta)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "nonevaluable-zeta",
        )
        assert result["status"] == "ready_for_paper_revision"
        assert result["sections"]["zeta_exact_supply_yoke"]["status"] == "complete"
        assert result["sections"]["zeta_exact_supply_yoke"]["checks"][
            "retrieval_candidate_supply_audited"
        ]

        broken_zeta_pairing = _zeta(root=root)
        broken_zeta_pairing["stats"][0]["n_pairs"] = 239
        _write(zeta, broken_zeta_pairing)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-zeta-pairing",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["zeta_exact_supply_yoke"]["checks"][
            "stats_pairing_complete"
        ]

        broken_zeta_config = _zeta(root=root)
        broken_zeta_config["data_quality"][0]["configuration_pass"] = False
        _write(zeta, broken_zeta_config)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "broken-zeta-config",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["zeta_exact_supply_yoke"]["checks"][
            "all_configurations"
        ]

        tampered_zeta_schedule = _zeta(root=root)
        schedule_path = Path(tampered_zeta_schedule["schedule"]["path"])
        schedule_path.write_text("tampered", encoding="utf-8")
        _write(zeta, tampered_zeta_schedule)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "tampered-zeta-schedule",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["zeta_exact_supply_yoke"]["checks"][
            "schedule_hash_matches"
        ]

        _write(zeta, _zeta(root=root))
        warning_primary = _p3(intervention="consolidated", root=root)
        warning_append = _p3(intervention="append", root=root)
        for report in [warning_primary, warning_append]:
            report["decision"] = (
                "p3_not_behaviorally_interpretable_quality_warning"
            )
            report["checks"] = {}
            report["paired_stats"] = {}
            report["per_family_effects"] = []
            report["formal_data_quality"]["status"] = (
                "quality_warning_review_required"
            )
            report["formal_data_quality"]["checks"]["all_parse_rates"] = False
        _write(primary, warning_primary)
        _write(append, warning_append)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "p3-quality-warning",
        )
        assert result["status"] == "ready_for_paper_revision", result
        assert not result["p3_quality_clear"]
        assert result["p3_reports_same_quality"]
        assert result["sections"]["p3_primary"]["status"] == "complete"
        assert (
            result["sections"]["p3_primary"]["decision"]
            == "p3_not_behaviorally_interpretable_quality_warning"
        )

        inconsistent_warning = _p3(intervention="consolidated", root=root)
        inconsistent_warning["decision"] = (
            "p3_not_behaviorally_interpretable_quality_warning"
        )
        inconsistent_warning["formal_data_quality"]["status"] = (
            "quality_warning_review_required"
        )
        inconsistent_warning["formal_data_quality"]["checks"][
            "all_parse_rates"
        ] = False
        _write(primary, inconsistent_warning)
        _write(append, warning_append)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "p3-warning-with-behavior",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["sections"]["p3_primary"]["checks"][
            "decision_quality_consistent"
        ]

        _write(primary, _p3(intervention="consolidated", root=root))
        _write(append, _p3(intervention="append", root=root))
        mismatched_append = _p3(intervention="append", root=root)
        mismatched_append["formal_data_quality"]["aggregate"]["parse_rate"] = 0.999
        _write(append, mismatched_append)
        result = build_revision_evidence(
            controls_manifest=controls,
            sensitivity_manifest=sensitivity,
            zeta_manifest=zeta,
            p3_primary_report=primary,
            p3_append_report=append,
            out_dir=root / "mismatched-p3-quality",
        )
        assert result["status"] == "evidence_incomplete"
        assert not result["p3_reports_same_quality"]
    print("selftest_revision_evidence OK")


if __name__ == "__main__":
    main()
