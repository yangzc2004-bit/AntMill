from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPO_ROOT / "benchmarks" / "scbench"
GENERATED_ROOT = REPO_ROOT / "paper_draft" / "generated" / "moa_paper"
OUTPUT_JSON = AUDIT_ROOT / "scbench_transfer_mechanism_audit_20260715.json"
OUTPUT_MD = AUDIT_ROOT / "scbench_transfer_mechanism_audit_20260715.md"
OUTPUT_SIZE_CSV = GENERATED_ROOT / "experience_summary_sizes.csv"
OUTPUT_ALIGNMENT_CSV = GENERATED_ROOT / "experience_copy_alignment.csv"
OUTPUT_LAYER_CSV = GENERATED_ROOT / "implementation_alignment_layers.csv"
OUTPUT_SCHEMA_MD = (
    REPO_ROOT / "paper_draft" / "EXPERIENCE_ARTIFACT_SCHEMA_20260715.md"
)

TRAJECTORY_MARKER = "Recent MiniSWE actions and reasoning:\n"
SNAPSHOT_MARKER = "Resulting source snapshot excerpt:\n"
SELF_REPORT_REGEX = (
    r"\b(pass|passes|passed|works|working|success|successful|"
    r"correct|verify|verified)\b"
)
IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}

RUNS = (
    {
        "run_id": "cfgpipe-cumulative-main",
        "role": "frozen_main_treatment",
        "root": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_"
            "depth12_self_report_r2_20260715"
        ),
        "arm": (
            "cumulative_self_report_acceptance-"
            "426bc68aaa4b4e8c8f2aad850c75a89b"
        ),
        "routing": "cumulative",
    },
    {
        "run_id": "cfgpipe-bounded-control",
        "role": "prospective_bounded_context_control",
        "root": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_"
            "bounded_context_depth6_r1_20260715"
        ),
        "arm": (
            "bounded_recent_self_report_acceptance-"
            "93be1c12894e4c8f96b0fdc6b2334b68"
        ),
        "routing": "bounded_recent",
    },
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())


def included_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in IGNORED_PARTS for part in path.relative_to(root).parts)
    )


def directory_hash(root: Path) -> str | None:
    files = included_files(root)
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def normalized_lines(text: str) -> frozenset[str]:
    lines = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if len(line) >= 3 and not line.startswith("### FILE "):
            lines.append(line)
    return frozenset(lines)


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = frozenset(left)
    right_set = frozenset(right)
    union = left_set | right_set
    return 1.0 if not union else len(left_set & right_set) / len(union)


