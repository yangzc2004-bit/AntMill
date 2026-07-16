from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from .manuscript_revision_audit import (
    REQUIRED_MAIN_GENERATED_INPUTS,
    REQUIRED_SUPPLEMENT_GENERATED_INPUTS,
    build_manuscript_revision_audit,
)


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_pdf(
    path: Path,
    text: str,
    *,
    page_count: int = 1,
    text_page: int = 1,
    text_y: int = 720,
) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    for page_number in range(1, page_count + 1):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )
        if page_number == text_page:
            stream = DecodedStreamObject()
            escaped = (
                text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            )
            stream.set_data(
                f"BT /F1 12 Tf 72 {text_y} Td ({escaped}) Tj ET".encode("ascii")
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer.write(str(path))


def _render_record(pdf: Path) -> dict:
    page_count = len(PdfReader(str(pdf)).pages)
    return {
        "status": "visual_audit_complete",
        "pdf_sha256": _sha256(pdf),
        "page_count": page_count,
        "rendered_page_count": page_count,
        "visual_checks": {
            "all_pages_rendered": True,
            "no_text_or_table_clipping": True,
            "no_overlapping_elements": True,
            "figures_and_tables_legible": True,
            "captions_match_content": True,
        },
    }


def _fixture(root: Path) -> dict[str, Path]:
    generated = root / "paper_draft" / "generated" / "revision_results"
    generated.mkdir(parents=True)
    source = root / "evidence.json"
    _write_json(source, {"frozen": True})
    generated_files = {}
    generated_content = {
        "mechanism_controls.tex": (
            "seed-clustered 95\\% bootstrap CIs. Positive success is better. "
            "Terminal round $t=5$; five seeds per contrast. "
            "Intervals are not multiplicity-adjusted.\n"
        ),
        "sensitivity_envelope.tex": (
            "seed-clustered 95\\% bootstrap CIs. Positive success is better. "
            "Terminal round $t=5$; three seeds per contrast. "
            "Intervals are not multiplicity-adjusted.\n"
        ),
        "miniwob_boundary.tex": (
            "% MiniWoB behavioral estimates withheld because formal data quality "
            "is not clear.\n"
        ),
        "appendix_diagnostics.tex": (
            "validated runs/total runs\n"
            "Config/Manifest/Env.\n"
            "all-run validation gates\n"
            "MiniWoB runtime:\n"
            "Exhausted\n"
            "Route LLM all/final\n"
            "Non-HO exhausted calls\n"
            "LLM path\n"
        ),
    }
    for name in [
        "mechanism_controls.tex",
        "sensitivity_envelope.tex",
        "miniwob_boundary.tex",
        "appendix_heterogeneity.tex",
        "appendix_diagnostics.tex",
        "revision_results.md",
        "revision_macros.tex",
        "macro_manifest.json",
    ]:
        path = generated / name
        path.write_text(generated_content.get(name, f"% {name}\n"), encoding="utf-8")
        generated_files[name] = {"path": str(path), "sha256": _sha256(path)}
    macro_tex = generated / "revision_macros.tex"
    macro_records = [
        {
            "macro": "RevSharedPrivateLoopRateMean",
            "value": "+0.0100",
            "contrast": "shared_consolidated_minus_private_consolidated",
            "metric": "looped",
            "field": "Mean",
        },
        {
            "macro": "RevSharedPrivateLoopRateCILo",
            "value": "-0.0100",
            "contrast": "shared_consolidated_minus_private_consolidated",
            "metric": "looped",
            "field": "CILo",
        },
        {
            "macro": "RevSharedPrivateLoopRateCIHi",
            "value": "+0.0300",
            "contrast": "shared_consolidated_minus_private_consolidated",
            "metric": "looped",
            "field": "CIHi",
        },
        {
            "macro": "RevZetaConsolidatedLoopRateMean",
            "value": "+0.0100",
            "contrast": "zeta_exact_yoke_minus_epsilon_shared_consolidated",
            "metric": "looped",
            "field": "Mean",
        },
        {
            "macro": "RevZetaConsolidatedLoopRateCILo",
            "value": "-0.0100",
            "contrast": "zeta_exact_yoke_minus_epsilon_shared_consolidated",
            "metric": "looped",
            "field": "CILo",
        },
        {
            "macro": "RevZetaConsolidatedLoopRateCIHi",
            "value": "+0.0300",
            "contrast": "zeta_exact_yoke_minus_epsilon_shared_consolidated",
            "metric": "looped",
            "field": "CIHi",
        },
        {
            "macro": "RevSensitivityLoopRatePositiveDetectedSettings",
            "value": "none",
            "contrast": "epsilon_sensitivity_envelope",
            "metric": "looped",
            "field": "PositiveDetectedSettings",
        },
        {
            "macro": "RevSensitivityLoopRateNegativeDetectedSettings",
            "value": "k=3",
            "contrast": "epsilon_sensitivity_envelope",
            "metric": "looped",
            "field": "NegativeDetectedSettings",
        },
        {
            "macro": "RevSensitivityLoopRateNotDetectedSettings",
            "value": "k=10",
            "contrast": "epsilon_sensitivity_envelope",
            "metric": "looped",
            "field": "NotDetectedSettings",
        },
    ]
    macro_tex.write_text(
        "\n".join(
            f"\\newcommand{{\\{row['macro']}}}{{{row['value']}}}"
            for row in macro_records
        )
        + "\n",
        encoding="utf-8",
    )
    macro_manifest = generated / "macro_manifest.json"
    _write_json(
        macro_manifest,
        {
            "macro_count": len(macro_records),
            "records": macro_records,
        },
    )
    generated_files["revision_macros.tex"] = {
        "path": str(macro_tex),
        "sha256": _sha256(macro_tex),
    }
    generated_files["macro_manifest.json"] = {
        "path": str(macro_manifest),
        "sha256": _sha256(macro_manifest),
    }

    gate = root / "revision_gate.json"
    _write_json(
        gate,
        {
            "status": "ready_for_paper_revision",
            "data_complete": True,
            "p3_quality_clear": False,
            "p3_reports_same_quality": True,
            "sections": {
                "p3_primary": {"decision": "p3_not_detected_or_underpowered"},
                "zeta_exact_supply_yoke": {"decision": "zeta_supply_yoke_evaluable"},
            },
        },
    )
    manifest = generated / "paper_results_manifest.json"
    _write_json(
        manifest,
        {
            "source_hashes": {
                "evidence": {"path": str(source), "sha256": _sha256(source)}
            },
            "generated_hashes": generated_files,
            "revision_macro_count": len(macro_records),
            "gates": {"p3_quality_clear": False},
        },
    )
    claim_decisions = generated / "claim_decisions.json"
    _write_json(
        claim_decisions,
        {
            "status": "claim_decisions_ready",
            "rules_provenance": {"match": True},
            "source_hashes": {
                "evidence": {"path": str(source), "sha256": _sha256(source)}
            },
            "shared_vs_private": {
                "endpoints": {
                    "looped": {"classification": "not_detected"}
                }
            },
            "mmr_vs_consolidated": {
                "manipulation": {"status": "direction_not_observed"},
                "endpoint_specific_mitigation_allowed": [],
            },
            "zeta_exact_yoke": {
                "interpretation": "candidate_supply_size_remains_plausible"
            },
        },
    )
    tex = root / "paper_draft" / "paper.tex"
    main_inputs = "\n".join(
        f"\\input{{{path}}}" for path in REQUIRED_MAIN_GENERATED_INPUTS
    )
    tex.write_text(
        "\n".join(
            [
                "\\begin{abstract}",
                "Bounded result for the tested shared reviewer-consolidation protocol.",
                "The fresh study does not isolate a shared-specific loop effect.",
                "Strategy-supply compression remains a candidate channel, not an "
                "established cause.",
                "The MiniWoB formal evaluation is not behaviorally interpretable "
                "because of a quality warning.",
                "\\end{abstract}",
                "\\paragraph{Operational loop metrics.} A cycle length test.",
                "Route-level stagnation is formally defined.",
                "The private-consolidation result, exact-size yoke, MMR, sensitivity,",
                "seed-clustered analysis, and MiniWoB boundary are reported.",
                "MMR uses a 0.70 relevance and 0.30 redundancy objective with "
                "cosine similarity over deterministic token-hashing embeddings.",
                "The MMR control uses deterministic token-hashing cosine rather "
                "than learned semantic embeddings; it tests one reproducible "
                "lexical diversity policy, not MMR or xQuAD generally.",
                "Private consolidation uses four per-agent reviewer calls per "
                "training maze, versus one joint shared reviewer call. This is "
                "a protocol-level contrast and does not isolate sharing from "
                "reviewer-call count or total operation opportunity.",
                "The shared-append append/agree protocol treats a near-duplicate "
                "addition as an agreement upvote, with no joint reviewer-issued "
                "EDIT or DOWNVOTE operation.",
                "For MiniWoB, loop/stall burden marks either the same normalized "
                "action from a previously seen hashed browser state or an "
                "unsuccessful route without an environment termination signal. "
                "The repeated-action and nontermination components are reported "
                "separately, and this task-specific measure is distinct from the "
                "maze position-cycle detector.",
                "Any terminal route error or unresolved active-memory LLM error "
                "withholds behavioral interpretation. A nonterminal frozen-arm "
                "error is disclosed separately because the frozen arm never "
                "injects its written memory.",
                "Cap-14 is a fixed terminal-capacity control, not an exact "
                "round-by-round yoke.",
                "For the exact-size yoke, item content and write dynamics remain unequal.",
                "The sensitivity suite is a descriptive envelope; no best setting "
                "is selected.",
                "Across the eight prespecified sensitivity settings, loop rate is "
                "higher than reference for "
                "\\RevSensitivityLoopRatePositiveDetectedSettings{}, lower for "
                "\\RevSensitivityLoopRateNegativeDetectedSettings{}, and not "
                "detected for "
                "\\RevSensitivityLoopRateNotDetectedSettings{}.",
                "Strategy-supply compression remains a correlate and candidate "
                "channel, not an established cause.",
                "The tested shared reviewer-consolidation protocol is scoped.",
                "The fresh study does not isolate a shared-specific loop effect.",
                "The loop contrast is "
                "\\RevSharedPrivateLoopRateMean{} with CI "
                "[\\RevSharedPrivateLoopRateCILo{},"
                "\\RevSharedPrivateLoopRateCIHi{}].",
                "MMR does not establish its intended diversity manipulation.",
                "The exact-size yoke leaves candidate-supply size plausible.",
                "The exact-size loop contrast is "
                "\\RevZetaConsolidatedLoopRateMean{} with CI "
                "[\\RevZetaConsolidatedLoopRateCILo{},"
                "\\RevZetaConsolidatedLoopRateCIHi{}].",
                main_inputs,
                "\\section{Limitations}",
                "MiniWoB was not evaluable because of a formal quality warning.",
                "\\section{Conclusion}",
                "Bounded protocol-level conclusion for the tested shared "
                "reviewer-consolidation protocol under the tested retrieval "
                "capacity, reviewer budget, and merge policy. The fresh study "
                "does not isolate a shared-specific loop effect. Strategy-supply "
                "compression remains a candidate channel, not an established "
                "cause. The exact-size yoke leaves candidate-supply size plausible.",
                "The MiniWoB formal evaluation is not behaviorally interpretable "
                "because of a quality warning.",
                "\\paragraph{Reproducibility}",
                "\\bibliography{paper}",
            ]
        ),
        encoding="utf-8",
    )
    supplement_tex = root / "paper_draft" / "supplement.tex"
    supplement_inputs = "\n".join(
        f"\\input{{{path}}}" for path in REQUIRED_SUPPLEMENT_GENERATED_INPUTS
    )
    supplement_tex.write_text(
        "\n".join(
            [
                "\\begin{document}",
                "\\section{Sensitivity Envelope}",
                "\\section{Seed-Level and Task-Family Heterogeneity}",
                "\\section{Exact Supply-Yoke Checks, Data Quality, and Provenance}",
                supplement_inputs,
                "\\end{document}",
            ]
        ),
        encoding="utf-8",
    )
    checklist_template = root / "checklist_template.tex"
    checklist_template.write_text("% frozen template\n", encoding="utf-8")
    checklist_responses = root / "checklist_responses.json"
    _write_json(checklist_responses, {"status": "finalized"})
    checklist_tex = root / "paper_draft" / "checklist.tex"
    checklist_tex.write_text(
        "\\question{Fixture}{(yes/no)}\nyes\n",
        encoding="utf-8",
    )
    checklist_report = generated / "reproducibility_checklist_report.json"
    _write_json(
        checklist_report,
        {
            "status": "checklist_ready",
            "specification_status": "finalized",
            "question_count": 31,
            "template": {
                "path": str(checklist_template),
                "sha256": _sha256(checklist_template),
            },
            "responses": {
                "path": str(checklist_responses),
                "sha256": _sha256(checklist_responses),
            },
            "output": {
                "path": str(checklist_tex),
                "sha256": _sha256(checklist_tex),
            },
        },
    )
    environment_tex = generated / "environment_manifest.tex"
    environment_tex.write_text(
        "\\begin{table*}Environment\\end{table*}\n",
        encoding="utf-8",
    )
    formal_browser_environment = {
        "miniwob_plusplus_commit": "fixture",
        "primary_tasks": ["fixture-task"],
        "replacement_tasks": [],
        "python_version": "3.12",
        "browser_executable": "fixture-browser",
        "browser_version": "1.2.3",
        "browser_executable_sha256": "fixture-executable-sha256",
        "browser_tree_root": "fixture-browser-root",
        "browser_tree_sha256": "fixture-tree-sha256",
        "browser_tree_file_count": 273,
        "browser_tree_total_bytes": 501388593,
        "versions": {
            "browsergym-core": "1",
            "browsergym-miniwob": "1",
            "gymnasium": "1",
            "playwright": "1",
        },
        "miniwob_url": "file:///fixture/",
        "task_validation": {
            "ok": True,
            "missing": [],
            "n_registered": 189,
        },
        "independent_envs_per_task": 4,
    }
    environment_sources = []
    for index in range(54):
        run_dir = root / "runs_miniwob_gamma_p3e" / f"condition_{index}"
        _write_json(run_dir / "result.json", {"index": index})
        source_path = run_dir / "manifest.json"
        _write_json(
            source_path,
            {
                "phase": "gamma_p3_formal",
                "miniwob": formal_browser_environment,
            },
        )
        environment_sources.append(
            {"path": str(source_path), "sha256": _sha256(source_path)}
        )
    environment_manifest = generated / "environment_manifest.json"
    _write_json(
        environment_manifest,
        {
            "status": "environment_manifest_ready",
            "system": {
                "cpu_model": "fixture CPU",
                "python_version": "3.12",
            },
            "browser_environment": {
                **formal_browser_environment,
                "provenance": {
                    "source": "formal_run_manifests",
                    "completed_manifest_count": 54,
                    "source_manifests": environment_sources,
                },
            },
            "tex": {
                "path": str(environment_tex),
                "size_bytes": environment_tex.stat().st_size,
                "sha256": _sha256(environment_tex),
            },
        },
    )
    bib = root / "paper_draft" / "paper.bib"
    bib.write_text("@misc{x, title={x}}\n", encoding="utf-8")
    pdf = root / "paper_draft" / "paper.pdf"
    _write_pdf(pdf, "References")
    supplement_pdf = root / "paper_draft" / "supplement.pdf"
    _write_pdf(supplement_pdf, "Supplementary Material")
    checklist_pdf = root / "paper_draft" / "checklist.pdf"
    _write_pdf(checklist_pdf, "Reproducibility Checklist")
    newest_input = max(
        [
            tex.stat().st_mtime,
            supplement_tex.stat().st_mtime,
            checklist_tex.stat().st_mtime,
            checklist_report.stat().st_mtime,
            environment_manifest.stat().st_mtime,
            environment_tex.stat().st_mtime,
            bib.stat().st_mtime,
            manifest.stat().st_mtime,
            claim_decisions.stat().st_mtime,
        ]
        + [Path(record["path"]).stat().st_mtime for record in generated_files.values()]
    )
    os.utime(pdf, (newest_input + 2, newest_input + 2))
    os.utime(supplement_pdf, (newest_input + 2, newest_input + 2))
    os.utime(checklist_pdf, (newest_input + 2, newest_input + 2))
    render = generated / "final_render_audit.json"
    _write_json(render, _render_record(pdf))
    supplement_render = generated / "final_supplement_render_audit.json"
    _write_json(supplement_render, _render_record(supplement_pdf))
    checklist_render = generated / "final_checklist_render_audit.json"
    _write_json(checklist_render, _render_record(checklist_pdf))
    return {
        "tex": tex,
        "supplement_tex": supplement_tex,
        "checklist_tex": checklist_tex,
        "bib": bib,
        "pdf": pdf,
        "supplement_pdf": supplement_pdf,
        "checklist_pdf": checklist_pdf,
        "gate": gate,
        "manifest": manifest,
        "claim_decisions": claim_decisions,
        "checklist_report": checklist_report,
        "environment_manifest": environment_manifest,
        "render": render,
        "supplement_render": supplement_render,
        "checklist_render": checklist_render,
    }


def _audit(root: Path, paths: dict[str, Path]) -> dict:
    return build_manuscript_revision_audit(
        tex_path=paths["tex"],
        supplement_tex_path=paths["supplement_tex"],
        checklist_tex_path=paths["checklist_tex"],
        bib_path=paths["bib"],
        pdf_path=paths["pdf"],
        supplement_pdf_path=paths["supplement_pdf"],
        checklist_pdf_path=paths["checklist_pdf"],
        revision_gate_path=paths["gate"],
        paper_results_manifest_path=paths["manifest"],
        claim_decisions_path=paths["claim_decisions"],
        checklist_report_path=paths["checklist_report"],
        environment_manifest_path=paths["environment_manifest"],
        render_audit_path=paths["render"],
        supplement_render_audit_path=paths["supplement_render"],
        checklist_render_audit_path=paths["checklist_render"],
        out_dir=root / "audit",
    )


def _add_macro_records(
    paths: dict[str, Path],
    records: list[dict],
) -> None:
    paper_manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    macro_tex_path = Path(
        paper_manifest["generated_hashes"]["revision_macros.tex"]["path"]
    )
    macro_manifest_path = Path(
        paper_manifest["generated_hashes"]["macro_manifest.json"]["path"]
    )
    macro_manifest = json.loads(
        macro_manifest_path.read_text(encoding="utf-8")
    )
    merged = [dict(row) for row in macro_manifest["records"]]
    existing = {str(row["macro"]) for row in merged}
    for record in records:
        if str(record["macro"]) in existing:
            raise AssertionError(f"Duplicate fixture macro: {record['macro']}")
        merged.append(dict(record))
        existing.add(str(record["macro"]))
    macro_manifest["records"] = merged
    macro_manifest["macro_count"] = len(merged)
    _write_json(macro_manifest_path, macro_manifest)
    macro_tex_path.write_text(
        "\n".join(
            f"\\newcommand{{\\{row['macro']}}}{{{row['value']}}}"
            for row in merged
        )
        + "\n",
        encoding="utf-8",
    )
    paper_manifest["revision_macro_count"] = len(merged)
    paper_manifest["generated_hashes"]["revision_macros.tex"]["sha256"] = (
        _sha256(macro_tex_path)
    )
    paper_manifest["generated_hashes"]["macro_manifest.json"]["sha256"] = (
        _sha256(macro_manifest_path)
    )
    _write_json(paths["manifest"], paper_manifest)


def _set_p3_pass_fixture(paths: dict[str, Path]) -> None:
    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    gate["p3_quality_clear"] = True
    gate["sections"]["p3_primary"]["decision"] = "p3_phenomenon_pass"
    _write_json(paths["gate"], gate)

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["gates"]["p3_quality_clear"] = True
    p3_table = (
        "Consolidated family; paired routes per endpoint; quality clear; "
        "terminal $t=3$; six-family block is descriptive. "
        "Only failure-penalized cost and loop/stall burden determine the gate.\n"
    )
    p3_path = Path(
        manifest["generated_hashes"]["miniwob_boundary.tex"]["path"]
    )
    p3_path.write_text(p3_table, encoding="utf-8")
    manifest["generated_hashes"]["miniwob_boundary.tex"]["sha256"] = _sha256(
        p3_path
    )
    _write_json(paths["manifest"], manifest)
    _add_macro_records(
        paths,
        [
            {
                "macro": "RevPThreeConsolidatedFailurePenalizedCostMean",
                "value": "+0.1000",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "failure_penalized_cost",
                "field": "Mean",
            },
            {
                "macro": "RevPThreeConsolidatedFailurePenalizedCostCILo",
                "value": "+0.0100",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "failure_penalized_cost",
                "field": "CILo",
            },
            {
                "macro": "RevPThreeConsolidatedFailurePenalizedCostCIHi",
                "value": "+0.1900",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "failure_penalized_cost",
                "field": "CIHi",
            },
            {
                "macro": "RevPThreeConsolidatedLoopStallBurdenMean",
                "value": "+0.1000",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "loop_stall_burden",
                "field": "Mean",
            },
            {
                "macro": "RevPThreeConsolidatedLoopStallBurdenCILo",
                "value": "+0.0100",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "loop_stall_burden",
                "field": "CILo",
            },
            {
                "macro": "RevPThreeConsolidatedLoopStallBurdenCIHi",
                "value": "+0.1900",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "loop_stall_burden",
                "field": "CIHi",
            },
            {
                "macro": "RevPThreeConsolidatedFailurePenalizedCostSeedSigns",
                "value": "+,+,-",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "failure_penalized_cost",
                "field": "SeedSigns",
            },
            {
                "macro": "RevPThreeConsolidatedLoopStallBurdenSeedSigns",
                "value": "+,-,+",
                "contrast": "p3_consolidated_minus_frozen",
                "metric": "loop_stall_burden",
                "field": "SeedSigns",
            },
        ],
    )

    tex = paths["tex"].read_text(encoding="utf-8")
    tex = tex.replace(
        "The MiniWoB formal evaluation is not behaviorally interpretable "
        "because of a quality warning.\n",
        "",
    )
    tex = tex.replace(
        "\\end{abstract}",
        "In the six-family MiniWoB evaluation, the equal-family pooled "
        "failure-penalized-cost and loop/stall gate passes.\n"
        "The pooled failure-cost effect is "
        "\\RevPThreeConsolidatedFailurePenalizedCostMean{} with CI "
        "[\\RevPThreeConsolidatedFailurePenalizedCostCILo{},"
        "\\RevPThreeConsolidatedFailurePenalizedCostCIHi{}], and loop/stall "
        "burden is \\RevPThreeConsolidatedLoopStallBurdenMean{} with CI "
        "[\\RevPThreeConsolidatedLoopStallBurdenCILo{},"
        "\\RevPThreeConsolidatedLoopStallBurdenCIHi{}]. "
        "Seed 0/1/2 signs are "
        "\\RevPThreeConsolidatedFailurePenalizedCostSeedSigns{} for failure "
        "cost and \\RevPThreeConsolidatedLoopStallBurdenSeedSigns{} for "
        "loop/stall burden.\n"
        "\\end{abstract}",
        1,
    )
    tex = tex.replace(
        "MiniWoB was not evaluable because of a formal quality warning.",
        "MiniWoB per-family effects remain heterogeneous; the pooled pass is "
        "not uniform across tasks.",
    )
    tex = tex.replace(
        "\\paragraph{Reproducibility}",
        "Across six tested MiniWoB task families, the equal-family pooled "
        "failure-penalized-cost and loop/stall gate passes.\n"
        "\\paragraph{Reproducibility}",
        1,
    )
    paths["tex"].write_text(tex, encoding="utf-8")

    newest = max(
        paths["tex"].stat().st_mtime,
        paths["manifest"].stat().st_mtime,
        p3_path.stat().st_mtime,
    )
    for key in ["pdf", "supplement_pdf", "checklist_pdf"]:
        os.utime(paths[key], (newest + 2, newest + 2))


def _set_p3_nonpass_fixture(paths: dict[str, Path]) -> None:
    _set_p3_pass_fixture(paths)
    gate = json.loads(paths["gate"].read_text(encoding="utf-8"))
    gate["sections"]["p3_primary"]["decision"] = (
        "p3_not_detected_or_underpowered"
    )
    _write_json(paths["gate"], gate)
    tex = paths["tex"].read_text(encoding="utf-8")
    tex = tex.replace(
        "In the six-family MiniWoB evaluation, the equal-family pooled "
        "failure-penalized-cost and loop/stall gate passes.\n",
        "In MiniWoB, task-family replication was not detected under the "
        "frozen design and sample size.\n",
        1,
    )
    tex = tex.replace(
        "MiniWoB per-family effects remain heterogeneous; the pooled "
        "pass is not uniform across tasks.",
        "MiniWoB task-family replication was not detected under the frozen "
        "design and sample size.",
    )
    tex = tex.replace(
        "Across six tested MiniWoB task families, the equal-family pooled "
        "failure-penalized-cost and loop/stall gate passes.",
        "MiniWoB task-family replication was not detected under the frozen "
        "design and sample size.",
    )
    paths["tex"].write_text(tex, encoding="utf-8")
    newest = max(
        paths["tex"].stat().st_mtime,
        paths["gate"].stat().st_mtime,
    )
    for key in ["pdf", "supplement_pdf", "checklist_pdf"]:
        os.utime(paths[key], (newest + 2, newest + 2))


def _set_mmr_mitigation_fixture(paths: dict[str, Path]) -> None:
    decisions = json.loads(paths["claim_decisions"].read_text(encoding="utf-8"))
    decisions["mmr_vs_consolidated"] = {
        "manipulation": {"status": "direction_observed"},
        "endpoint_specific_mitigation_allowed": ["looped"],
    }
    _write_json(paths["claim_decisions"], decisions)
    _add_macro_records(
        paths,
        [
            {
                "macro": "RevMmrConsolidatedLoopRateMean",
                "value": "-0.0400",
                "contrast": "mmr_minus_shared_consolidated",
                "metric": "looped",
                "field": "Mean",
            },
            {
                "macro": "RevMmrConsolidatedLoopRateCILo",
                "value": "-0.0800",
                "contrast": "mmr_minus_shared_consolidated",
                "metric": "looped",
                "field": "CILo",
            },
            {
                "macro": "RevMmrConsolidatedLoopRateCIHi",
                "value": "-0.0100",
                "contrast": "mmr_minus_shared_consolidated",
                "metric": "looped",
                "field": "CIHi",
            },
        ],
    )
    paths["tex"].write_text(
        paths["tex"]
        .read_text(encoding="utf-8")
        .replace(
            "MMR does not establish its intended diversity manipulation.",
            "MMR shifts retrieval-diversity diagnostics in the intended "
            "direction and reduces loop rate by "
            "\\RevMmrConsolidatedLoopRateMean{} with CI "
            "[\\RevMmrConsolidatedLoopRateCILo{},"
            "\\RevMmrConsolidatedLoopRateCIHi{}].",
        ),
        encoding="utf-8",
    )
    newest = max(
        paths["tex"].stat().st_mtime,
        paths["claim_decisions"].stat().st_mtime,
    )
    for key in ["pdf", "supplement_pdf", "checklist_pdf"]:
        os.utime(paths[key], (newest + 2, newest + 2))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-audit-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        result = _audit(root, paths)
        assert result["status"] == "complete", result["failed_checks"]

        paths["tex"].write_text(
            paths["tex"].read_text(encoding="utf-8") + "\nShared memory fails.\n",
            encoding="utf-8",
        )
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "banned_claim_absent:shared memory fails" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-macro-reference-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace("\\RevSharedPrivateLoopRateMean{}", "+0.0100"),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "key_fresh_narrative_uses_generated_macros"
            in result["failed_checks"]
        )

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-causality-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"].read_text(encoding="utf-8")
            + "\nStrategy-supply compression drives looping behavior.\n",
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "compression_causal_overclaim_absent" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-abstract-scope-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "Bounded result for the tested shared reviewer-consolidation protocol.",
                "Shared memory broadly degrades agent behavior.",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "abstract_protocol_scope" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-abstract-compression-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "Strategy-supply compression remains a candidate channel, "
                "not an established cause.",
                "Strategy-supply compression is observed.",
                1,
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "abstract_compression_causality_bounded"
            in result["failed_checks"]
        )

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-conclusion-conditions-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "under the tested retrieval capacity, reviewer budget, and "
                "merge policy",
                "under the tested settings",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "conclusion_protocol_conditions" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-zeta-conclusion-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        text = paths["tex"].read_text(encoding="utf-8")
        marker = "The exact-size yoke leaves candidate-supply size plausible."
        marker_index = text.rfind(marker)
        assert marker_index >= 0
        paths["tex"].write_text(
            text[:marker_index]
            + "The exact-size yoke is reported."
            + text[marker_index + len(marker) :],
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "zeta_claim_branch" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-stale-prose-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"].read_text(encoding="utf-8")
            + "\nWe include no completed browser or tool-workflow evaluation.\n",
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert any(
            name.startswith("stale_final_prose_absent:")
            for name in result["failed_checks"]
        )

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-cap14-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "Cap-14 is a fixed terminal-capacity control, not an exact "
                "round-by-round yoke.",
                "Cap-14 exactly matches pool size.",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "cap14_fixed_terminal_scope" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-private-budget-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "Private consolidation uses four per-agent reviewer calls per "
                "training maze, versus one joint shared reviewer call. This is "
                "a protocol-level contrast and does not isolate sharing from "
                "reviewer-call count or total operation opportunity.\n",
                "",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "shared_private_reviewer_allocation_caveat" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-append-agree-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "The shared-append append/agree protocol treats a near-duplicate "
                "addition as an agreement upvote, with no joint reviewer-issued "
                "EDIT or DOWNVOTE operation.\n",
                "The shared-append arm is shared but never merged.\n",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "append_agree_protocol_defined" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-mmr-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        _set_mmr_mitigation_fixture(paths)
        result = _audit(root, paths)
        assert result["status"] == "complete", result["failed_checks"]

        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "direction and reduces loop rate by ",
                "direction, but its behavioral result is reported elsewhere as ",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "mmr_claim_branch" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-sensitivity-selection-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "The sensitivity suite is a descriptive envelope; no best "
                "setting is selected.",
                "The sensitivity suite identifies the best setting.",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "sensitivity_descriptive_no_selection" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-sensitivity-branches-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "\\RevSensitivityLoopRateNotDetectedSettings{}",
                "k=10",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "key_fresh_narrative_uses_generated_macros"
            in result["failed_checks"]
        )
        assert "sensitivity_setting_branches_reported" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-supp-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["supplement_tex"].write_text(
            paths["supplement_tex"]
            .read_text(encoding="utf-8")
            .replace("generated/revision_results/sensitivity_envelope.tex", "missing.tex"),
            encoding="utf-8",
        )
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "supplement_tex_input:sensitivity_envelope.tex"
            in result["failed_checks"]
        )

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-fresh-control-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "The fresh study does not isolate a shared-specific loop effect.",
                "The study does not isolate a shared-specific loop effect.",
            ),
            encoding="utf-8",
        )
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "shared_private_claim_branch" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-shared-contradiction-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "\\paragraph{Reproducibility}",
                "Shared consolidation amplifies loops relative to private memory.\n"
                "\\paragraph{Reproducibility}",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "shared_private_contradiction_absent" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-p3-quality-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "MiniWoB was not evaluable because of a formal quality warning.",
                "MiniWoB was not detected or underpowered under the frozen design.",
            ),
            encoding="utf-8",
        )
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "p3_quality_warning_bounded_in_limitations"
            in result["failed_checks"]
        )

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-p3-nonpass-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        _set_p3_nonpass_fixture(paths)
        result = _audit(root, paths)
        assert result["status"] == "complete", result["failed_checks"]

        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "In MiniWoB, task-family replication was not detected under "
                "the frozen design and sample size.",
                "MiniWoB results are reported.",
                1,
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "p3_nonpass_bounded_in_abstract" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-p3-pass-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        _set_p3_pass_fixture(paths)
        result = _audit(root, paths)
        assert result["status"] == "complete", result["failed_checks"]

        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            + "\nThe effect replicates uniformly across all six MiniWoB task families.\n",
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "p3_pass_uniform_replication_claim_absent"
            in result["failed_checks"]
        )

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-p3-heterogeneity-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        _set_p3_pass_fixture(paths)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "MiniWoB per-family effects remain heterogeneous; the pooled "
                "pass is not uniform across tasks.",
                "MiniWoB pooled results are reported.",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "p3_pass_task_family_heterogeneity" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-p3-seed-signs-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        _set_p3_pass_fixture(paths)
        paths["tex"].write_text(
            paths["tex"]
            .read_text(encoding="utf-8")
            .replace(
                "\\RevPThreeConsolidatedLoopStallBurdenSeedSigns{}",
                "+,-,+",
            ),
            encoding="utf-8",
        )
        os.utime(paths["pdf"], (paths["tex"].stat().st_mtime + 2,) * 2)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert (
            "key_fresh_narrative_uses_generated_macros"
            in result["failed_checks"]
        )
        assert "p3_primary_seed_signs_reported" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-pages-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        _write_pdf(paths["pdf"], "References", page_count=9, text_page=9)
        _write_json(paths["render"], _render_record(paths["pdf"]))
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "technical_content_within_seven_pages" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-late-refs-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        _write_pdf(
            paths["pdf"],
            "References",
            page_count=8,
            text_page=8,
            text_y=300,
        )
        _write_json(paths["render"], _render_record(paths["pdf"]))
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "technical_content_within_seven_pages" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-checklist-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        report = json.loads(paths["checklist_report"].read_text(encoding="utf-8"))
        report["status"] = "checklist_provisional"
        report["specification_status"] = "provisional"
        _write_json(paths["checklist_report"], report)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "reproducibility_checklist_ready" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-environment-anonymity-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        environment = json.loads(
            paths["environment_manifest"].read_text(encoding="utf-8")
        )
        environment["system"]["python_executable"] = (
            "C:\\Users\\named-account\\python.exe"
        )
        _write_json(paths["environment_manifest"], environment)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "execution_environment_recorded" in result["failed_checks"]

    with tempfile.TemporaryDirectory(
        prefix="antmill-manuscript-environment-source-binding-"
    ) as raw:
        root = Path(raw)
        paths = _fixture(root)
        environment = json.loads(
            paths["environment_manifest"].read_text(encoding="utf-8")
        )
        environment["browser_environment"]["browser_version"] = "stale-version"
        _write_json(paths["environment_manifest"], environment)
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "execution_environment_recorded" in result["failed_checks"]

    with tempfile.TemporaryDirectory(prefix="antmill-manuscript-hash-") as raw:
        root = Path(raw)
        paths = _fixture(root)
        source = root / "evidence.json"
        source.write_text('{"changed": true}', encoding="utf-8")
        result = _audit(root, paths)
        assert result["status"] == "incomplete"
        assert "paper_result_source_hashes" in result["failed_checks"]
    print("selftest_manuscript_revision_audit OK")


if __name__ == "__main__":
    main()
