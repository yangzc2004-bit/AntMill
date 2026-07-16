from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .epsilon_evidence import CONTROL_ARMS, CONTROL_CONTRASTS, SENSITIVITY_ARMS
from .maze_stats import PAIRED_METRICS
from .miniwob_stats import P3_METRICS, PRIMARY_METRICS as P3_PRIMARY_METRICS


P3_FAMILIES = [
    "click-button",
    "choose-list",
    "enter-text",
    "click-checkboxes",
    "login-user",
    "use-autocomplete-nodelay",
]
P3_CONDITIONS = ["frozen", "append", "consolidated"]
MAZE_ROUTES_PER_SEED = 12 * 4
P3_PAIRS_PER_FAMILY = 3 * 12 * 4
P3_TOTAL_PAIRS = len(P3_FAMILIES) * P3_PAIRS_PER_FAMILY
P3_QUALITY_CHECKS = {
    "complete_matrix",
    "all_route_counts",
    "all_parse_rates",
    "all_llm_behavioral_paths",
    "all_infrastructure_error_rates",
    "all_bid_error_rates",
    "all_reviewer_summary_schemas",
    "all_configurations",
    "all_manifests",
    "all_environments_consistent",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_result_checks(
    rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
    expected_keys: set[tuple[str, ...]],
) -> tuple[bool, bool]:
    actual_keys = [
        tuple(str(row.get(field, "")) for field in key_fields)
        for row in rows
    ]
    exact_keys = (
        len(rows) == len(expected_keys)
        and len(set(actual_keys)) == len(expected_keys)
        and set(actual_keys) == expected_keys
    )
    hashes_match = bool(rows)
    for row in rows:
        path = Path(str(row.get("path", "")))
        expected = str(row.get("sha256", ""))
        if not path.exists() or not expected or _sha256(path) != expected:
            hashes_match = False
            break
    return exact_keys, hashes_match


def _check_epsilon(path: Path, *, suite: str) -> dict[str, Any]:
    report = _load_json(path)
    if suite == "controls":
        expected_seeds = [0, 1, 2, 3, 4]
        expected_contrasts = CONTROL_CONTRASTS
        expected_arms = CONTROL_ARMS
    else:
        expected_seeds = [0, 1, 2]
        expected_contrasts = [
            (f"{arm}_minus_epsilon_sens_reference", arm, "epsilon_sens_reference")
            for arm in SENSITIVITY_ARMS
            if arm != "epsilon_sens_reference"
        ]
        expected_arms = SENSITIVITY_ARMS
    expected_stats = len(expected_contrasts) * len(PAIRED_METRICS)
    expected_effects = expected_stats * len(expected_seeds)
    expected_runs = len(expected_arms) * len(expected_seeds)
    expected_stat_keys = {
        (contrast, metric)
        for contrast, _intervention, _baseline in expected_contrasts
        for metric in PAIRED_METRICS
    }
    expected_effect_keys = {
        (contrast, metric, seed)
        for contrast, _intervention, _baseline in expected_contrasts
        for metric in PAIRED_METRICS
        for seed in expected_seeds
    }
    expected_run_keys = {
        (arm, seed)
        for arm in expected_arms
        for seed in expected_seeds
    }
    stats = report.get("stats", [])
    effects = report.get("per_seed_effects", [])
    quality = report.get("data_quality", [])
    memory = report.get("memory_summary", [])
    source_results = report.get("source_results", [])
    source_manifests = report.get("source_manifests", [])
    provenance = report.get("provenance", {})
    actual_stat_keys = {
        (str(row.get("contrast")), str(row.get("metric")))
        for row in stats
    }
    actual_effect_keys = {
        (str(row.get("contrast")), str(row.get("metric")), int(row.get("seed", -1)))
        for row in effects
    }
    expected_pairs = len(expected_seeds) * MAZE_ROUTES_PER_SEED
    unconditional_metrics = set(PAIRED_METRICS) - {"success_excess_steps"}
    stats_pairing_complete = bool(stats) and all(
        (
            int(row.get("n_pairs", -1)) == expected_pairs
            and int(row.get("n_dropped", -1)) == 0
        )
        if str(row.get("metric")) in unconditional_metrics
        else (
            0 < int(row.get("n_pairs", 0)) <= expected_pairs
            and int(row.get("n_pairs", 0))
            + int(row.get("n_dropped", -1))
            == expected_pairs
        )
        for row in stats
    )
    stats_terminal_complete = bool(stats) and all(
        int(row.get("t", -1)) == 5
        and row.get("analysis_method") == "seed_clustered_paired_bootstrap"
        and int(row.get("n_seeds", -1)) == len(expected_seeds)
        for row in stats
    )
    effects_pairing_complete = bool(effects) and all(
        int(row.get("t", -1)) == 5
        and (
            int(row.get("n_pairs", -1)) == MAZE_ROUTES_PER_SEED
            if str(row.get("metric")) in unconditional_metrics
            else 0 < int(row.get("n_pairs", 0)) <= MAZE_ROUTES_PER_SEED
        )
        for row in effects
    )
    quality_keys = {
        (str(row.get("condition")), int(row.get("seed", -1)))
        for row in quality
    }
    memory_keys = {
        (str(row.get("condition")), int(row.get("seed", -1)))
        for row in memory
    }
    source_exact_keys, source_hashes_match = _source_result_checks(
        source_results,
        key_fields=("condition", "seed"),
        expected_keys={
            (str(arm), str(seed))
            for arm, seed in expected_run_keys
        },
    )
    manifest_exact_keys, manifest_hashes_match = _source_result_checks(
        source_manifests,
        key_fields=("condition", "seed"),
        expected_keys={
            (str(arm), str(seed))
            for arm, seed in expected_run_keys
        },
    )
    checks = {
        "suite": report.get("suite") == suite,
        "seeds": report.get("seeds") == expected_seeds,
        "terminal_round": int(report.get("final_t", -1)) == 5,
        "contrasts": [tuple(value) for value in report.get("contrasts", [])] == expected_contrasts,
        "stats_count": len(stats) == expected_stats,
        "stats_exact_keys": len(actual_stat_keys) == expected_stats
        and actual_stat_keys == expected_stat_keys,
        "stats_terminal_and_seed_counts": stats_terminal_complete,
        "stats_pairing_complete": stats_pairing_complete,
        "per_seed_effect_count": len(effects) == expected_effects,
        "per_seed_effect_exact_keys": len(actual_effect_keys) == expected_effects
        and actual_effect_keys == expected_effect_keys,
        "per_seed_pairing_complete": effects_pairing_complete,
        "run_quality_count": len(quality) == expected_runs,
        "run_quality_exact_keys": len(quality_keys) == expected_runs
        and quality_keys == expected_run_keys,
        "all_terminal_route_counts": bool(quality) and all(bool(row.get("route_count_pass")) for row in quality),
        "all_terminal_rounds": bool(quality)
        and all(
            bool(row.get("terminal_round_pass"))
            and int(row.get("terminal_t", -1)) == 5
            and int(row.get("expected_terminal_t", -1)) == 5
            for row in quality
        ),
        "all_configurations": bool(quality)
        and all(bool(row.get("configuration_pass")) for row in quality),
        "all_manifests": bool(quality)
        and all(bool(row.get("manifest_pass")) for row in quality),
        "memory_summary_count": len(memory) == expected_runs,
        "memory_summary_exact_keys": len(memory_keys) == expected_runs
        and memory_keys == expected_run_keys,
        "source_result_exact_keys": source_exact_keys,
        "source_result_hashes": source_hashes_match,
        "source_manifest_exact_keys": manifest_exact_keys,
        "source_manifest_hashes": manifest_hashes_match,
        "hierarchical_method": report.get("analysis_method") == "seed_clustered_paired_bootstrap",
        "preregistration_hash": bool(provenance.get("preregistration", {}).get("match")),
        "runtime_source_hashes": bool(provenance.get("runtime_source", {}).get("all_match")),
    }
    return {
        "suite": suite,
        "path": str(path),
        "status": "complete" if all(checks.values()) else "incomplete_or_invalid",
        "checks": checks,
        "expected": {
            "runs": expected_runs,
            "stats": expected_stats,
            "per_seed_effects": expected_effects,
        },
    }


def _check_p3(path: Path, *, intervention: str) -> dict[str, Any]:
    report = _load_json(path)
    quality = report.get("formal_data_quality", {})
    quality_status = quality.get("status")
    quality_clear = quality_status == "quality_clear"
    quality_warning = quality_status == "quality_warning_review_required"
    provenance = report.get("preregistration_provenance", {})
    family_effects = report.get("per_family_effects", [])
    expected_family_keys = {
        (family, metric)
        for family in P3_FAMILIES
        for metric in P3_METRICS
    }
    actual_family_keys = {
        (str(row.get("family")), str(row.get("metric")))
        for row in family_effects
    }
    paired_stats = report.get("paired_stats", {})
    paired_stats_complete = bool(paired_stats) and all(
        str(stat.get("metric")) == metric
        and int(stat.get("n_pairs", -1)) == P3_TOTAL_PAIRS
        and int(stat.get("n_dropped", -1)) == 0
        for metric, stat in paired_stats.items()
    )
    family_pairing_complete = bool(family_effects) and all(
        int(row.get("n_pairs", -1)) == P3_PAIRS_PER_FAMILY
        and int(row.get("n_dropped", -1)) == 0
        for row in family_effects
    )
    quality_runs = quality.get("runs", [])
    expected_run_keys = {
        (condition, str(seed), family)
        for condition in P3_CONDITIONS
        for seed in range(3)
        for family in P3_FAMILIES
    }
    actual_run_keys = {
        (str(row.get("condition")), str(row.get("seed")), str(row.get("family")))
        for row in quality_runs
    }
    source_exact_keys, source_hashes_match = _source_result_checks(
        report.get("source_results", []),
        key_fields=("condition", "seed", "family"),
        expected_keys=expected_run_keys,
    )
    manifest_exact_keys, manifest_hashes_match = _source_result_checks(
        report.get("source_manifests", []),
        key_fields=("condition", "seed", "family"),
        expected_keys=expected_run_keys,
    )
    gate_checks = report.get("checks", {})
    quality_checks = quality.get("checks", {})
    quality_check_keys = set(quality_checks)
    all_quality_checks_pass = (
        quality_check_keys == P3_QUALITY_CHECKS
        and all(bool(quality_checks[key]) for key in P3_QUALITY_CHECKS)
    )
    quality_status_consistent = (
        quality_status == "quality_clear" and all_quality_checks_pass
    ) or (
        quality_status == "quality_warning_review_required"
        and quality_check_keys == P3_QUALITY_CHECKS
        and not all_quality_checks_pass
    )
    seed_effects_complete = True
    for metric in P3_PRIMARY_METRICS:
        summary = gate_checks.get(f"{metric}_same_sign_seeds", {})
        seed_keys = {str(seed) for seed in summary.get("diffs", {})}
        seed_effects_complete = bool(
            seed_effects_complete
            and int(summary.get("n", -1)) == 3
            and seed_keys == {"0", "1", "2"}
        )
    decision = report.get("decision")
    clear_behavioral_payload = bool(
        quality_clear
        and decision in {
            "p3_phenomenon_pass",
            "p3_not_detected_or_underpowered",
        }
        and len(paired_stats) == len(P3_METRICS)
        and set(paired_stats) == set(P3_METRICS)
        and paired_stats_complete
        and len(family_effects) == len(expected_family_keys)
        and len(actual_family_keys) == len(expected_family_keys)
        and actual_family_keys == expected_family_keys
        and family_pairing_complete
        and seed_effects_complete
    )
    warning_payload_withheld = bool(
        quality_warning
        and decision == "p3_not_behaviorally_interpretable_quality_warning"
        and not gate_checks
        and not paired_stats
        and not family_effects
    )
    route_count = int(quality.get("aggregate", {}).get("route_count", -1))
    checks = {
        "kind": report.get("kind") == "p3",
        "intervention": report.get("intervention") == intervention,
        "baseline": report.get("baseline") == "frozen",
        "terminal_round": int(report.get("t", -1)) == 3,
        "decision_recorded": decision in {
            "p3_phenomenon_pass",
            "p3_not_detected_or_underpowered",
            "p3_not_behaviorally_interpretable_quality_warning",
        },
        "decision_quality_consistent": clear_behavioral_payload
        or warning_payload_withheld,
        "metric_count": (
            len(paired_stats) == len(P3_METRICS)
            if quality_clear
            else len(paired_stats) == 0
        ),
        "metric_exact_keys": (
            set(paired_stats) == set(P3_METRICS)
            if quality_clear
            else not paired_stats
        ),
        "paired_route_coverage": paired_stats_complete if quality_clear else not paired_stats,
        "per_family_effect_count": (
            len(family_effects) == len(expected_family_keys)
            if quality_clear
            else len(family_effects) == 0
        ),
        "per_family_effect_exact_keys": (
            len(actual_family_keys) == len(expected_family_keys)
            and actual_family_keys == expected_family_keys
            if quality_clear
            else not actual_family_keys
        ),
        "per_family_route_coverage": (
            family_pairing_complete if quality_clear else not family_effects
        ),
        "per_seed_primary_effects": (
            seed_effects_complete if quality_clear else not gate_checks
        ),
        "formal_run_count": int(quality.get("aggregate", {}).get("run_count", 0)) == 54,
        "formal_route_count": (
            route_count == 10_368
            if quality_clear
            else 0 <= route_count <= 10_368
        ),
        "formal_run_rows": len(quality_runs) == 54,
        "formal_run_exact_keys": len(actual_run_keys) == 54
        and actual_run_keys == expected_run_keys,
        "source_result_exact_keys": source_exact_keys,
        "source_result_hashes": source_hashes_match,
        "source_manifest_exact_keys": manifest_exact_keys,
        "source_manifest_hashes": manifest_hashes_match,
        "quality_status_recorded": quality_clear or quality_warning,
        "quality_check_exact_keys": quality_check_keys == P3_QUALITY_CHECKS,
        "quality_status_consistent": quality_status_consistent,
        "preregistration_hashes": bool(provenance.get("all_match")),
        "runtime_source_hashes": bool(
            provenance.get("runtime_source", {}).get("all_match")
        ),
    }
    return {
        "intervention": intervention,
        "path": str(path),
        "status": "complete" if all(checks.values()) else "incomplete_or_invalid",
        "quality_status": quality_status or "missing",
        "quality_digest": _json_digest(quality),
        "decision": report.get("decision", "missing"),
        "checks": checks,
    }


def _check_zeta(path: Path) -> dict[str, Any]:
    report = _load_json(path)
    quality = report.get("data_quality", [])
    manipulation = report.get("manipulation_checks", [])
    memory = report.get("memory_summary", [])
    schedule = report.get("schedule", {})
    expected_stat_keys = set(PAIRED_METRICS)
    actual_stat_keys = {str(row.get("metric")) for row in report.get("stats", [])}
    expected_effect_keys = {
        (metric, seed)
        for metric in PAIRED_METRICS
        for seed in range(5)
    }
    actual_effect_keys = {
        (str(row.get("metric")), int(row.get("seed", -1)))
        for row in report.get("per_seed_effects", [])
    }
    stats = report.get("stats", [])
    effects = report.get("per_seed_effects", [])
    unconditional_metrics = set(PAIRED_METRICS) - {"success_excess_steps"}
    stats_pairing_complete = bool(stats) and all(
        (
            int(row.get("n_pairs", -1)) == 5 * MAZE_ROUTES_PER_SEED
            and int(row.get("n_dropped", -1)) == 0
        )
        if str(row.get("metric")) in unconditional_metrics
        else (
            0 < int(row.get("n_pairs", 0)) <= 5 * MAZE_ROUTES_PER_SEED
            and int(row.get("n_pairs", 0))
            + int(row.get("n_dropped", -1))
            == 5 * MAZE_ROUTES_PER_SEED
        )
        for row in stats
    )
    stats_terminal_complete = bool(stats) and all(
        int(row.get("t", -1)) == 5
        and row.get("analysis_method") == "seed_clustered_paired_bootstrap"
        and int(row.get("n_seeds", -1)) == 5
        for row in stats
    )
    effects_pairing_complete = bool(effects) and all(
        int(row.get("t", -1)) == 5
        and (
            int(row.get("n_pairs", -1)) == MAZE_ROUTES_PER_SEED
            if str(row.get("metric")) in unconditional_metrics
            else 0 < int(row.get("n_pairs", 0)) <= MAZE_ROUTES_PER_SEED
        )
        for row in effects
    )
    expected_manipulation_keys = {
        (seed, t)
        for seed in range(5)
        for t in range(6)
    }
    actual_manipulation_keys = {
        (int(row.get("seed", -1)), int(row.get("t", -1)))
        for row in manipulation
    }
    source_exact_keys, source_hashes_match = _source_result_checks(
        report.get("source_results", []),
        key_fields=("condition", "seed"),
        expected_keys={
            (condition, str(seed))
            for condition in (
                "epsilon_shared_consolidated",
                "zeta_shared_append_exact_yoke",
            )
            for seed in range(5)
        },
    )
    expected_run_keys = {
        (condition, seed)
        for condition in (
            "epsilon_shared_consolidated",
            "zeta_shared_append_exact_yoke",
        )
        for seed in range(5)
    }
    quality_keys = {
        (str(row.get("condition")), int(row.get("seed", -1)))
        for row in quality
    }
    memory_keys = {
        (str(row.get("condition")), int(row.get("seed", -1)))
        for row in memory
    }
    manifest_exact_keys, manifest_hashes_match = _source_result_checks(
        report.get("source_manifests", []),
        key_fields=("condition", "seed"),
        expected_keys={
            (condition, str(seed))
            for condition, seed in expected_run_keys
        },
    )
    schedule_path = Path(str(schedule.get("path", "")))
    schedule_hash_matches = bool(
        schedule_path.exists()
        and schedule.get("sha256")
        and _sha256(schedule_path) == schedule.get("sha256")
    )
    all_manipulations_pass = bool(manipulation) and all(bool(row.get("passed")) for row in manipulation)
    decision = report.get("decision")
    manipulation_decision_consistent = (
        decision == "zeta_supply_yoke_evaluable" and all_manipulations_pass
    ) or (
        decision == "zeta_supply_yoke_not_evaluable" and not all_manipulations_pass
    )
    checks = {
        "suite": report.get("suite") == "zeta_exact_supply_yoke",
        "decision_recorded": decision in {
            "zeta_supply_yoke_evaluable",
            "zeta_supply_yoke_not_evaluable",
        },
        "manipulation_decision_consistent": manipulation_decision_consistent,
        "seeds": report.get("seeds") == [0, 1, 2, 3, 4],
        "terminal_round": int(report.get("final_t", -1)) == 5,
        "hierarchical_method": report.get("analysis_method") == "seed_clustered_paired_bootstrap",
        "stats_count": len(report.get("stats", [])) == len(PAIRED_METRICS),
        "stats_exact_keys": actual_stat_keys == expected_stat_keys,
        "stats_terminal_and_seed_counts": stats_terminal_complete,
        "stats_pairing_complete": stats_pairing_complete,
        "per_seed_effect_count": len(report.get("per_seed_effects", [])) == len(PAIRED_METRICS) * 5,
        "per_seed_effect_exact_keys": len(actual_effect_keys) == len(expected_effect_keys)
        and actual_effect_keys == expected_effect_keys,
        "per_seed_pairing_complete": effects_pairing_complete,
        "manipulation_count": len(manipulation) == 30,
        "manipulation_exact_keys": len(actual_manipulation_keys) == 30
        and actual_manipulation_keys == expected_manipulation_keys,
        "retrieval_candidate_supply_audited": bool(manipulation)
        and all(
            bool(row.get("budget_match"))
            == (
                int(row.get("budget", -1))
                == int(row.get("target", -2))
            )
            and bool(row.get("selected_match"))
            == (
                int(row.get("selected", -1))
                == int(row.get("target", -2))
            )
            and bool(row.get("retrieval_candidate_match"))
            == (
                int(row.get("retrieval_record_count", 0))
                >= MAZE_ROUTES_PER_SEED
                and int(row.get("retrieval_candidate_min", -1))
                == int(row.get("target", -2))
                and int(row.get("retrieval_candidate_max", -1))
                == int(row.get("target", -2))
            )
            and bool(row.get("passed"))
            == (
                bool(row.get("budget_match"))
                and bool(row.get("selected_match"))
                and bool(row.get("retrieval_candidate_match"))
            )
            for row in manipulation
        ),
        "quality_count": len(quality) == 10,
        "quality_exact_keys": len(quality_keys) == 10
        and quality_keys == expected_run_keys,
        "all_terminal_route_counts": bool(quality) and all(bool(row.get("route_count_pass")) for row in quality),
        "all_terminal_rounds": bool(quality)
        and all(
            bool(row.get("terminal_round_pass"))
            and int(row.get("terminal_t", -1)) == 5
            and int(row.get("expected_terminal_t", -1)) == 5
            for row in quality
        ),
        "all_configurations": bool(quality)
        and all(bool(row.get("configuration_pass")) for row in quality),
        "all_manifests": bool(quality)
        and all(bool(row.get("manifest_pass")) for row in quality),
        "memory_summary_count": len(memory) == 10,
        "memory_summary_exact_keys": len(memory_keys) == 10
        and memory_keys == expected_run_keys,
        "source_result_exact_keys": source_exact_keys,
        "source_result_hashes": source_hashes_match,
        "source_manifest_exact_keys": manifest_exact_keys,
        "source_manifest_hashes": manifest_hashes_match,
        "preregistration_hash": bool(schedule.get("preregistration", {}).get("match")),
        "schedule_hash_matches": schedule_hash_matches,
        "schedule_metadata": (
            schedule.get("phase") == "zeta_exact_supply_yoke"
            and schedule.get("schedule_name") == "gamma_consolidated_active_cummax"
            and schedule.get("source_arm") == "epsilon_shared_consolidated"
            and schedule.get("target_definition")
            == "active_pool_size at the matching evaluation round"
            and int(schedule.get("source_count", -1)) == 5
        ),
    }
    return {
        "path": str(path),
        "status": "complete" if all(checks.values()) else "incomplete_or_invalid",
        "decision": report.get("decision", "missing"),
        "checks": checks,
    }


def build_revision_evidence(
    *,
    controls_manifest: Path,
    sensitivity_manifest: Path,
    zeta_manifest: Path,
    p3_primary_report: Path,
    p3_append_report: Path,
    out_dir: Path,
) -> dict[str, Any]:
    controls = _check_epsilon(controls_manifest, suite="controls")
    sensitivity = _check_epsilon(sensitivity_manifest, suite="sensitivity")
    zeta = _check_zeta(zeta_manifest)
    p3_primary = _check_p3(p3_primary_report, intervention="consolidated")
    p3_append = _check_p3(p3_append_report, intervention="append")
    sections = {
        "epsilon_controls": controls,
        "epsilon_sensitivity": sensitivity,
        "zeta_exact_supply_yoke": zeta,
        "p3_primary": p3_primary,
        "p3_append_secondary": p3_append,
    }
    p3_reports_same_quality = p3_primary["quality_digest"] == p3_append["quality_digest"]
    data_complete = (
        all(section["status"] == "complete" for section in sections.values())
        and p3_reports_same_quality
    )
    p3_quality_clear = (
        p3_reports_same_quality
        and p3_primary["quality_status"] == "quality_clear"
        and p3_append["quality_status"] == "quality_clear"
    )
    result = {
        "status": "ready_for_paper_revision" if data_complete else "evidence_incomplete",
        "data_complete": data_complete,
        "p3_quality_clear": p3_quality_clear,
        "p3_reports_same_quality": p3_reports_same_quality,
        "sections": sections,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "revision_evidence.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Revision Evidence Gate",
        "",
        f"Status: **{result['status']}**",
        "",
        "| section | completeness | decision | quality |",
        "|---|---|---|---|",
    ]
    for name, section in sections.items():
        lines.append(
            f"| {name} | {section['status']} | {section.get('decision', 'n/a')} | "
            f"{section.get('quality_status', 'n/a')} |"
        )
    lines.extend(
        [
            "",
            "This gate verifies artifact completeness only. It does not choose claims, "
            "reinterpret preregistered outcomes, or certify the paper revision.",
            "",
        ]
    )
    (out_dir / "revision_evidence.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify that all revision evidence artifacts are complete.")
    parser.add_argument(
        "--controls-manifest",
        default="runs_maze_epsilon_controls_stats/evidence_manifest.json",
    )
    parser.add_argument(
        "--sensitivity-manifest",
        default="runs_maze_epsilon_sensitivity_stats/evidence_manifest.json",
    )
    parser.add_argument(
        "--zeta-manifest",
        default="runs_maze_zeta_exact_yoke_stats/evidence_manifest.json",
    )
    parser.add_argument(
        "--p3-primary-report",
        default="runs_miniwob_gamma_p3e_stats/p3_gate_report.json",
    )
    parser.add_argument(
        "--p3-append-report",
        default="runs_miniwob_gamma_p3e_stats/append_secondary/p3_gate_report.json",
    )
    parser.add_argument("--out-dir", default="runs_revision_evidence")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_revision_evidence(
        controls_manifest=Path(args.controls_manifest),
        sensitivity_manifest=Path(args.sensitivity_manifest),
        zeta_manifest=Path(args.zeta_manifest),
        p3_primary_report=Path(args.p3_primary_report),
        p3_append_report=Path(args.p3_append_report),
        out_dir=Path(args.out_dir),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