def recall(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = frozenset(left)
    right_set = frozenset(right)
    return 1.0 if not left_set else len(left_set & right_set) / len(left_set)


def primary_source(snapshot: Path) -> Path | None:
    preferred = snapshot / "cfgpipe.py"
    if preferred.is_file():
        return preferred
    python_files = [
        path
        for path in included_files(snapshot)
        if path.suffix.lower() == ".py"
        and not path.name.lower().startswith("test")
    ]
    return python_files[0] if python_files else None


def ast_features(path: Path | None) -> dict[str, frozenset[str]]:
    if path is None:
        return {
            "functions": frozenset(),
            "ast_signatures": frozenset(),
            "strings": frozenset(),
        }
    text = read_text(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {
            "functions": frozenset(),
            "ast_signatures": frozenset(),
            "strings": frozenset(),
        }
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    signatures = Counter(type(node).__name__ for node in ast.walk(tree))
    ast_signature_set = {
        f"{node_type}:{count}" for node_type, count in signatures.items()
    }
    strings = {
        node.value.strip()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value.strip()) >= 4
    }
    return {
        "functions": frozenset(functions),
        "ast_signatures": frozenset(ast_signature_set),
        "strings": frozenset(strings),
    }


def experience_components(summary: str) -> dict[str, str]:
    if TRAJECTORY_MARKER not in summary:
        return {"header": summary, "trajectory": "", "snapshot": ""}
    header, remainder = summary.split(TRAJECTORY_MARKER, 1)
    if SNAPSHOT_MARKER not in remainder:
        return {"header": header, "trajectory": remainder, "snapshot": ""}
    trajectory, snapshot = remainder.split(SNAPSHOT_MARKER, 1)
    return {
        "header": header,
        "trajectory": trajectory,
        "snapshot": snapshot,
    }


def result_features(result: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(str(result["workspace"]))
    source_path = primary_source(workspace)
    source_text = read_text(source_path) if source_path is not None else ""
    components = experience_components(str(result["artifact"]["summary"]))
    features = ast_features(source_path)
    return {
        "artifact_id": str(result["artifact"]["artifact_id"]),
        "worker_id": str(result["worker_id"]),
        "source_layer": int(result["layer"]),
        "workspace": str(workspace),
        "snapshot_hash": directory_hash(workspace),
        "primary_source": str(source_path) if source_path is not None else None,
        "primary_hash": sha256_file(source_path) if source_path is not None else None,
        "source_lines": normalized_lines(source_text),
        "summary_snapshot_lines": normalized_lines(components["snapshot"]),
        **features,
    }


def references_for_layer(
    manifest: dict[str, Any],
    routing: str,
    recipient_layer: int,
) -> list[dict[str, Any]]:
    seeds = list(manifest.get("initial_references", []))
    prior_outputs = [
        output
        for layer in manifest["layers"][: recipient_layer - 1]
        for output in layer
        if bool(output["telemetry"]["self_reported_success"])
    ]
    if routing == "cumulative":
        return seeds + prior_outputs
    if routing == "bounded_recent":
        return (seeds + prior_outputs)[-3:]
    raise ValueError(f"Unsupported routing: {routing}")


def best_reference_alignment(
    recipient: dict[str, Any],
    reference_features: list[dict[str, Any]],
) -> dict[str, Any]:
    if not reference_features:
        return {
            "best_reference_artifact": None,
            "exact_primary_match": False,
            "max_source_line_jaccard": 0.0,
            "max_summary_line_recall": 0.0,
            "max_function_jaccard": 0.0,
            "max_ast_signature_jaccard": 0.0,
            "max_string_literal_jaccard": 0.0,
        }
    candidates = []
    for reference in reference_features:
        candidate = {
            "artifact_id": reference["artifact_id"],
            "exact_primary_match": (
                recipient["primary_hash"] is not None
                and recipient["primary_hash"] == reference["primary_hash"]
            ),
            "source_line_jaccard": jaccard(
                recipient["source_lines"], reference["source_lines"]
            ),
            "summary_line_recall": recall(
                recipient["source_lines"],
                reference["summary_snapshot_lines"],
            ),
            "function_jaccard": jaccard(
                recipient["functions"], reference["functions"]
            ),
            "ast_signature_jaccard": jaccard(
                recipient["ast_signatures"], reference["ast_signatures"]
            ),
            "string_literal_jaccard": jaccard(
                recipient["strings"], reference["strings"]
            ),
        }
        candidates.append(candidate)
    best = max(
        candidates,
        key=lambda item: (
            bool(item["exact_primary_match"]),
            float(item["source_line_jaccard"]),
            float(item["summary_line_recall"]),
        ),
    )
    return {
        "best_reference_artifact": best["artifact_id"],
        "exact_primary_match": best["exact_primary_match"],
        "max_source_line_jaccard": max(
            float(item["source_line_jaccard"]) for item in candidates
        ),
        "max_summary_line_recall": max(
            float(item["summary_line_recall"]) for item in candidates
        ),
        "max_function_jaccard": max(
            float(item["function_jaccard"]) for item in candidates
        ),
        "max_ast_signature_jaccard": max(
            float(item["ast_signature_jaccard"]) for item in candidates
        ),
        "max_string_literal_jaccard": max(
            float(item["string_literal_jaccard"]) for item in candidates
        ),
    }


def pairwise_mean(values: list[frozenset[str]]) -> float:
    scores = [jaccard(left, right) for left, right in combinations(values, 2)]
    return mean(scores) if scores else 1.0


def summarize(values: list[float | int]) -> dict[str, float]:
    numeric = [float(value) for value in values]
    return {
        "min": min(numeric),
        "median": median(numeric),
        "mean": mean(numeric),
        "max": max(numeric),
    }


def audit_run(spec: dict[str, str]) -> dict[str, Any]:
    arm_root = REPO_ROOT / spec["root"] / spec["arm"]
    manifest_path = arm_root / "manifest.json"
    manifest = load_json(manifest_path)
    size_rows: list[dict[str, Any]] = []
    alignment_rows: list[dict[str, Any]] = []
    layer_rows: list[dict[str, Any]] = []

    for layer_index, layer_outputs in enumerate(manifest["layers"], start=1):
        recipient_features = [result_features(output) for output in layer_outputs]
        reference_outputs = references_for_layer(
            manifest, spec["routing"], layer_index
        )
        reference_features = [
            result_features(reference) for reference in reference_outputs
        ]

        for output, features in zip(layer_outputs, recipient_features):
            summary = str(output["artifact"]["summary"])
            components = experience_components(summary)
            telemetry = output["telemetry"]
            size_rows.append(
                {
                    "run_id": spec["run_id"],
                    "role": spec["role"],
                    "mode": manifest["assimilation_mode"],
                    "layer": layer_index,
                    "worker_id": output["worker_id"],
                    "summary_chars": len(summary),
                    "header_chars": len(components["header"]),
                    "trajectory_chars": len(components["trajectory"]),
                    "snapshot_excerpt_chars": len(components["snapshot"]),
                    "received_results": telemetry["received_results"],
                    "received_experience_chars": (
                        telemetry["received_experience_chars"]
                    ),
                    "input_tokens": telemetry["input_tokens"],
                    "output_tokens": telemetry["output_tokens"],
                    "duration_sec": telemetry["duration_sec"],
                    "self_reported_success": (
                        telemetry["self_reported_success"]
                    ),
                    "local_validation_passed": (
                        telemetry["local_validation_passed"]
                    ),
                }
            )
            alignment = best_reference_alignment(features, reference_features)
            alignment_rows.append(
                {
                    "run_id": spec["run_id"],
                    "role": spec["role"],
                    "mode": manifest["assimilation_mode"],
                    "layer": layer_index,
                    "worker_id": output["worker_id"],
                    "reference_count": len(reference_features),
                    "snapshot_hash": features["snapshot_hash"],
                    "primary_hash": features["primary_hash"],
                    **alignment,
                }
            )

        layer_rows.append(
            {
                "run_id": spec["run_id"],
                "role": spec["role"],
                "mode": manifest["assimilation_mode"],
                "layer": layer_index,
                "unique_workspace_snapshots": len(
                    {
                        item["snapshot_hash"]
                        for item in recipient_features
                        if item["snapshot_hash"] is not None
                    }
                ),
                "unique_primary_implementations": len(
                    {
                        item["primary_hash"]
                        for item in recipient_features
                        if item["primary_hash"] is not None
                    }
                ),
                "pairwise_source_line_jaccard": pairwise_mean(
                    [item["source_lines"] for item in recipient_features]
                ),
                "pairwise_function_jaccard": pairwise_mean(
                    [item["functions"] for item in recipient_features]
                ),
                "pairwise_ast_signature_jaccard": pairwise_mean(
                    [item["ast_signatures"] for item in recipient_features]
                ),
                "mean_max_prior_source_line_jaccard": mean(
                    float(row["max_source_line_jaccard"])
                    for row in alignment_rows
                    if row["run_id"] == spec["run_id"]
                    and row["layer"] == layer_index
                ),
                "mean_max_summary_line_recall": mean(
                    float(row["max_summary_line_recall"])
                    for row in alignment_rows
                    if row["run_id"] == spec["run_id"]
                    and row["layer"] == layer_index
                ),
                "exact_primary_matches": sum(
                    bool(row["exact_primary_match"])
                    for row in alignment_rows
                    if row["run_id"] == spec["run_id"]
                    and row["layer"] == layer_index
                ),
            }
        )

    return {
        "run_id": spec["run_id"],
        "role": spec["role"],
        "routing": spec["routing"],
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "mode": manifest["assimilation_mode"],
        "layers": len(manifest["layers"]),
        "workers": manifest["worker_count"],
        "size_rows": size_rows,
        "alignment_rows": alignment_rows,
        "layer_rows": layer_rows,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def short_hash(value: str | None) -> str:
    return value[:10] if value else "missing"


def main() -> None:
    audits = [audit_run(spec) for spec in RUNS]
    size_rows = [row for audit in audits for row in audit["size_rows"]]
    alignment_rows = [
        row for audit in audits for row in audit["alignment_rows"]
    ]
    layer_rows = [row for audit in audits for row in audit["layer_rows"]]

    manager_sample = (
        REPO_ROOT
        / "runs_scbench_moa_kimi_cfgpipe_cp1_recursive_synthesis_depth5_20260714"
        / "recursive_synthesis-6f605bbdeaa340a7ad79319c848f8038"
        / "manager"
        / "layer_1"
        / "synthesis.json"
    )
    manager_record = load_json(manager_sample)
    source_code = REPO_ROOT / "sec" / "scbench_miniswe.py"
    code_text = source_code.read_text(encoding="utf-8")
    required_markers = (
        TRAJECTORY_MARKER.strip(),
        SNAPSHOT_MARKER.strip(),
        "You are the intermediate aggregator in a layered",
        r"\b(pass|passes|passed|works|working|success|successful|",
        r"correct|verify|verified)\b",
    )
    missing_markers = [marker for marker in required_markers if marker not in code_text]
    if missing_markers:
        raise RuntimeError(f"Implementation markers changed: {missing_markers}")

    report = {
        "audit_date": "2026-07-15",
        "scope": (
            "Mechanism and reproducibility audit of the frozen cfgpipe "
            "cumulative treatment and prospective bounded-context control."
        ),
        "implementation_source": str(source_code),
        "implementation_source_sha256": sha256_file(source_code),
        "experience_schema": {
            "header": (
                "Worker <id>, layer <n>. Local verifier Core: <p>/<t>; "
                "pytest exit <code>."
            ),
            "trajectory": (
                "Trailing 6,000 characters from the final four assistant "
                "steps, before whole-artifact truncation."
            ),
            "snapshot": (
                "UTF-8 source snapshot excerpt under the remaining source "
                "budget, before whole-artifact truncation."
            ),
            "artifact_cap_chars": 12000,
            "recipient_per_source_cap_chars": 12000,
        },
        "self_report_admission": {
            "regex": SELF_REPORT_REGEX,
            "flags": "re.IGNORECASE",
            "scope": "Concatenation of all assistant message content.",
            "local_validation_gate": (
                "Separately requires at least three successful environment "
                "commands and the same self-report match."
            ),
            "external_evaluator_used_for_admission": False,
        },
        "manager_schema": {
            "sample_path": str(manager_sample),
            "sample_sha256": sha256_file(manager_sample),
            "sample_output_chars": manager_record["output_chars"],
            "system_instruction": (
                "Produce one shared implementation playbook for the next "
                "independent agents; retain constraints, implementation "
                "decisions, edge cases, failure-prevention rules, and "
                "validation procedures; resolve conflicts explicitly."
            ),
            "user_fields": (
                "task identifier, public specification through current "
                "round, previous shared playbook, accepted worker evidence"
            ),
            "manager_output_cap_chars": 12000,
        },
        "runs": [
            {
                key: value
                for key, value in audit.items()
                if key not in {"size_rows", "alignment_rows", "layer_rows"}
            }
            for audit in audits
        ],
        "summary_distributions": {
            audit["run_id"]: {
                "summary_chars": summarize(
                    [
                        row["summary_chars"]
                        for row in audit["size_rows"]
                    ]
                ),
                "trajectory_chars": summarize(
                    [
                        row["trajectory_chars"]
                        for row in audit["size_rows"]
                    ]
                ),
                "snapshot_excerpt_chars": summarize(
                    [
                        row["snapshot_excerpt_chars"]
                        for row in audit["size_rows"]
                    ]
                ),
                "received_experience_chars": summarize(
                    [
                        row["received_experience_chars"]
                        for row in audit["size_rows"]
                    ]
                ),
                "input_tokens": summarize(
                    [
                        row["input_tokens"]
                        for row in audit["size_rows"]
                    ]
                ),
            }
            for audit in audits
        },
        "alignment_summary": {
            audit["run_id"]: {
                "exact_primary_match_rate_after_layer_1": mean(
                    [
                        float(row["exact_primary_match"])
                        for row in audit["alignment_rows"]
                        if int(row["layer"]) >= 2
                    ]
                ),
                "mean_max_prior_source_line_jaccard_after_layer_1": mean(
                    [
                        float(row["max_source_line_jaccard"])
                        for row in audit["alignment_rows"]
                        if int(row["layer"]) >= 2
                    ]
                ),
                "mean_max_summary_line_recall_after_layer_1": mean(
                    [
                        float(row["max_summary_line_recall"])
                        for row in audit["alignment_rows"]
                        if int(row["layer"]) >= 2
                    ]
                ),
                "first_single_primary_implementation_layer": next(
                    (
                        int(row["layer"])
                        for row in audit["layer_rows"]
                        if int(row["unique_primary_implementations"]) == 1
                    ),
                    None,
                ),
            }
            for audit in audits
        },
        "layer_rows": layer_rows,
        "interpretation_guards": [
            (
                "Exact primary-file matches are direct implementation "
                "alignment, but do not by themselves identify whether agents "
                "copied text or independently regenerated equivalent code."
            ),
            (
                "Summary-line recall measures verbatim normalized-line "
                "availability in the delivered snapshot excerpt; it is not a "
                "causal attribution estimator."
            ),
            (
                "Workspace hash differences can be caused by inert scratch or "
                "test files; primary implementation hashes are reported "
                "separately."
            ),
        ],
    }
    OUTPUT_JSON.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    write_csv(OUTPUT_SIZE_CSV, size_rows)
    write_csv(OUTPUT_ALIGNMENT_CSV, alignment_rows)
    write_csv(OUTPUT_LAYER_CSV, layer_rows)

    bounded = next(
        audit for audit in audits if audit["run_id"] == "cfgpipe-bounded-control"
    )
    bounded_l4 = next(
        row for row in bounded["layer_rows"] if row["layer"] == 4
    )
    md_lines = [
        "# SCBench Transfer Mechanism Audit",
        "",
        "Generated from frozen manifests and local snapshots on 2026-07-15.",
        "",
        "## Experience and admission",
        "",
        "- Artifact body: worker/layer header, the trailing part of the final "
        "four assistant steps, and a source-snapshot excerpt.",
        "- Per-artifact and per-recipient-source cap: 12,000 characters.",
        f"- Self-report regex: `{SELF_REPORT_REGEX}` with `re.IGNORECASE`.",
        "- The self-report gate scans all assistant text. It does not read the "
        "external SCBench evaluator.",
        "- The stricter local proxy additionally requires at least three "
        "successful environment commands.",
        "",
        "## Summary sizes",
        "",
        "| Run | Summary chars (median, range) | Received chars "
        "(median, range) | Input tokens (median, range) |",
        "|---|---:|---:|---:|",
    ]
    for audit in audits:
        distributions = report["summary_distributions"][audit["run_id"]]
        summary = distributions["summary_chars"]
        received = distributions["received_experience_chars"]
        inputs = distributions["input_tokens"]
        md_lines.append(
            f"| {audit['run_id']} | {summary['median']:.0f} "
            f"({summary['min']:.0f}-{summary['max']:.0f}) | "
            f"{received['median']:.0f} "
            f"({received['min']:.0f}-{received['max']:.0f}) | "
            f"{inputs['median']:.0f} "
            f"({inputs['min']:.0f}-{inputs['max']:.0f}) |"
        )
    md_lines.extend(
        [
            "",
            "## Alignment",
            "",
            "| Run | Exact primary match after L1 | Mean max source-line "
            "Jaccard | Mean summary-line recall | First single primary impl. |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for audit in audits:
        alignment = report["alignment_summary"][audit["run_id"]]
        md_lines.append(
            f"| {audit['run_id']} | "
            f"{alignment['exact_primary_match_rate_after_layer_1']:.3f} | "
            f"{alignment['mean_max_prior_source_line_jaccard_after_layer_1']:.3f} | "
            f"{alignment['mean_max_summary_line_recall_after_layer_1']:.3f} | "
            f"L{alignment['first_single_primary_implementation_layer']} |"
        )
    md_lines.extend(
        [
            "",
            "## Layer-4 bounded-context audit",
            "",
            f"- Whole-workspace snapshots: "
            f"{bounded_l4['unique_workspace_snapshots']} unique.",
            f"- Primary `cfgpipe.py` implementations: "
            f"{bounded_l4['unique_primary_implementations']} unique.",
            "- Therefore the apparent layer-4 workspace re-diversification is "
            "not a primary-implementation re-diversification; it is caused by "
            "an extra non-entrypoint workspace file.",
            "",
            "## Files",
            "",
            f"- JSON audit: `{OUTPUT_JSON.relative_to(REPO_ROOT)}`",
            f"- Size table: `{OUTPUT_SIZE_CSV.relative_to(REPO_ROOT)}`",
            f"- Alignment table: `{OUTPUT_ALIGNMENT_CSV.relative_to(REPO_ROOT)}`",
            f"- Layer table: `{OUTPUT_LAYER_CSV.relative_to(REPO_ROOT)}`",
        ]
    )
    OUTPUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    main_first = audits[0]["size_rows"][0]
    main_manifest = load_json(Path(audits[0]["manifest"]))
    example_summary = str(main_manifest["layers"][0][0]["artifact"]["summary"])
    example_components = experience_components(example_summary)
    manager_excerpt = str(manager_record["playbook"])[:1200]
    schema_lines = [
        "# Experience Artifact and Manager Schema",
        "",
        "This file records the exact experiment-facing schema used by the "
        "frozen SCBench MoA runs. External evaluator outcomes are logged after "
        "execution but are not supplied to self-report recipients.",
        "",
        "## Worker artifact",
        "",
        "```text",
        "Worker <worker_id>, layer <layer>.",
        "Local verifier Core: <passed>/<total>; pytest exit <code>.",
        "Recent MiniSWE actions and reasoning:",
        "<trailing 6,000 characters from the final four assistant messages>",
        "Resulting source snapshot excerpt:",
        "<UTF-8 source files, followed by whole-artifact truncation at 12,000 chars>",
        "```",
        "",
        "When the artifact is admitted by a self-report policy, the `Local "
        "verifier Core:` line is replaced with:",
        "",
        "```text",
        "Agent completion report: accepted without an independent smoke check; "
        "external evaluation withheld.",
        "```",
        "",
        "The admission expression is:",
        "",
        f"```python\nre.search(r\"{SELF_REPORT_REGEX}\", assistant_text, "
        "flags=re.IGNORECASE)\n```",
        "",
        "## Anonymized worker example",
        "",
        "Header:",
        "",
        "```text\n"
        + example_components["header"].strip()[:400]
        + "\n```",
        "",
        "Trajectory excerpt:",
        "",
        "```text\n"
        + example_components["trajectory"].strip()[:900]
        + "\n```",
        "",
        "Snapshot excerpt:",
        "",
        "```text\n"
        + example_components["snapshot"].strip()[:900]
        + "\n```",
        "",
        "## Recursive manager",
        "",
        "System instruction fields: produce one shared implementation playbook; "
        "retain constraints, decisions, edge cases, failure-prevention rules, "
        "and validation procedures; resolve conflicts; return only the "
        "playbook.",
        "",
        "User message fields: task identifier, public specification through the "
        "current layer, previous shared playbook, and newly accepted sources.",
        "",
        "Example playbook excerpt:",
        "",
        "```text",
        manager_excerpt,
        "```",
        "",
        "## Provenance",
        "",
        f"- Implementation: `{source_code.relative_to(REPO_ROOT)}` "
        f"(`{short_hash(sha256_file(source_code))}`)",
        f"- Frozen cumulative manifest: "
        f"`{Path(audits[0]['manifest']).relative_to(REPO_ROOT)}`",
        f"- Example summary chars: {main_first['summary_chars']}",
        f"- Manager example: `{manager_sample.relative_to(REPO_ROOT)}` "
        f"(`{short_hash(sha256_file(manager_sample))}`)",
    ]
    OUTPUT_SCHEMA_MD.write_text(
        "\n".join(schema_lines) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["alignment_summary"], indent=2))
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")
    print(f"Wrote {OUTPUT_SCHEMA_MD}")


if __name__ == "__main__":
    main()
