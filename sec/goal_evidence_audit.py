from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .environment_manifest import FORMAL_MINIWOB_FIELDS, formal_browser_environment
from .epsilon_evidence import CONTROL_ARMS, SENSITIVITY_ARMS


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _result_count(path: Path) -> int:
    return len(list(path.rglob("result.json"))) if path.exists() else 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_source_freeze_status(
    root: Path,
    freeze_name: str,
) -> dict[str, Any]:
    freeze_path = root / freeze_name
    if not freeze_path.exists():
        return {
            "available": False,
            "all_match": False,
            "file_count": 0,
            "matched_count": 0,
            "failures": [f"missing {freeze_path}"],
        }
    try:
        freeze = _load_optional(freeze_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "available": True,
            "all_match": False,
            "file_count": 0,
            "matched_count": 0,
            "failures": [str(exc)],
        }
    records = freeze.get("files", [])
    failures: list[str] = []
    matched = 0
    for record in records if isinstance(records, list) else []:
        raw_path = Path(str(record.get("path", "")))
        path = raw_path if raw_path.is_absolute() else root / raw_path
        expected = str(record.get("sha256", ""))
        if not path.exists():
            failures.append(f"missing {path}")
            continue
        if not expected or _sha256(path) != expected:
            failures.append(f"hash mismatch {path}")
            continue
        matched += 1
    file_count = len(records) if isinstance(records, list) else 0
    return {
        "available": True,
        "all_match": file_count > 0 and matched == file_count and not failures,
        "file_count": file_count,
        "matched_count": matched,
        "failures": failures,
    }


def _arm_result_count(path: Path, arm: str) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for result in path.rglob("result.json")
        if result.parent.name.endswith("_" + arm)
    )


def _source_hashes(browser: dict[str, Any]) -> list[str]:
    sources = browser.get("provenance", {}).get("source_manifests", [])
    if not isinstance(sources, list):
        return []
    return sorted(
        str(source.get("sha256", ""))
        for source in sources
        if isinstance(source, dict) and source.get("sha256")
    )


def _environment_fields(browser: dict[str, Any]) -> dict[str, Any]:
    return {field: browser.get(field) for field in FORMAL_MINIWOB_FIELDS}


def _requirement(
    *,
    name: str,
    complete: bool,
    progress: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "complete" if complete else ("in_progress" if progress else "missing"),
        "evidence": evidence,
    }


