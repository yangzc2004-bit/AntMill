from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .epsilon_evidence import _provenance_report, _quality_rows
from .miniwob_stats import formal_quality_report, p3_preregistration_provenance
from .revision_evidence import P3_CONDITIONS, P3_FAMILIES


P3_SUFFIXES = {
    "frozen_reviewer": "frozen",
    "shared_append_ga": "append",
    "shared_consolidated_expel": "consolidated",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _epsilon_results(runs_dir: Path) -> tuple[dict[tuple[str, int], dict[str, Any]], list[dict[str, Any]]]:
    results: dict[tuple[str, int], dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []
    for path in sorted(runs_dir.rglob("result.json")) if runs_dir.exists() else []:
        match = re.fullmatch(r"n4_gt_false_seed(\d+)_(.+)", path.parent.name)
        if not match:
            continue
        seed = int(match.group(1))
        condition = match.group(2)
        results[(condition, seed)] = _load_json(path)
        sources.append(
            {
                "condition": condition,
                "seed": seed,
                "path": str(path),
                "sha256": _sha256(path),
            }
        )
    return results, sources


def _parse_p3_path(path: Path) -> tuple[str, str, str]:
    name = path.parent.name
    seed_match = re.search(r"_seed(\d+)_", name)
    if not seed_match:
        raise ValueError(f"Cannot parse P3 seed from {name}")
    seed = seed_match.group(1)
    family = next(
        (
            family
            for family in P3_FAMILIES
            if f"gamma_p3_{family.replace('-', '_')}_" in name
        ),
        None,
    )
    if not family:
        raise ValueError(f"Cannot parse P3 family from {name}")
    condition = next(
        (
            label
            for suffix, label in P3_SUFFIXES.items()
            if name.endswith(suffix)
        ),
        None,
    )
    if not condition:
        raise ValueError(f"Cannot parse P3 condition from {name}")
    return condition, seed, family


def _p3_specs(runs_dir: Path) -> tuple[list[str], list[dict[str, Any]]]:
    specs: list[str] = []
    sources: list[dict[str, Any]] = []
    for path in sorted(runs_dir.rglob("result.json")) if runs_dir.exists() else []:
        condition, seed, family = _parse_p3_path(path)
        specs.append(f"{condition}:{seed}:{family}={path.as_posix()}")
        sources.append(
            {
                "condition": condition,
                "seed": seed,
                "family": family,
                "path": str(path),
                "sha256": _sha256(path),
            }
        )
    return specs, sources


def build_live_run_health(
    *,
    epsilon_dir: Path,
    p3_dir: Path,
    out_dir: Path,
) -> dict[str, Any]:
    epsilon_results, epsilon_sources = _epsilon_results(epsilon_dir)
    epsilon_result_paths = {
        (str(row["condition"]), int(row["seed"])): Path(str(row["path"]))
        for row in epsilon_sources
    }
    epsilon_quality = (
        _quality_rows(
            epsilon_results,
            suite="controls",
            result_paths=epsilon_result_paths,
        )
        if epsilon_results
        else []
    )
    epsilon_provenance = _provenance_report() if epsilon_results else {}
    epsilon_summary = {
        "completed_results": len(epsilon_sources),
        "all_terminal_route_counts": bool(epsilon_quality)
        and all(bool(row["route_count_pass"]) for row in epsilon_quality),
        "all_configurations": bool(epsilon_quality)
        and all(bool(row["configuration_pass"]) for row in epsilon_quality),
        "all_manifests": bool(epsilon_quality)
        and all(bool(row["manifest_pass"]) for row in epsilon_quality),
        "total_api_errors": sum(int(row["llm_error_count"]) for row in epsilon_quality),
        "total_retries": sum(int(row["llm_retry_count"]) for row in epsilon_quality),
        "total_content_filter_hits": sum(
            int(row["content_filter_hits"]) for row in epsilon_quality
        ),
        "total_exhausted_llm_calls": sum(
            int(row["exhausted_llm_call_count"]) for row in epsilon_quality
        ),
        "total_all_round_route_llm_errors": sum(
            int(row["route_llm_error_count_all_rounds"]) for row in epsilon_quality
        ),
        "total_terminal_route_llm_errors": sum(
            int(row["route_llm_error_count_final"]) for row in epsilon_quality
        ),
        "total_nonterminal_route_llm_errors": sum(
            int(row["route_llm_error_count_nonterminal"]) for row in epsilon_quality
        ),
        "total_all_round_parse_failures": sum(
            int(row["parse_failure_count_all_rounds"]) for row in epsilon_quality
        ),
        "total_terminal_parse_failures": sum(
            int(row["parse_failure_count_final"]) for row in epsilon_quality
        ),
        "total_nonterminal_parse_failures": sum(
            int(row["parse_failure_count_nonterminal"]) for row in epsilon_quality
        ),
        "nonterminal_route_quality_warnings": [
            {
                "condition": row["condition"],
                "seed": row["seed"],
                "route_llm_errors": row["route_llm_error_count_nonterminal"],
                "route_llm_error_affected_routes": row[
                    "route_llm_error_affected_routes_all_rounds"
                ],
                "route_llm_error_rounds": [
                    t for t in row["route_llm_error_rounds"] if t != row["terminal_t"]
                ],
                "parse_failures": row["parse_failure_count_nonterminal"],
                "parse_failure_rounds": [
                    t for t in row["parse_failure_rounds"] if t != row["terminal_t"]
                ],
            }
            for row in epsilon_quality
            if row["route_llm_error_count_nonterminal"] > 0
            or row["parse_failure_count_nonterminal"] > 0
        ],
        "llm_quality_warnings": [
            {
                "condition": row["condition"],
                "seed": row["seed"],
                "exhausted_llm_calls": row["exhausted_llm_call_count"],
                "exhausted_llm_call_rounds": row["exhausted_llm_call_rounds"],
                "exhausted_llm_call_contexts": row[
                    "exhausted_llm_call_contexts"
                ],
                "route_llm_errors_all_rounds": row[
                    "route_llm_error_count_all_rounds"
                ],
                "route_llm_errors_terminal": row[
                    "route_llm_error_count_final"
                ],
                "parse_failures_all_rounds": row[
                    "parse_failure_count_all_rounds"
                ],
                "parse_failures_terminal": row["parse_failure_count_final"],
            }
            for row in epsilon_quality
            if row["exhausted_llm_call_count"] > 0
            or row["route_llm_error_count_all_rounds"] > 0
            or row["parse_failure_count_all_rounds"] > 0
        ],
        "preregistration_hash_match": bool(
            epsilon_provenance.get("preregistration", {}).get("match")
        )
        if epsilon_results
        else None,
        "runtime_source_hashes_match": bool(
            epsilon_provenance.get("runtime_source", {}).get("all_match")
        )
        if epsilon_results
        else None,
    }

    p3_specs, p3_sources = _p3_specs(p3_dir)
    if p3_specs:
        p3_quality = formal_quality_report(
            runs=p3_specs,
            require_complete_matrix=False,
        )
        p3_provenance = p3_preregistration_provenance()
    else:
        p3_quality = {
            "status": "no_complete_results",
            "checks": {},
            "aggregate": {"run_count": 0, "route_count": 0},
            "runs": [],
        }
        p3_provenance = {}
    completed_keys = {
        (row["condition"], str(row["seed"]), row["family"])
        for row in p3_sources
    }
    expected_keys = {
        (condition, str(seed), family)
        for condition in P3_CONDITIONS
        for seed in range(3)
        for family in P3_FAMILIES
    }
    complete_families = [
        family
        for family in P3_FAMILIES
        if all(
            (condition, str(seed), family) in completed_keys
            for condition in P3_CONDITIONS
            for seed in range(3)
        )
    ]
    p3_summary = {
        "completed_results": len(p3_sources),
        "expected_results": len(expected_keys),
        "complete_families": complete_families,
        "quality_status_for_completed_results": p3_quality["status"],
        "total_api_errors": int(
            p3_quality.get("aggregate", {}).get("api_error_count", 0)
        ),
        "total_retries": int(
            p3_quality.get("aggregate", {}).get("retry_count", 0)
        ),
        "total_content_filter_hits": int(
            p3_quality.get("aggregate", {}).get(
                "content_filter_hits",
                0,
            )
        ),
        "total_exhausted_llm_calls": int(
            p3_quality.get("aggregate", {}).get(
                "exhausted_llm_call_count",
                0,
            )
        ),
        "total_route_llm_errors_all_rounds": int(
            p3_quality.get("aggregate", {}).get(
                "route_llm_error_count_all_rounds",
                0,
            )
        ),
        "total_route_llm_errors_final": int(
            p3_quality.get("aggregate", {}).get(
                "route_llm_error_count_final",
                0,
            )
        ),
        "total_nonheldout_exhausted_llm_calls": int(
            p3_quality.get("aggregate", {}).get(
                "nonheldout_exhausted_llm_call_count",
                0,
            )
        ),
        "llm_disclosure_warning_runs": [
            {
                "condition": row["condition"],
                "seed": row["seed"],
                "family": row["family"],
                "active_memory_arm": row["active_memory_arm"],
                "api_errors": row["api_error_count"],
                "retries": row["retry_count"],
                "exhausted_llm_calls": row[
                    "exhausted_llm_call_count"
                ],
                "route_llm_errors_all_rounds": row[
                    "route_llm_error_count_all_rounds"
                ],
                "route_llm_errors_final": row[
                    "route_llm_error_count_final"
                ],
                "route_llm_error_rounds": row[
                    "route_llm_error_rounds"
                ],
                "nonheldout_exhausted_llm_calls": row[
                    "nonheldout_exhausted_llm_call_count"
                ],
                "audit_llm_error_count": row[
                    "audit_llm_error_count"
                ],
                "llm_behavioral_path_pass": row[
                    "llm_behavioral_path_pass"
                ],
            }
            for row in p3_quality.get("runs", [])
            if row.get("llm_disclosure_warning")
        ],
        "preregistration_and_runtime_hashes_match": (
            bool(p3_provenance.get("all_match")) if p3_specs else None
        ),
        "runtime_source_hashes_match": (
            bool(p3_provenance.get("runtime_source", {}).get("all_match"))
            if p3_specs
            else None
        ),
        "aggregate": p3_quality["aggregate"],
        "checks": p3_quality["checks"],
        "failed_completed_results": [
            {
                "condition": row["condition"],
                "seed": row["seed"],
                "family": row["family"],
                "route_count_pass": row["route_count_pass"],
                "parse_pass": row["parse_pass"],
                "llm_behavioral_path_pass": row[
                    "llm_behavioral_path_pass"
                ],
                "infrastructure_pass": row["infrastructure_pass"],
                "bid_pass": row["bid_pass"],
                "reviewer_summary_schema_pass": row[
                    "reviewer_summary_schema_pass"
                ],
                "configuration_pass": row["configuration_pass"],
                "manifest_pass": row["manifest_pass"],
                "environment_consistency_pass": row[
                    "environment_consistency_pass"
                ],
            }
            for row in p3_quality.get("runs", [])
            if not row.get("passed")
        ],
    }

    engineering_clear = (
        (
            not epsilon_quality
            or (
                epsilon_summary["all_terminal_route_counts"]
                and epsilon_summary["all_configurations"]
                and epsilon_summary["all_manifests"]
            )
        )
        and (
            not p3_specs
            or (
                p3_quality["status"] == "quality_clear"
                and bool(p3_provenance.get("all_match"))
            )
        )
    )
    result = {
        "status": (
            "completed_artifacts_need_review"
            if not engineering_clear
            else (
                "completed_artifacts_engineering_clear_with_nonterminal_warnings"
                if (
                    epsilon_summary["llm_quality_warnings"]
                    or p3_summary["llm_disclosure_warning_runs"]
                )
                else "completed_artifacts_engineering_clear"
            )
        ),
        "scope": (
            "engineering quality and coverage only; no cross-arm behavioral "
            "contrast or outcome decision is computed"
        ),
        "epsilon": {
            "runs_dir": str(epsilon_dir),
            "summary": epsilon_summary,
            "quality_rows": epsilon_quality,
            "sources": epsilon_sources,
        },
        "p3": {
            "runs_dir": str(p3_dir),
            "summary": p3_summary,
            "quality_rows": p3_quality.get("runs", []),
            "sources": p3_sources,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "live_run_health.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Live Run Health",
        "",
        f"Status: **{result['status']}**",
        "",
        result["scope"] + ".",
        "",
        "## Epsilon",
        "",
        f"- complete results: {epsilon_summary['completed_results']}",
        f"- terminal route counts complete: {epsilon_summary['all_terminal_route_counts']}",
        f"- formal configurations match: {epsilon_summary['all_configurations']}",
        f"- result manifests match: {epsilon_summary['all_manifests']}",
        f"- API errors / retries / filter hits: "
        f"{epsilon_summary['total_api_errors']} / {epsilon_summary['total_retries']} / "
        f"{epsilon_summary['total_content_filter_hits']}",
        f"- exhausted LLM calls after all retries: "
        f"{epsilon_summary['total_exhausted_llm_calls']}",
        f"- all-round / terminal route LLM errors: "
        f"{epsilon_summary['total_all_round_route_llm_errors']} / "
        f"{epsilon_summary['total_terminal_route_llm_errors']}",
        f"- all-round / terminal parse failures: "
        f"{epsilon_summary['total_all_round_parse_failures']} / "
        f"{epsilon_summary['total_terminal_parse_failures']}",
        f"- runs with disclosed LLM/parse warnings: "
        f"{len(epsilon_summary['llm_quality_warnings'])}",
        "",
        "## MiniWoB P3",
        "",
        f"- complete results: {p3_summary['completed_results']}/{p3_summary['expected_results']}",
        f"- preregistration and runtime-source hashes match: "
        f"{p3_summary['preregistration_and_runtime_hashes_match']}",
        f"- complete task families: {', '.join(complete_families) or 'none'}",
        f"- quality status for completed results: "
        f"{p3_summary['quality_status_for_completed_results']}",
        f"- API errors / retries / filter hits: "
        f"{p3_summary['total_api_errors']} / "
        f"{p3_summary['total_retries']} / "
        f"{p3_summary['total_content_filter_hits']}",
        f"- exhausted LLM calls after all retries: "
        f"{p3_summary['total_exhausted_llm_calls']}",
        f"- all-round / terminal route LLM errors: "
        f"{p3_summary['total_route_llm_errors_all_rounds']} / "
        f"{p3_summary['total_route_llm_errors_final']}",
        f"- non-heldout exhausted LLM calls: "
        f"{p3_summary['total_nonheldout_exhausted_llm_calls']}",
        f"- runs with disclosed LLM warnings: "
        f"{len(p3_summary['llm_disclosure_warning_runs'])}",
        f"- failed completed results: {len(p3_summary['failed_completed_results'])}",
        "",
    ]
    (out_dir / "live_run_health.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit completed run artifacts without computing behavioral contrasts."
    )
    parser.add_argument(
        "--epsilon-dir",
        default="runs_maze_epsilon_controls",
    )
    parser.add_argument(
        "--p3-dir",
        default="runs_miniwob_gamma_p3e",
    )
    parser.add_argument("--out-dir", default="runs_live_health")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_live_run_health(
        epsilon_dir=Path(args.epsilon_dir),
        p3_dir=Path(args.p3_dir),
        out_dir=Path(args.out_dir),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
