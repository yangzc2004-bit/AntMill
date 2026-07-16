from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader

from .environment_manifest import FORMAL_MINIWOB_FIELDS


REQUIRED_MAIN_GENERATED_INPUTS = [
    "generated/revision_results/revision_macros.tex",
    "generated/revision_results/mechanism_controls.tex",
    "generated/revision_results/miniwob_boundary.tex",
]
REQUIRED_SUPPLEMENT_GENERATED_INPUTS = [
    "generated/revision_results/revision_macros.tex",
    "generated/revision_results/sensitivity_envelope.tex",
    "generated/revision_results/appendix_heterogeneity.tex",
    "generated/revision_results/appendix_diagnostics.tex",
    "generated/revision_results/environment_manifest.tex",
]
REQUIRED_GENERATED_INPUTS = sorted(
    set(REQUIRED_MAIN_GENERATED_INPUTS + REQUIRED_SUPPLEMENT_GENERATED_INPUTS)
)
EXPECTED_GENERATED_HASH_NAMES = {
    "mechanism_controls.tex",
    "sensitivity_envelope.tex",
    "miniwob_boundary.tex",
    "appendix_heterogeneity.tex",
    "appendix_diagnostics.tex",
    "revision_results.md",
    "revision_macros.tex",
    "macro_manifest.json",
}
REQUIRED_MANUSCRIPT_MARKERS = {
    "formal_loop_definition": r"\\paragraph\{Operational loop metrics\.\}",
    "formal_stagnation_definition": r"Route-level\s+stagnation\s+is",
    "private_consolidation_result": r"private[- ]consolidat",
    "exact_size_yoke_result": r"(exact[- ]size|exact.*yoke|supply[- ]yoke)",
    "diversity_aware_result": r"\bMMR\b|diversity-aware",
    "sensitivity_result": r"\bsensitivit",
    "seed_clustered_analysis": r"seed-clustered",
    "miniwob_boundary": r"\bMiniWoB\b",
    "miniwob_loop_stall_definition": (
        r"For MiniWoB, loop/stall burden.{0,240}same normalized action"
        r".{0,180}hashed browser state.{0,240}(nontermination|"
        r"without an environment termination signal).{0,260}"
        r"(distinct|different).{0,100}maze position-cycle detector"
    ),
    "miniwob_llm_path_quality": (
        r"(terminal route error|terminal.*LLM error).{0,220}"
        r"(active-memory|active memory).{0,220}"
        r"(withhold|not behaviorally interpretable).{0,260}"
        r"(frozen arm|frozen-arm).{0,180}(never injects|not injected)"
    ),
    "bounded_protocol_language": r"tested shared reviewer-consolidation protocol",
}
BANNED_CLAIMS = [
    "shared memory fails",
    "consensus consolidation is generally harmful",
    "strategy compression causes looping",
    "generalizes to web agents",
]
STALE_FINAL_PROSE = [
    "we include no completed browser or tool-workflow evaluation",
    "we do not compare against deterministic compression or diversity-preserving retrieval baselines",
    "route-level bootstrap intervals quantify paired trajectory variation",
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


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _section(text: str, start_pattern: str, end_pattern: str | None = None) -> str:
    start = re.search(start_pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not start:
        return ""
    tail = text[start.end() :]
    if not end_pattern:
        return tail
    end = re.search(end_pattern, tail, flags=re.IGNORECASE | re.DOTALL)
    return tail[: end.start()] if end else tail


def _verify_hash_records(records: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for name, record in records.items():
        path = Path(str(record.get("path", "")))
        expected = str(record.get("sha256", ""))
        if not path.exists():
            failures.append(f"{name}: missing {path}")
            continue
        actual = _sha256(path)
        if not expected or actual != expected:
            failures.append(f"{name}: hash mismatch")
    return not failures, failures


def _formal_manifest_matches_environment(
    record: dict[str, Any],
    browser_environment: dict[str, Any],
) -> bool:
    path = Path(str(record.get("path", "")))
    if (
        "runs_miniwob_gamma_p3e" not in path.parts
        or not path.exists()
        or not path.with_name("result.json").exists()
    ):
        return False
    try:
        payload = _load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    miniwob = payload.get("miniwob", {})
    return bool(
        payload.get("phase") == "gamma_p3_formal"
        and isinstance(miniwob, dict)
        and all(
            miniwob.get(field) == browser_environment.get(field)
            for field in FORMAL_MINIWOB_FIELDS
        )
    )


def _pdf_page_texts(path: Path) -> list[str]:
    return [(page.extract_text() or "") for page in PdfReader(str(path)).pages]


def _references_location(path: Path) -> tuple[int | None, float | None]:
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for word in page.extract_words():
                if str(word.get("text", "")).strip() == "References":
                    return page_number, float(word.get("top", 0.0))
    return None, None


def _visual_audit_pass(
    *,
    pdf_path: Path,
    render_audit: dict[str, Any],
) -> bool:
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        return False
    expected_visual_checks = {
        "all_pages_rendered",
        "no_text_or_table_clipping",
        "no_overlapping_elements",
        "figures_and_tables_legible",
        "captions_match_content",
    }
    visual_checks = render_audit.get("visual_checks", {})
    return bool(
        render_audit.get("status") == "visual_audit_complete"
        and str(render_audit.get("pdf_sha256", "")) == _sha256(pdf_path)
        and set(visual_checks) == expected_visual_checks
        and all(bool(visual_checks[name]) for name in expected_visual_checks)
        and int(render_audit.get("page_count", 0)) > 0
        and int(render_audit.get("rendered_page_count", 0))
        == int(render_audit.get("page_count", -1))
    )


def build_manuscript_revision_audit(
    *,
    tex_path: Path,
    supplement_tex_path: Path,
    checklist_tex_path: Path,
    bib_path: Path,
    pdf_path: Path,
    supplement_pdf_path: Path,
    checklist_pdf_path: Path,
    revision_gate_path: Path,
    paper_results_manifest_path: Path,
    claim_decisions_path: Path,
    checklist_report_path: Path,
    environment_manifest_path: Path,
    render_audit_path: Path,
    supplement_render_audit_path: Path,
    checklist_render_audit_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    gate = _load_json(revision_gate_path)
    checks.append(
        _check(
            "revision_evidence_ready",
            gate.get("status") == "ready_for_paper_revision"
            and bool(gate.get("data_complete"))
            and bool(gate.get("p3_reports_same_quality")),
            str(gate.get("status", "missing")),
        )
    )

    paper_results = _load_json(paper_results_manifest_path)
    source_ok, source_failures = _verify_hash_records(paper_results.get("source_hashes", {}))
    generated_ok, generated_failures = _verify_hash_records(
        paper_results.get("generated_hashes", {})
    )
    checks.append(
        _check(
            "paper_result_source_hashes",
            source_ok and bool(paper_results.get("source_hashes")),
            "; ".join(source_failures) or "all source hashes match",
        )
    )
    checks.append(
        _check(
            "generated_table_hashes",
            generated_ok
            and set(paper_results.get("generated_hashes", {}))
            == EXPECTED_GENERATED_HASH_NAMES,
            "; ".join(generated_failures) or "all generated hashes match",
        )
    )
    generated_records = paper_results.get("generated_hashes", {})

    def generated_text(name: str) -> str:
        record = generated_records.get(name, {})
        path = Path(str(record.get("path", "")))
        return path.read_text(encoding="utf-8-sig") if path.exists() else ""

    mechanism_table = generated_text("mechanism_controls.tex")
    sensitivity_table = generated_text("sensitivity_envelope.tex")
    p3_table = generated_text("miniwob_boundary.tex")
    diagnostics_table = generated_text("appendix_diagnostics.tex")
    checks.append(
        _check(
            "mechanism_table_reporting_contract",
            all(
                marker in mechanism_table
                for marker in [
                    "Terminal round $t=5$; five seeds per contrast",
                    "Positive success is better",
                    "seed-clustered 95\\% bootstrap CIs",
                    "not multiplicity-adjusted",
                ]
            ),
            "terminal round, seed count, directions, and clustered CIs",
        )
    )
    checks.append(
        _check(
            "sensitivity_table_reporting_contract",
            all(
                marker in sensitivity_table
                for marker in [
                    "Terminal round $t=5$; three seeds per contrast",
                    "Positive success is better",
                    "seed-clustered 95\\% bootstrap CIs",
                    "not multiplicity-adjusted",
                ]
            ),
            "terminal round, seed count, directions, and clustered CIs",
        )
    )
    if paper_results.get("gates", {}).get("p3_quality_clear"):
        p3_reporting_pass = all(
            marker in p3_table
            for marker in [
                "Consolidated family",
                "paired routes per endpoint",
                "quality clear",
                "terminal $t=3$",
                "six-family block is descriptive",
                "Only failure-penalized cost",
            ]
        )
        p3_reporting_detail = "clear-quality pooled and family reporting"
    else:
        p3_reporting_pass = "withheld" in p3_table.lower()
        p3_reporting_detail = "quality-warning behavioral estimates withheld"
    checks.append(
        _check(
            "p3_table_reporting_contract",
            p3_reporting_pass,
            p3_reporting_detail,
        )
    )
    checks.append(
        _check(
            "formal_configuration_provenance_reporting",
            all(
                marker in diagnostics_table
                for marker in [
                    "validated runs/total runs",
                    "Config/Manifest/Env.",
                    "all-run validation gates",
                    "MiniWoB runtime:",
                    "Exhausted",
                    "Route LLM all/final",
                    "Non-HO exhausted calls",
                    "LLM path",
                ]
            ),
            "formal configuration, sibling-manifest, and cross-run environment "
            "validation plus P3 runtime-source hashes are visible in the supplement",
        )
    )

    macro_manifest_record = generated_records.get("macro_manifest.json", {})
    macro_tex_record = generated_records.get("revision_macros.tex", {})
    macro_manifest_path = Path(str(macro_manifest_record.get("path", "")))
    macro_tex_path = Path(str(macro_tex_record.get("path", "")))
    macro_records: list[dict[str, Any]] = []
    macro_integrity_pass = False
    macro_integrity_detail = "macro artifacts missing"
    if macro_manifest_path.exists() and macro_tex_path.exists():
        macro_manifest = _load_json(macro_manifest_path)
        macro_records = [
            dict(row)
            for row in macro_manifest.get("records", [])
            if isinstance(row, dict)
        ]
        expected_macros = {
            str(row["macro"]): str(row["value"])
            for row in macro_records
        }
        definitions = {
            name: value
            for name, value in re.findall(
                r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}",
                macro_tex_path.read_text(encoding="utf-8-sig"),
            )
        }
        macro_integrity_pass = bool(expected_macros) and (
            int(macro_manifest.get("macro_count", -1)) == len(expected_macros)
            and definitions == expected_macros
            and int(paper_results.get("revision_macro_count", -1))
            == len(expected_macros)
        )
        macro_integrity_detail = (
            f"manifest={len(expected_macros)}, definitions={len(definitions)}, "
            f"paper_results={paper_results.get('revision_macro_count', 'missing')}"
        )
    checks.append(
        _check(
            "revision_macro_manifest_integrity",
            macro_integrity_pass,
            macro_integrity_detail,
        )
    )

    claim_decisions = _load_json(claim_decisions_path)
    claim_source_ok, claim_source_failures = _verify_hash_records(
        claim_decisions.get("source_hashes", {})
    )
    checks.append(
        _check(
            "claim_decisions_ready",
            claim_decisions.get("status") == "claim_decisions_ready"
            and bool(claim_decisions.get("rules_provenance", {}).get("match")),
            str(claim_decisions.get("status", "missing")),
        )
    )
    checks.append(
        _check(
            "claim_decision_source_hashes",
            claim_source_ok and bool(claim_decisions.get("source_hashes")),
            "; ".join(claim_source_failures) or "all claim-decision source hashes match",
        )
    )

    if not tex_path.exists():
        raise FileNotFoundError(tex_path)
    tex = tex_path.read_text(encoding="utf-8-sig")
    if not supplement_tex_path.exists():
        raise FileNotFoundError(supplement_tex_path)
    supplement_tex = supplement_tex_path.read_text(encoding="utf-8-sig")
    uncommented_tex = re.sub(r"(?m)(?<!\\)%.*$", "", tex)
    normalized_tex = tex.replace("\\", "/")
    normalized_supplement_tex = supplement_tex.replace("\\", "/")
    for required in REQUIRED_MAIN_GENERATED_INPUTS:
        checks.append(
            _check(
                f"main_tex_input:{Path(required).name}",
                required in normalized_tex,
                required,
            )
        )
    for required in REQUIRED_SUPPLEMENT_GENERATED_INPUTS:
        checks.append(
            _check(
                f"supplement_tex_input:{Path(required).name}",
                required in normalized_supplement_tex,
                required,
            )
        )
    supplement_only_names = {
        Path(path).name
        for path in REQUIRED_SUPPLEMENT_GENERATED_INPUTS
        if path not in REQUIRED_MAIN_GENERATED_INPUTS
    }
    checks.append(
        _check(
            "supplement_only_tables_absent_from_main",
            all(name not in normalized_tex for name in supplement_only_names),
            ", ".join(sorted(supplement_only_names)),
        )
    )
    bibliography_index = normalized_tex.find("/bibliography")
    main_inputs_before_bibliography = (
        bibliography_index >= 0
        and all(
            0 <= normalized_tex.find(required) < bibliography_index
            for required in REQUIRED_MAIN_GENERATED_INPUTS
        )
    )
    checks.append(
        _check(
            "main_generated_inputs_before_references",
            main_inputs_before_bibliography,
            "all main generated inputs must precede bibliography",
        )
    )
    for name, pattern in REQUIRED_MANUSCRIPT_MARKERS.items():
        checks.append(
            _check(
                name,
                bool(re.search(pattern, tex, flags=re.IGNORECASE | re.DOTALL)),
                pattern,
            )
        )
    lowered = tex.lower()
    for phrase in BANNED_CLAIMS:
        checks.append(
            _check(
                f"banned_claim_absent:{phrase}",
                phrase not in lowered,
                phrase,
            )
        )
    for phrase in STALE_FINAL_PROSE:
        checks.append(
            _check(
                f"stale_final_prose_absent:{phrase}",
                phrase not in lowered,
                phrase,
            )
        )
    def compression_is_bounded(section: str) -> bool:
        return bool(
            re.search(
                r"(strategy[- ]supply|supply|strategy)[- ]compression"
                r"[^.]{0,180}(correlate|candidate (mechanism|channel)|"
                r"not (an )?established cause|causal(?:ity| role)[^.]{0,60}"
                r"(unresolved|not identified|not established))",
                section,
                flags=re.IGNORECASE,
            )
        )

    checks.append(
        _check(
            "compression_causality_bounded",
            compression_is_bounded(tex),
            "strategy-supply compression must remain a correlate or candidate channel",
        )
    )
    checks.append(
        _check(
            "compression_causal_overclaim_absent",
            not bool(
                re.search(
                    r"(strategy[- ]supply|supply|strategy)[- ]compression"
                    r"[^.]{0,80}(causes?|caused|drives?|drove|produces?|"
                    r"produced|leads? to|led to)[^.]{0,80}(loop|stagnat|behavior)"
                    r"|(loop|stagnat\w*)[^.]{0,80}(is|are|was|were) caused by"
                    r"[^.]{0,80}(strategy[- ]supply|supply|strategy)[- ]compression",
                    tex,
                    flags=re.IGNORECASE,
                )
            ),
            "causal verbs linking compression to looping or stagnation are not allowed",
        )
    )
    checks.append(
        _check(
            "cap14_fixed_terminal_scope",
            bool(
                re.search(
                    r"cap[- ]?14[^.]{0,180}(fixed|terminal[- ]capacity)"
                    r"[^.]{0,160}(not (an )?exact|not round[- ]by[- ]round)"
                    r"|(fixed|terminal[- ]capacity)[^.]{0,180}cap[- ]?14"
                    r"[^.]{0,160}(not (an )?exact|not round[- ]by[- ]round)",
                    tex,
                    flags=re.IGNORECASE,
                )
            ),
            "cap-14 must be identified as fixed terminal capacity, not an exact yoke",
        )
    )
    checks.append(
        _check(
            "zeta_content_write_dynamics_caveat",
            bool(
                re.search(
                    r"(exact[- ]size|supply[- ]yoke|exact[^.]{0,40}yoke)"
                    r"[^.]{0,220}(item content|write dynamics)"
                    r"[^.]{0,120}(unequal|unmatched|not controlled|remain)"
                    r"|(item content|write dynamics)[^.]{0,180}"
                    r"(unequal|unmatched|not controlled|remain)[^.]{0,180}"
                    r"(exact[- ]size|supply[- ]yoke|yoke)",
                    tex,
                    flags=re.IGNORECASE,
                )
            ),
            "the exact-size yoke leaves item content or write dynamics unequal",
        )
    )
    checks.append(
        _check(
            "sensitivity_descriptive_no_selection",
            bool(
                re.search(
                    r"sensitivit\w*.{0,260}(descriptive|envelope)"
                    r".{0,260}(no best|not[^.]{0,80}(model|parameter)[- ]selection)"
                    r"|(descriptive|envelope).{0,260}sensitivit\w*"
                    r".{0,260}(no best|not[^.]{0,80}(model|parameter)[- ]selection)",
                    tex,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            ),
            "the sensitivity suite is descriptive and cannot select a best setting",
        )
    )
    mmr_contexts = [
        match.group(0)
        for match in re.finditer(
            r"\bMMR\b.{0,500}",
            tex,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]
    checks.append(
        _check(
            "mmr_method_defined",
            any(
                "0.70" in context
                and "0.30" in context
                and re.search(r"\bcosine\b", context, flags=re.IGNORECASE)
                and re.search(
                    r"(token[- ]hashing|hashing embedding)",
                    context,
                    flags=re.IGNORECASE,
                )
                for context in mmr_contexts
            ),
            "MMR must report its 0.70/0.30 objective and deterministic "
            "token-hashing cosine representation",
        )
    )
    checks.append(
        _check(
            "mmr_representation_scope_caveat",
            bool(
                re.search(
                    r"MMR[^.]{0,220}token[- ]hashing[^.]{0,180}"
                    r"(rather than|not)[^.]{0,120}(learned|semantic)"
                    r"[^.]{0,220}(not[^.]{0,80}(MMR|xQuAD)[^.]{0,80}"
                    r"(generally|general)|one reproducible lexical)",
                    tex,
                    flags=re.IGNORECASE,
                )
            ),
            "token-hashing MMR must be scoped as one lexical policy rather "
            "than diversity-aware retrieval generally",
        )
    )
    checks.append(
        _check(
            "shared_private_reviewer_allocation_caveat",
            bool(
                re.search(
                    r"(private[- ]consolidat\w*|private (?:arm|pool))"
                    r".{0,420}(four|4)[^.]{0,120}(per[- ]agent )?"
                    r"reviewer calls?.{0,320}(one|1)[^.]{0,120}"
                    r"(joint|shared)[^.]{0,80}reviewer call"
                    r"|reviewer calls?.{0,180}(four|4)[^.]{0,120}"
                    r"per[- ]agent.{0,320}(one|1)[^.]{0,120}(joint|shared)",
                    tex,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                and re.search(
                    r"(protocol[- ]level|does not (?:equalize|isolate)|"
                    r"not a one[- ]factor causal)"
                    r".{0,260}(sharing|reviewer|operation opportunity)",
                    tex,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            ),
            "shared versus private must disclose four per-agent reviewer calls "
            "versus one joint call and bound the contrast as protocol-level",
        )
    )
    checks.append(
        _check(
            "append_agree_protocol_defined",
            bool(
                re.search(
                    r"(append/agree|shared[- ]append)"
                    r".{0,300}near[- ]duplicate"
                    r".{0,180}(agreement|upvote)"
                    r".{0,300}(no joint reviewer|no reviewer-issued|"
                    r"without[^.]{0,80}(edit|downvote))",
                    tex,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            )
            and not bool(
                re.search(
                    r"shared(?:[- ]|\\texttt\{shared-)append\}?"
                    r"[^.]{0,100}(never merged|no merg\w*)",
                    tex,
                    flags=re.IGNORECASE,
                )
            ),
            "append controls must disclose deterministic near-duplicate agreement "
            "and must not be described as never merged",
        )
    )

    abstract = _section(tex, r"\\begin\{abstract\}", r"\\end\{abstract\}")
    limitations = _section(tex, r"\\section\{Limitations\}", r"\\section\{Conclusion\}")
    conclusion = _section(
        tex,
        r"\\section\{Conclusion\}",
        r"\\paragraph\{Reproducibility\}",
    )
    protocol_scope_pattern = (
        r"tested shared reviewer[- ]consolidation protocol"
        r"|shared reviewer[- ]consolidation protocol[^.]{0,80}"
        r"(tested|evaluated|under this design)"
    )
    checks.append(
        _check(
            "abstract_protocol_scope",
            bool(
                re.search(
                    protocol_scope_pattern,
                    abstract,
                    flags=re.IGNORECASE,
                )
            ),
            "the abstract must scope claims to the tested shared reviewer-consolidation protocol",
        )
    )
    checks.append(
        _check(
            "conclusion_protocol_scope",
            bool(
                re.search(
                    protocol_scope_pattern,
                    conclusion,
                    flags=re.IGNORECASE,
                )
            ),
            "the conclusion must scope claims to the tested shared reviewer-consolidation protocol",
        )
    )
    checks.append(
        _check(
            "abstract_compression_causality_bounded",
            compression_is_bounded(abstract),
            "the abstract must present compression as a correlate or candidate channel",
        )
    )
    checks.append(
        _check(
            "conclusion_compression_causality_bounded",
            compression_is_bounded(conclusion),
            "the conclusion must present compression as a correlate or candidate channel",
        )
    )
    checks.append(
        _check(
            "conclusion_protocol_conditions",
            all(
                re.search(pattern, conclusion, flags=re.IGNORECASE)
                for pattern in [
                    r"retrieval capacity",
                    r"(writer|reviewer) budget",
                    r"merge (policy|threshold)",
                ]
            ),
            "the conclusion must name the tested retrieval capacity, writer/reviewer "
            "budget, and merge policy",
        )
    )

    shared_loop_class = (
        claim_decisions.get("shared_vs_private", {})
        .get("endpoints", {})
        .get("looped", {})
        .get("classification")
    )
    required_macro_specs = [
        ("shared_consolidated_minus_private_consolidated", "looped"),
    ]
    required_seed_sign_macro_specs: list[tuple[str, str]] = []
    required_sensitivity_setting_fields = [
        "PositiveDetectedSettings",
        "NegativeDetectedSettings",
        "NotDetectedSettings",
    ]
    zeta_interpretation = claim_decisions.get("zeta_exact_yoke", {}).get(
        "interpretation"
    )
    if zeta_interpretation in {
        "candidate_pool_size_alone_insufficient_for_loop_separation",
        "candidate_supply_size_remains_plausible",
    }:
        required_macro_specs.append(
            ("zeta_exact_yoke_minus_epsilon_shared_consolidated", "looped")
        )
    for metric in claim_decisions.get("mmr_vs_consolidated", {}).get(
        "endpoint_specific_mitigation_allowed", []
    ):
        required_macro_specs.append(
            ("mmr_minus_shared_consolidated", str(metric))
        )
    p3_primary = gate.get("sections", {}).get("p3_primary", {})
    p3_quality_clear = bool(gate.get("p3_quality_clear"))
    if p3_quality_clear:
        required_macro_specs.extend(
            [
                ("p3_consolidated_minus_frozen", "failure_penalized_cost"),
                ("p3_consolidated_minus_frozen", "loop_stall_burden"),
            ]
        )
        required_seed_sign_macro_specs.extend(
            [
                ("p3_consolidated_minus_frozen", "failure_penalized_cost"),
                ("p3_consolidated_minus_frozen", "loop_stall_burden"),
            ]
        )
    macro_index = {
        (
            str(row.get("contrast", "")),
            str(row.get("metric", "")),
            str(row.get("field", "")),
        ): str(row.get("macro", ""))
        for row in macro_records
    }
    missing_macro_records: list[str] = []
    missing_macro_references: list[str] = []
    for contrast, metric in required_macro_specs:
        for field in ("Mean", "CILo", "CIHi"):
            name = macro_index.get((contrast, metric, field), "")
            key = f"{contrast}/{metric}/{field}"
            if not name:
                missing_macro_records.append(key)
            elif not re.search(
                rf"\\{re.escape(name)}(?![A-Za-z])",
                uncommented_tex,
            ):
                missing_macro_references.append(name)
    p3_seed_sign_macro_names: list[str] = []
    for contrast, metric in required_seed_sign_macro_specs:
        name = macro_index.get((contrast, metric, "SeedSigns"), "")
        key = f"{contrast}/{metric}/SeedSigns"
        if not name:
            missing_macro_records.append(key)
        else:
            p3_seed_sign_macro_names.append(name)
            if not re.search(
                rf"\\{re.escape(name)}(?![A-Za-z])",
                uncommented_tex,
            ):
                missing_macro_references.append(name)
    sensitivity_setting_macro_names: list[str] = []
    for field in required_sensitivity_setting_fields:
        name = macro_index.get(
            ("epsilon_sensitivity_envelope", "looped", field),
            "",
        )
        key = f"epsilon_sensitivity_envelope/looped/{field}"
        if not name:
            missing_macro_records.append(key)
        else:
            sensitivity_setting_macro_names.append(name)
            if not re.search(
                rf"\\{re.escape(name)}(?![A-Za-z])",
                uncommented_tex,
            ):
                missing_macro_references.append(name)
    checks.append(
        _check(
            "key_fresh_narrative_uses_generated_macros",
            not missing_macro_records and not missing_macro_references,
            (
                "missing records="
                + (", ".join(missing_macro_records) or "none")
                + "; missing references="
                + (", ".join(missing_macro_references) or "none")
            ),
        )
    )
    checks.append(
        _check(
            "sensitivity_setting_branches_reported",
            bool(
                re.search(
                    r"eight prespecified sensitivity settings",
                    tex,
                    flags=re.IGNORECASE,
                )
                and len(sensitivity_setting_macro_names) == 3
                and all(
                    re.search(
                        rf"\\{re.escape(name)}(?![A-Za-z])",
                        uncommented_tex,
                    )
                    for name in sensitivity_setting_macro_names
                )
            ),
            "main text must classify all eight settings for loop rate relative "
            "to the reference through generated macros",
        )
    )
    fresh_shared_context = bool(
        re.search(
            r"(fresh|epsilon|mechanism[- ]control|new control)[^.]{0,220}(shared|private)|"
            r"(shared|private)[^.]{0,220}(fresh|epsilon|mechanism[- ]control|new control)",
            tex,
            flags=re.IGNORECASE,
        )
    )

    def shared_class_present(section: str, classification: str) -> bool:
        if classification == "positive_detected":
            return bool(
                re.search(
                    r"(adds|amplif\w*|associated with added)"
                    r"[^.]{0,100}loop[^.]{0,100}private|"
                    r"loop[^.]{0,100}(adds|amplif\w*|associated with added)"
                    r"[^.]{0,100}private",
                    section,
                    flags=re.IGNORECASE,
                )
            )
        if classification == "negative_detected":
            return bool(
                re.search(
                    r"(lower|reduc\w*)[^.]{0,100}loop[^.]{0,100}private",
                    section,
                    flags=re.IGNORECASE,
                )
            )
        return bool(
            re.search(
                r"does not isolate[^.]{0,100}shared-specific loop",
                section,
                flags=re.IGNORECASE,
            )
        )

    def shared_branch_matches(section: str) -> bool:
        return shared_class_present(section, str(shared_loop_class))

    if shared_loop_class == "positive_detected":
        shared_branch_pass = (
            fresh_shared_context
            and shared_branch_matches(tex)
            and shared_branch_matches(abstract)
            and shared_branch_matches(conclusion)
        )
    elif shared_loop_class == "negative_detected":
        shared_branch_pass = (
            fresh_shared_context
            and shared_branch_matches(tex)
            and shared_branch_matches(abstract)
            and shared_branch_matches(conclusion)
        )
    else:
        shared_branch_pass = (
            fresh_shared_context
            and shared_branch_matches(tex)
            and shared_branch_matches(abstract)
            and shared_branch_matches(conclusion)
        )
    checks.append(
        _check(
            "shared_private_claim_branch",
            shared_branch_pass,
            f"{shared_loop_class}; fresh-context={fresh_shared_context}",
        )
    )
    abstract_conclusion = abstract + "\n" + conclusion
    contradictory_shared_classes = [
        classification
        for classification in [
            "positive_detected",
            "negative_detected",
            "not_detected",
        ]
        if classification != shared_loop_class
        and shared_class_present(abstract_conclusion, classification)
    ]
    checks.append(
        _check(
            "shared_private_contradiction_absent",
            not contradictory_shared_classes,
            "contradictory branches: "
            + (", ".join(contradictory_shared_classes) or "none"),
        )
    )

    mmr_status = (
        claim_decisions.get("mmr_vs_consolidated", {})
        .get("manipulation", {})
        .get("status")
    )
    mmr_allowed = claim_decisions.get("mmr_vs_consolidated", {}).get(
        "endpoint_specific_mitigation_allowed", []
    )
    mmr_direction_reported = bool(
        re.search(
            r"MMR[^.]{0,180}(diversity|entropy|concentration|distinct)"
            r"[^.]{0,120}(intended|direction|diagnostic|increas|decreas|shift)"
            r"|(diversity|entropy|concentration|distinct)[^.]{0,180}MMR"
            r"[^.]{0,120}(intended|direction|diagnostic|increas|decreas|shift)",
            tex,
            flags=re.IGNORECASE,
        )
    )

    def mmr_endpoint_improvement_reported(metric: str) -> bool:
        metric_patterns = {
            "success": r"success(?: rate)?",
            "success_excess_steps": r"success[- ]only excess(?: steps)?",
            "failure_penalized_steps": r"failure[- ]penalized(?: excess)? steps",
            "looped": r"loop(?:ed| rate| burden)?",
            "stagnation_rate": r"stagnation(?: rate)?",
        }
        if metric not in metric_patterns:
            return False
        endpoint = metric_patterns[metric]
        verbs = (
            r"(improv\w*|rais\w*|increas\w*|higher)"
            if metric == "success"
            else r"(improv\w*|mitigat\w*|reduc\w*|lower\w*|decreas\w*)"
        )
        return bool(
            re.search(
                rf"MMR[^.]{{0,180}}{verbs}[^.]{{0,120}}{endpoint}"
                rf"|MMR[^.]{{0,180}}{endpoint}[^.]{{0,120}}{verbs}"
                rf"|{endpoint}[^.]{{0,180}}{verbs}[^.]{{0,120}}MMR",
                tex,
                flags=re.IGNORECASE,
            )
        )

    if mmr_status == "direction_not_observed":
        mmr_branch_pass = bool(
            re.search(
                r"MMR[^.]{0,160}(does not establish|manipulation[^.]{0,40}(fails|not observed))",
                tex,
                flags=re.IGNORECASE,
            )
        )
    elif mmr_allowed:
        mmr_branch_pass = (
            mmr_direction_reported
            and all(
                mmr_endpoint_improvement_reported(str(metric))
                for metric in mmr_allowed
            )
        )
    else:
        mmr_branch_pass = mmr_direction_reported and bool(
            re.search(
                r"MMR[^.]{0,160}(no .*mitigation|does not improve|insufficient)",
                tex,
                flags=re.IGNORECASE,
            )
        )
    checks.append(
        _check(
            "mmr_claim_branch",
            mmr_branch_pass,
            f"{mmr_status}; mitigation endpoints={mmr_allowed}",
        )
    )

    def zeta_branch_present(section: str) -> bool:
        if zeta_interpretation == "candidate_pool_size_alone_insufficient_for_loop_separation":
            return bool(
                re.search(
                    r"(exact[- ]size|yoke)[^.]{0,180}(size alone|pool size alone|candidate-pool size alone)[^.]{0,80}insufficient",
                    section,
                    flags=re.IGNORECASE,
                )
            )
        if zeta_interpretation == "candidate_supply_size_remains_plausible":
            return bool(
                re.search(
                    r"(exact[- ]size|yoke)[^.]{0,180}(size|supply)[^.]{0,80}(plausible|unresolved)",
                    section,
                    flags=re.IGNORECASE,
                )
            )
        return bool(
            re.search(
                r"(exact[- ]size|yoke)[^.]{0,180}not evaluable",
                section,
                flags=re.IGNORECASE,
            )
        )
    zeta_branch_pass = zeta_branch_present(tex) and zeta_branch_present(conclusion)
    checks.append(
        _check(
            "zeta_claim_branch",
            zeta_branch_pass,
            str(zeta_interpretation),
        )
    )

    p3_decision = p3_primary.get("decision")
    p3_pass = (
        p3_quality_clear
        and p3_decision == "p3_phenomenon_pass"
    )
    if p3_pass:
        p3_seed_signs_reported = bool(
            re.search(
                r"seed\s*0\s*/\s*1\s*/\s*2\s+(?:signs|directions)",
                tex,
                flags=re.IGNORECASE,
            )
            and len(p3_seed_sign_macro_names) == 2
            and all(
                re.search(
                    rf"\\{re.escape(name)}(?![A-Za-z])",
                    uncommented_tex,
                )
                for name in p3_seed_sign_macro_names
            )
        )
        checks.append(
            _check(
                "p3_primary_seed_signs_reported",
                p3_seed_signs_reported,
                "the two primary endpoints must list seed 0/1/2 directions "
                "through generated macros",
            )
        )

        def pooled_p3_scope(section: str) -> bool:
            return bool(
                re.search(r"\bMiniWoB\b", section, flags=re.IGNORECASE)
                and re.search(
                    r"(six[- ]family|six tested|six task)",
                    section,
                    flags=re.IGNORECASE,
                )
                and re.search(
                    r"(equal[- ]family pooled|pooled (?:primary )?gate|"
                    r"pooled[^.]{0,80}(failure[- ]penalized|loop/stall))",
                    section,
                    flags=re.IGNORECASE,
                )
            )

        checks.append(
            _check(
                "p3_pass_pooled_scope_in_abstract",
                pooled_p3_scope(abstract),
                "clear-quality P3 pass must be described as a six-family pooled gate",
            )
        )
        checks.append(
            _check(
                "p3_pass_pooled_scope_in_conclusion",
                pooled_p3_scope(conclusion),
                "clear-quality P3 pass must be described as a six-family pooled gate",
            )
        )
        checks.append(
            _check(
                "p3_pass_task_family_heterogeneity",
                bool(
                    re.search(
                        r"(per[- ]family|task[- ]family)[^.]{0,120}"
                        r"(heterogen|vari\w*|not uniform)|"
                        r"(heterogen|not uniform)[^.]{0,120}"
                        r"(per[- ]family|task[- ]family|across tasks)",
                        tex,
                        flags=re.IGNORECASE,
                    )
                ),
                "a pooled P3 pass must retain an explicit task-family heterogeneity caveat",
            )
        )
        checks.append(
            _check(
                "p3_pass_uniform_replication_claim_absent",
                not bool(
                    re.search(
                        r"replicat\w*\s+(uniformly|across all six|in every|in all)"
                        r"|(?<!not )uniform replication\s+(across|in)"
                        r"|all six task families[^.]{0,40}replicat\w*",
                        tex,
                        flags=re.IGNORECASE,
                    )
                ),
                "a pooled P3 pass cannot be promoted to uniform per-family replication",
            )
        )
    elif (
        p3_quality_clear
        and p3_decision == "p3_not_detected_or_underpowered"
    ):
        def bounded_p3_nonpass(section: str) -> bool:
            return bool(
                re.search(r"\bMiniWoB\b", section, flags=re.IGNORECASE)
                and re.search(
                    r"(not detected|underpowered)",
                    section,
                    flags=re.IGNORECASE,
                )
                and re.search(
                    r"(frozen design|design and sample size|tested design)",
                    section,
                    flags=re.IGNORECASE,
                )
            )
        for section_name, section in [
            ("abstract", abstract),
            ("limitations", limitations),
            ("conclusion", conclusion),
        ]:
            checks.append(
                _check(
                    f"p3_nonpass_bounded_in_{section_name}",
                    bounded_p3_nonpass(section),
                    "clear-quality P3 nonpass must be stated as not detected "
                    "under the frozen design and sample size",
                )
            )
    else:
        def bounded_p3_quality_warning(section: str) -> bool:
            return bool(
                re.search(r"\bMiniWoB\b", section, flags=re.IGNORECASE)
                and re.search(
                    r"(not evaluable|not behaviorally interpretable|quality warning)",
                    section,
                    flags=re.IGNORECASE,
                )
            )
        for section_name, section in [
            ("abstract", abstract),
            ("limitations", limitations),
            ("conclusion", conclusion),
        ]:
            checks.append(
                _check(
                    f"p3_quality_warning_bounded_in_{section_name}",
                    bounded_p3_quality_warning(section),
                    "P3 formal quality is not clear",
                )
            )

    abstract_conclusion = abstract + "\n" + conclusion
    p3_branch_language = {
        "pass": bool(
            re.search(
                r"\bMiniWoB\b[^.]{0,220}(pooled[^.]{0,100}"
                r"(?:gate )?passes|scoped[^.]{0,80}replication)",
                abstract_conclusion,
                flags=re.IGNORECASE,
            )
        ),
        "nonpass": bool(
            re.search(
                r"\bMiniWoB\b[^.]{0,220}(not detected|underpowered)",
                abstract_conclusion,
                flags=re.IGNORECASE,
            )
        ),
        "quality_warning": bool(
            re.search(
                r"\bMiniWoB\b[^.]{0,220}"
                r"(not evaluable|not behaviorally interpretable|quality warning)",
                abstract_conclusion,
                flags=re.IGNORECASE,
            )
        ),
    }
    expected_p3_branch = (
        "pass"
        if p3_pass
        else (
            "nonpass"
            if p3_quality_clear
            and p3_decision == "p3_not_detected_or_underpowered"
            else "quality_warning"
        )
    )
    checks.append(
        _check(
            "p3_abstract_conclusion_branch_exclusive",
            p3_branch_language.get(expected_p3_branch, False)
            and not any(
                present
                for name, present in p3_branch_language.items()
                if name != expected_p3_branch
            ),
            f"expected={expected_p3_branch}; observed="
            + ", ".join(
                name for name, present in p3_branch_language.items() if present
            ),
        )
    )

    zeta = gate.get("sections", {}).get("zeta_exact_supply_yoke", {})
    if zeta.get("decision") == "zeta_supply_yoke_not_evaluable":
        checks.append(
            _check(
                "zeta_nonevaluable_reported",
                bool(
                    re.search(r"(yoke|exact[- ]size)", tex, flags=re.IGNORECASE)
                    and re.search(r"not evaluable", tex, flags=re.IGNORECASE)
                ),
                "Zeta manipulation did not pass",
            )
        )

    main_generated_names = {
        Path(path).name for path in REQUIRED_MAIN_GENERATED_INPUTS
    }
    supplement_generated_names = {
        Path(path).name for path in REQUIRED_SUPPLEMENT_GENERATED_INPUTS
    }
    generated_hashes = paper_results.get("generated_hashes", {})
    required_build_inputs = [
        tex_path,
        bib_path,
        paper_results_manifest_path,
        claim_decisions_path,
    ]
    required_build_inputs.extend(
        Path(str(record["path"]))
        for name, record in generated_hashes.items()
        if name in main_generated_names and record.get("path")
    )
    pdf_exists = pdf_path.exists() and pdf_path.stat().st_size > 0
    pdf_fresh = pdf_exists and all(
        pdf_path.stat().st_mtime >= path.stat().st_mtime
        for path in required_build_inputs
        if path.exists()
    )
    checks.append(
        _check(
            "compiled_pdf_fresh",
            pdf_fresh,
            str(pdf_path),
        )
    )

    main_page_count = 0
    references_start_page = None
    references_top = None
    if pdf_exists:
        page_texts = _pdf_page_texts(pdf_path)
        main_page_count = len(page_texts)
        references_start_page, references_top = _references_location(pdf_path)
    checks.append(
        _check(
            "main_pdf_total_page_limit",
            0 < main_page_count <= 9,
            f"pages={main_page_count}; maximum=9",
        )
    )
    checks.append(
        _check(
            "technical_content_within_seven_pages",
            references_start_page is not None
            and (
                references_start_page <= 7
                or (
                    references_start_page == 8
                    and references_top is not None
                    and references_top <= 120.0
                )
            ),
            (
                f"references_start_page={references_start_page}; "
                f"references_top={references_top}"
            ),
        )
    )

    render_audit = _load_json(render_audit_path)
    checks.append(
        _check(
            "pdf_visual_audit",
            _visual_audit_pass(pdf_path=pdf_path, render_audit=render_audit),
            str(render_audit_path),
        )
    )

    supplement_required_build_inputs = [
        supplement_tex_path,
        paper_results_manifest_path,
        claim_decisions_path,
    ]
    supplement_required_build_inputs.extend(
        Path(str(record["path"]))
        for name, record in generated_hashes.items()
        if name in supplement_generated_names and record.get("path")
    )
    supplement_pdf_exists = (
        supplement_pdf_path.exists() and supplement_pdf_path.stat().st_size > 0
    )
    supplement_pdf_fresh = supplement_pdf_exists and all(
        supplement_pdf_path.stat().st_mtime >= path.stat().st_mtime
        for path in supplement_required_build_inputs
        if path.exists()
    )
    checks.append(
        _check(
            "compiled_supplement_pdf_fresh",
            supplement_pdf_fresh,
            str(supplement_pdf_path),
        )
    )
    supplement_render_audit = _load_json(supplement_render_audit_path)
    checks.append(
        _check(
            "supplement_pdf_visual_audit",
            _visual_audit_pass(
                pdf_path=supplement_pdf_path,
                render_audit=supplement_render_audit,
            ),
            str(supplement_render_audit_path),
        )
    )

    checklist_report = _load_json(checklist_report_path)
    checklist_records = [
        checklist_report.get("template", {}),
        checklist_report.get("responses", {}),
        checklist_report.get("output", {}),
    ]
    checklist_hashes_match = all(
        bool(record.get("path"))
        and Path(str(record["path"])).exists()
        and _sha256(Path(str(record["path"]))) == str(record.get("sha256", ""))
        for record in checklist_records
    )
    checks.append(
        _check(
            "reproducibility_checklist_ready",
            checklist_report.get("status") == "checklist_ready"
            and checklist_report.get("specification_status") == "finalized"
            and int(checklist_report.get("question_count", 0)) == 31
            and checklist_hashes_match,
            (
                f"status={checklist_report.get('status', 'missing')}; "
                f"questions={checklist_report.get('question_count', 'missing')}"
            ),
        )
    )
    if not checklist_tex_path.exists():
        raise FileNotFoundError(checklist_tex_path)
    checklist_tex = checklist_tex_path.read_text(encoding="utf-8-sig")
    unresolved_checklist = bool(
        re.search(
            r"\\question\{[^{}]+\}\{\([^()]*\)\}\s*Type your response here",
            checklist_tex,
        )
    )
    checks.append(
        _check(
            "reproducibility_checklist_no_unresolved_questions",
            not unresolved_checklist,
            str(checklist_tex_path),
        )
    )
    checklist_pdf_exists = (
        checklist_pdf_path.exists() and checklist_pdf_path.stat().st_size > 0
    )
    checklist_required_inputs = [checklist_tex_path, checklist_report_path]
    checklist_required_inputs.extend(
        Path(str(record["path"]))
        for record in checklist_records
        if record.get("path")
    )
    checklist_pdf_fresh = checklist_pdf_exists and all(
        checklist_pdf_path.stat().st_mtime >= path.stat().st_mtime
        for path in checklist_required_inputs
        if path.exists()
    )
    checks.append(
        _check(
            "compiled_checklist_pdf_fresh",
            checklist_pdf_fresh,
            str(checklist_pdf_path),
        )
    )
    checklist_render_audit = _load_json(checklist_render_audit_path)
    checks.append(
        _check(
            "checklist_pdf_visual_audit",
            _visual_audit_pass(
                pdf_path=checklist_pdf_path,
                render_audit=checklist_render_audit,
            ),
            str(checklist_render_audit_path),
        )
    )

    environment_manifest = _load_json(environment_manifest_path)
    environment_path_values = [
        environment_manifest.get("system", {}).get("python_executable", ""),
        environment_manifest.get("browser_environment", {}).get(
            "browser_executable", ""
        ),
        environment_manifest.get("browser_environment", {}).get(
            "miniwob_url", ""
        ),
    ]
    environment_serialized = json.dumps(environment_path_values, ensure_ascii=False)
    environment_anonymized = not bool(
        re.search(
            r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\\/\"']+",
            environment_serialized,
        )
    )
    environment_tex_record = environment_manifest.get("tex", {})
    environment_tex_path = Path(str(environment_tex_record.get("path", "")))
    browser_environment = environment_manifest.get("browser_environment", {})
    browser_provenance = browser_environment.get("provenance", {})
    browser_source_records = browser_provenance.get("source_manifests", [])
    browser_source_hashes_match = bool(browser_source_records) and all(
        bool(record.get("path"))
        and Path(str(record["path"])).exists()
        and _sha256(Path(str(record["path"]))) == str(record.get("sha256", ""))
        for record in browser_source_records
    )
    browser_source_payloads_match = (
        len(browser_source_records) == 54
        and all(
            _formal_manifest_matches_environment(record, browser_environment)
            for record in browser_source_records
            if isinstance(record, dict)
        )
    )
    browser_versions = browser_environment.get("versions", {})
    checks.append(
        _check(
            "execution_environment_recorded",
            environment_manifest.get("status") == "environment_manifest_ready"
            and environment_anonymized
            and bool(environment_manifest.get("system", {}).get("cpu_model"))
            and bool(environment_manifest.get("system", {}).get("python_version"))
            and bool(
                environment_manifest.get("browser_environment", {}).get(
                    "miniwob_plusplus_commit"
                )
            )
            and bool(browser_environment.get("browser_executable"))
            and bool(browser_environment.get("browser_version"))
            and bool(browser_environment.get("browser_executable_sha256"))
            and bool(browser_environment.get("browser_tree_sha256"))
            and int(browser_environment.get("browser_tree_file_count", 0)) == 273
            and int(browser_environment.get("browser_tree_total_bytes", 0))
            == 501_388_593
            and bool(browser_environment.get("miniwob_url"))
            and bool(browser_environment.get("task_validation", {}).get("ok"))
            and not browser_environment.get("task_validation", {}).get("missing")
            and int(
                browser_environment.get("task_validation", {}).get(
                    "n_registered", 0
                )
            )
            > 0
            and int(browser_environment.get("independent_envs_per_task", -1)) == 4
            and browser_provenance.get("source") == "formal_run_manifests"
            and int(browser_provenance.get("completed_manifest_count", -1)) == 54
            and len(browser_source_records) == 54
            and browser_source_hashes_match
            and browser_source_payloads_match
            and all(
                browser_versions.get(name) not in {None, "", "not-installed"}
                for name in [
                    "browsergym-core",
                    "browsergym-miniwob",
                    "gymnasium",
                    "playwright",
                ]
            )
            and environment_tex_path.exists()
            and environment_tex_path.stat().st_size
            == int(environment_tex_record.get("size_bytes", -1))
            and _sha256(environment_tex_path)
            == str(environment_tex_record.get("sha256", "")),
            str(environment_manifest_path),
        )
    )
    checks.append(
        _check(
            "supplement_pdf_current_with_environment",
            supplement_pdf_exists
            and environment_tex_path.exists()
            and supplement_pdf_path.stat().st_mtime
            >= environment_tex_path.stat().st_mtime,
            str(environment_tex_path),
        )
    )

    status = "complete" if checks and all(row["passed"] for row in checks) else "incomplete"
    result = {
        "status": status,
        "tex": str(tex_path),
        "pdf": str(pdf_path),
        "supplement_tex": str(supplement_tex_path),
        "supplement_pdf": str(supplement_pdf_path),
        "checklist_tex": str(checklist_tex_path),
        "checklist_pdf": str(checklist_pdf_path),
        "checks": checks,
        "failed_checks": [row["name"] for row in checks if not row["passed"]],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manuscript_revision_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Manuscript Revision Audit",
        "",
        f"Status: **{status}**",
        "",
        "| check | pass | detail |",
        "|---|---|---|",
    ]
    for row in checks:
        detail = str(row["detail"]).replace("|", "\\|")
        lines.append(f"| {row['name']} | {'yes' if row['passed'] else 'no'} | {detail} |")
    lines.append("")
    (out_dir / "manuscript_revision_audit.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit whether the complete evidence has actually been integrated into the paper."
    )
    parser.add_argument(
        "--tex",
        default="paper_draft/antmill_memory_aaai27_en.tex",
    )
    parser.add_argument(
        "--supplement-tex",
        default="paper_draft/antmill_memory_aaai27_supp.tex",
    )
    parser.add_argument(
        "--checklist-tex",
        default="paper_draft/antmill_memory_reproducibility_checklist.tex",
    )
    parser.add_argument("--bib", default="paper_draft/antmill_memory.bib")
    parser.add_argument(
        "--pdf",
        default="paper_draft/antmill_memory_aaai27_en.pdf",
    )
    parser.add_argument(
        "--supplement-pdf",
        default="paper_draft/antmill_memory_aaai27_supp.pdf",
    )
    parser.add_argument(
        "--checklist-pdf",
        default="paper_draft/antmill_memory_reproducibility_checklist.pdf",
    )
    parser.add_argument(
        "--revision-gate",
        default="runs_revision_evidence/revision_evidence.json",
    )
    parser.add_argument(
        "--paper-results",
        default="paper_draft/generated/revision_results/paper_results_manifest.json",
    )
    parser.add_argument(
        "--claim-decisions",
        default="paper_draft/generated/revision_results/claim_decisions.json",
    )
    parser.add_argument(
        "--checklist-report",
        default=(
            "paper_draft/generated/revision_results/"
            "reproducibility_checklist_report.json"
        ),
    )
    parser.add_argument(
        "--environment-manifest",
        default=(
            "paper_draft/generated/revision_results/"
            "environment_manifest.json"
        ),
    )
    parser.add_argument(
        "--render-audit",
        default="paper_draft/generated/revision_results/final_render_audit.json",
    )
    parser.add_argument(
        "--supplement-render-audit",
        default=(
            "paper_draft/generated/revision_results/"
            "final_supplement_render_audit.json"
        ),
    )
    parser.add_argument(
        "--checklist-render-audit",
        default=(
            "paper_draft/generated/revision_results/"
            "final_checklist_render_audit.json"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default="runs_manuscript_revision_audit",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_manuscript_revision_audit(
        tex_path=Path(args.tex),
        supplement_tex_path=Path(args.supplement_tex),
        checklist_tex_path=Path(args.checklist_tex),
        bib_path=Path(args.bib),
        pdf_path=Path(args.pdf),
        supplement_pdf_path=Path(args.supplement_pdf),
        checklist_pdf_path=Path(args.checklist_pdf),
        revision_gate_path=Path(args.revision_gate),
        paper_results_manifest_path=Path(args.paper_results),
        claim_decisions_path=Path(args.claim_decisions),
        checklist_report_path=Path(args.checklist_report),
        environment_manifest_path=Path(args.environment_manifest),
        render_audit_path=Path(args.render_audit),
        supplement_render_audit_path=Path(args.supplement_render_audit),
        checklist_render_audit_path=Path(args.checklist_render_audit),
        out_dir=Path(args.out_dir),
    )
    print(result["status"])
    if result["status"] != "complete":
        raise SystemExit(1)
    return result


if __name__ == "__main__":
    main()