def build_goal_evidence_audit(
    *,
    root: Path,
    out_dir: Path,
) -> dict[str, Any]:
    controls_dir = root / "runs_maze_epsilon_controls"
    sensitivity_dir = root / "runs_maze_epsilon_sensitivity"
    zeta_dir = root / "runs_maze_zeta_exact_yoke"
    p3_dir = root / "runs_miniwob_gamma_p3e"
    controls_manifest_path = root / "runs_maze_epsilon_controls_stats" / "evidence_manifest.json"
    sensitivity_manifest_path = root / "runs_maze_epsilon_sensitivity_stats" / "evidence_manifest.json"
    zeta_manifest_path = root / "runs_maze_zeta_exact_yoke_stats" / "evidence_manifest.json"
    revision_path = root / "runs_revision_evidence" / "revision_evidence.json"
    claim_path = root / "paper_draft" / "generated" / "revision_results" / "claim_decisions.json"
    paper_results_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "paper_results_manifest.json"
    )
    appendix_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "appendix_heterogeneity.tex"
    )
    render_audit_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "final_render_audit.json"
    )
    manuscript_audit_path = (
        root / "runs_manuscript_revision_audit" / "manuscript_revision_audit.json"
    )
    tex_path = root / "paper_draft" / "antmill_memory_aaai27_en.tex"
    bib_path = root / "paper_draft" / "antmill_memory.bib"
    pdf_path = root / "paper_draft" / "antmill_memory_aaai27_en.pdf"
    supplement_tex_path = root / "paper_draft" / "antmill_memory_aaai27_supp.tex"
    supplement_pdf_path = root / "paper_draft" / "antmill_memory_aaai27_supp.pdf"
    supplement_render_audit_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "final_supplement_render_audit.json"
    )
    checklist_tex_path = (
        root / "paper_draft" / "antmill_memory_reproducibility_checklist.tex"
    )
    checklist_pdf_path = (
        root / "paper_draft" / "antmill_memory_reproducibility_checklist.pdf"
    )
    checklist_report_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "reproducibility_checklist_report.json"
    )
    checklist_render_audit_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "final_checklist_render_audit.json"
    )
    environment_manifest_path = (
        root
        / "paper_draft"
        / "generated"
        / "revision_results"
        / "environment_manifest.json"
    )

    controls_manifest = _load_optional(controls_manifest_path)
    sensitivity_manifest = _load_optional(sensitivity_manifest_path)
    zeta_manifest = _load_optional(zeta_manifest_path)
    revision = _load_optional(revision_path)
    claims = _load_optional(claim_path)
    paper_results = _load_optional(paper_results_path)
    manuscript_audit = _load_optional(manuscript_audit_path)
    render_audit = _load_optional(render_audit_path)
    supplement_render_audit = _load_optional(supplement_render_audit_path)
    checklist_report = _load_optional(checklist_report_path)
    checklist_render_audit = _load_optional(checklist_render_audit_path)
    environment_manifest = _load_optional(environment_manifest_path)
    tex = tex_path.read_text(encoding="utf-8-sig") if tex_path.exists() else ""
    bib = bib_path.read_text(encoding="utf-8-sig") if bib_path.exists() else ""

    controls_total = _result_count(controls_dir)
    private_count = _arm_result_count(controls_dir, "epsilon_private_consolidated")
    cap14_count = _arm_result_count(controls_dir, "epsilon_shared_append_cap14")
    mmr_count = _arm_result_count(controls_dir, "epsilon_shared_consolidated_mmr")
    sensitivity_count = _result_count(sensitivity_dir)
    zeta_count = _result_count(zeta_dir)
    zeta_manipulation_checks = zeta_manifest.get("manipulation_checks", [])
    zeta_manipulation_passed = sum(
        1
        for row in zeta_manipulation_checks
        if isinstance(row, dict) and row.get("passed")
    )
    zeta_exact_yoke_evaluable = bool(
        zeta_manifest.get("decision") == "zeta_supply_yoke_evaluable"
        and len(zeta_manipulation_checks) == 30
        and zeta_manipulation_passed == 30
        and all(
            isinstance(row, dict)
            and bool(row.get("retrieval_candidate_match"))
            and int(row.get("retrieval_record_count", 0)) >= 12 * 4
            and int(row.get("retrieval_candidate_min", -1))
            == int(row.get("target", -2))
            and int(row.get("retrieval_candidate_max", -1))
            == int(row.get("target", -2))
            for row in zeta_manipulation_checks
        )
    )
    p3_count = _result_count(p3_dir)
    sections = revision.get("sections", {})
    controls_complete = sections.get("epsilon_controls", {}).get("status") == "complete"
    sensitivity_complete = sections.get("epsilon_sensitivity", {}).get("status") == "complete"
    zeta_complete = sections.get("zeta_exact_supply_yoke", {}).get("status") == "complete"
    p3_primary_complete = sections.get("p3_primary", {}).get("status") == "complete"
    p3_append_complete = (
        sections.get("p3_append_secondary", {}).get("status") == "complete"
    )
    p3_runtime_source_complete = bool(
        sections.get("p3_primary", {})
        .get("checks", {})
        .get("runtime_source_hashes")
        and sections.get("p3_append_secondary", {})
        .get("checks", {})
        .get("runtime_source_hashes")
    )
    p3_runtime_source_current = _runtime_source_freeze_status(
        root,
        "p3e_runtime_source.freeze.json",
    )
    p3_browser = environment_manifest.get("browser_environment", {})
    p3_browser_provenance = p3_browser.get("provenance", {})
    p3_current_environment_error = ""
    try:
        p3_current_browser = formal_browser_environment(p3_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        p3_current_browser = {}
        p3_current_environment_error = str(exc)
    p3_current_provenance = p3_current_browser.get("provenance", {})
    p3_current_manifest_count = int(
        p3_current_provenance.get("completed_manifest_count", 0)
    )
    p3_environment_matches_current = (
        p3_current_provenance.get("source") == "formal_run_manifests"
        and p3_browser_provenance.get("source") == "formal_run_manifests"
        and p3_current_manifest_count
        == int(p3_browser_provenance.get("completed_manifest_count", -1))
        and _source_hashes(p3_current_browser) == _source_hashes(p3_browser)
        and _environment_fields(p3_current_browser) == _environment_fields(p3_browser)
    )
    p3_environment_complete = (
        environment_manifest.get("status") == "environment_manifest_ready"
        and not p3_current_environment_error
        and p3_environment_matches_current
        and p3_current_manifest_count == 54
        and p3_browser_provenance.get("source") == "formal_run_manifests"
        and int(p3_browser_provenance.get("completed_manifest_count", -1)) == 54
        and len(p3_browser_provenance.get("source_manifests", [])) == 54
        and bool(p3_browser.get("browser_executable"))
        and bool(p3_browser.get("browser_version"))
        and bool(p3_browser.get("browser_executable_sha256"))
        and bool(p3_browser.get("browser_tree_sha256"))
        and int(p3_browser.get("browser_tree_file_count", 0)) == 273
        and int(p3_browser.get("browser_tree_total_bytes", 0)) == 501_388_593
        and bool(p3_browser.get("miniwob_plusplus_commit"))
        and bool(p3_browser.get("task_validation", {}).get("ok"))
        and not p3_browser.get("task_validation", {}).get("missing")
        and int(p3_browser.get("task_validation", {}).get("n_registered", 0)) > 0
        and int(p3_browser.get("independent_envs_per_task", -1)) == 4
    )

    requirements: list[dict[str, Any]] = []
    requirements.append(
        _requirement(
            name="private_consolidation_separates_sharing",
            complete=controls_total == 25 and private_count == 5 and controls_complete,
            progress=private_count > 0 or controls_total > 0,
            evidence={
                "controls_results": controls_total,
                "private_results": private_count,
                "controls_evidence_status": sections.get("epsilon_controls", {}).get(
                    "status", "missing"
                ),
            },
        )
    )
    requirements.append(
        _requirement(
            name="fixed_and_exact_pool_size_controls",
            complete=(
                controls_total == 25
                and cap14_count == 5
                and zeta_count == 5
                and controls_complete
                and zeta_complete
                and zeta_exact_yoke_evaluable
            ),
            progress=cap14_count > 0 or zeta_count > 0 or controls_total > 0,
            evidence={
                "cap14_results": cap14_count,
                "zeta_results": zeta_count,
                "zeta_evidence_status": sections.get(
                    "zeta_exact_supply_yoke", {}
                ).get("status", "missing"),
                "zeta_decision": zeta_manifest.get("decision", "missing"),
                "zeta_manipulation_checks": (
                    f"{zeta_manipulation_passed}/{len(zeta_manipulation_checks)}"
                ),
            },
        )
    )
    requirements.append(
        _requirement(
            name="diversity_aware_retrieval",
            complete=(
                controls_total == 25
                and mmr_count == 5
                and controls_complete
                and claims.get("status") == "claim_decisions_ready"
                and "mmr_vs_consolidated" in claims
            ),
            progress=mmr_count > 0 or controls_total > 0,
            evidence={
                "mmr_results": mmr_count,
                "claim_decisions": claims.get("status", "missing"),
            },
        )
    )
    requirements.append(
        _requirement(
            name="parameter_sensitivity_envelope",
            complete=(
                sensitivity_count == len(SENSITIVITY_ARMS) * 3
                and sensitivity_complete
                and sensitivity_manifest.get("analysis_method")
                == "seed_clustered_paired_bootstrap"
            ),
            progress=sensitivity_count > 0 or sensitivity_dir.exists(),
            evidence={
                "results": sensitivity_count,
                "expected": len(SENSITIVITY_ARMS) * 3,
                "evidence_status": sections.get("epsilon_sensitivity", {}).get(
                    "status", "missing"
                ),
            },
        )
    )
    hierarchical_complete = (
        controls_complete
        and sensitivity_complete
        and zeta_complete
        and controls_manifest.get("analysis_method") == "seed_clustered_paired_bootstrap"
        and sensitivity_manifest.get("analysis_method")
        == "seed_clustered_paired_bootstrap"
        and zeta_manifest.get("analysis_method") == "seed_clustered_paired_bootstrap"
        and bool(controls_manifest.get("per_seed_effects"))
        and bool(sensitivity_manifest.get("per_seed_effects"))
        and bool(zeta_manifest.get("per_seed_effects"))
        and appendix_path.exists()
    )
    requirements.append(
        _requirement(
            name="seed_level_and_hierarchical_statistics",
            complete=hierarchical_complete,
            progress=(
                (root / "sec" / "maze_stats.py").exists()
                and (root / "sec" / "epsilon_evidence.py").exists()
            ),
            evidence={
                "controls_method": controls_manifest.get(
                    "analysis_method", "missing"
                ),
                "sensitivity_method": sensitivity_manifest.get(
                    "analysis_method", "missing"
                ),
                "zeta_method": zeta_manifest.get("analysis_method", "missing"),
                "appendix_generated": appendix_path.exists(),
            },
        )
    )
    formal_loop = bool(
        re.search(r"\\paragraph\{Operational loop metrics\.\}", tex)
        and re.search(r"cycle length", tex, flags=re.IGNORECASE)
    )
    formal_stagnation = bool(
        re.search(r"Route-level\s+stagnation\s+is", tex, flags=re.IGNORECASE)
        and "\\mathbf{1}" in tex
    )
    requirements.append(
        _requirement(
            name="formal_loop_and_stagnation_definitions",
            complete=formal_loop and formal_stagnation,
            progress=formal_loop or formal_stagnation,
            evidence={
                "formal_loop": formal_loop,
                "formal_stagnation": formal_stagnation,
                "tex": str(tex_path),
            },
        )
    )
    requirements.append(
        _requirement(
            name="realistic_tool_or_web_task_boundary",
            complete=(
                p3_count == 54
                and p3_primary_complete
                and p3_append_complete
                and p3_runtime_source_complete
                and p3_runtime_source_current["all_match"]
                and p3_environment_complete
                and revision.get("p3_reports_same_quality") is True
                and revision.get("p3_quality_clear") is True
                and claims.get("status") == "claim_decisions_ready"
                and claims.get("p3", {}).get("interpretation")
                in {
                    "scoped_six_family_replication",
                    "not_detected_under_frozen_design",
                }
            ),
            progress=p3_count > 0,
            evidence={
                "p3_results": p3_count,
                "expected": 54,
                "primary_status": sections.get("p3_primary", {}).get(
                    "status", "missing"
                ),
                "quality_clear": revision.get("p3_quality_clear", False),
                "runtime_source_hashes_recorded_in_final_gate": (
                    p3_runtime_source_complete
                ),
                "current_runtime_source_hashes_match": (
                    p3_runtime_source_current["all_match"]
                ),
                "current_runtime_source_hashes": (
                    f"{p3_runtime_source_current['matched_count']}/"
                    f"{p3_runtime_source_current['file_count']}"
                ),
                "current_runtime_source_failures": p3_runtime_source_current[
                    "failures"
                ],
                "environment_source": p3_current_provenance.get(
                    "source", "missing"
                ),
                "environment_manifests": p3_current_provenance.get(
                    "completed_manifest_count", 0
                ),
                "browser_version": p3_current_browser.get(
                    "browser_version", "missing"
                ),
                "registered_tasks": p3_current_browser.get(
                    "task_validation", {}
                ).get("n_registered", 0),
                "independent_envs_per_task": p3_current_browser.get(
                    "independent_envs_per_task", "missing"
                ),
                "generated_environment_matches_current": (
                    p3_environment_matches_current
                ),
                "current_environment_error": (
                    p3_current_environment_error or None
                ),
                "interpretation": claims.get("p3", {}).get(
                    "interpretation", "missing"
                ),
            },
        )
    )
    related_work_complete = bool(
        re.search(r"Applicability and governance controls", tex, flags=re.IGNORECASE)
        and all(
            key in tex
            for key in [
                "lu2026tag",
                "kumar2026memarchitect",
                "cai2026proactagent",
                "he2026memoryarena",
                "kagaya2024rap",
            ]
        )
        and all(
            key in bib
            for key in [
                "lu2026tag",
                "kumar2026memarchitect",
                "cai2026proactagent",
                "he2026memoryarena",
                "kagaya2024rap",
            ]
        )
    )
    requirements.append(
        _requirement(
            name="memory_governance_related_work",
            complete=related_work_complete,
            progress="governance" in tex.lower(),
            evidence={
                "tex_section_present": "Applicability and governance controls" in tex,
                "citations_present": related_work_complete,
            },
        )
    )
    manuscript_complete = (
        manuscript_audit.get("status") == "complete"
        and paper_results.get("status") == "paper_results_generated"
        and claims.get("status") == "claim_decisions_ready"
    )
    requirements.append(
        _requirement(
            name="outcome_bounded_manuscript_revision",
            complete=manuscript_complete,
            progress=paper_results_path.exists() or claim_path.exists(),
            evidence={
                "paper_results": paper_results.get("status", "missing"),
                "claim_decisions": claims.get("status", "missing"),
                "manuscript_audit": manuscript_audit.get("status", "missing"),
            },
        )
    )
    pdf_complete = (
        manuscript_audit.get("status") == "complete"
        and render_audit.get("status") == "visual_audit_complete"
        and supplement_render_audit.get("status") == "visual_audit_complete"
        and checklist_report.get("status") == "checklist_ready"
        and checklist_render_audit.get("status") == "visual_audit_complete"
        and environment_manifest.get("status") == "environment_manifest_ready"
        and pdf_path.exists()
        and supplement_tex_path.exists()
        and supplement_pdf_path.exists()
        and checklist_tex_path.exists()
        and checklist_pdf_path.exists()
    )
    requirements.append(
        _requirement(
            name="compiled_and_visually_audited_pdf",
            complete=pdf_complete,
            progress=pdf_path.exists(),
            evidence={
                "pdf_exists": pdf_path.exists(),
                "supplement_tex_exists": supplement_tex_path.exists(),
                "supplement_pdf_exists": supplement_pdf_path.exists(),
                "checklist_tex_exists": checklist_tex_path.exists(),
                "checklist_pdf_exists": checklist_pdf_path.exists(),
                "render_audit": render_audit.get("status", "missing"),
                "supplement_render_audit": supplement_render_audit.get(
                    "status", "missing"
                ),
                "checklist_report": checklist_report.get("status", "missing"),
                "checklist_render_audit": checklist_render_audit.get(
                    "status", "missing"
                ),
                "environment_manifest": environment_manifest.get(
                    "status", "missing"
                ),
                "manuscript_audit": manuscript_audit.get("status", "missing"),
            },
        )
    )

    overall = (
        "complete"
        if requirements and all(row["status"] == "complete" for row in requirements)
        else "incomplete"
    )
    result = {
        "status": overall,
        "requirement_count": len(requirements),
        "complete_count": sum(
            1 for row in requirements if row["status"] == "complete"
        ),
        "requirements": requirements,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "goal_evidence_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Goal Evidence Audit",
        "",
        f"Status: **{overall}**",
        f"Complete requirements: **{result['complete_count']}/{len(requirements)}**",
        "",
        "| requirement | status | evidence |",
        "|---|---|---|",
    ]
    for row in requirements:
        evidence = json.dumps(row["evidence"], ensure_ascii=False).replace("|", "\\|")
        lines.append(f"| {row['name']} | {row['status']} | `{evidence}` |")
    lines.append("")
    (out_dir / "goal_evidence_audit.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the full reviewer-driven manuscript-strengthening goal."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-dir", default="runs_goal_evidence_audit")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_goal_evidence_audit(
        root=Path(args.root).resolve(),
        out_dir=Path(args.out_dir),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
