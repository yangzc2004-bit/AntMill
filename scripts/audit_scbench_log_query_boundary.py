from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_log_query_cp1_three_arm_boundary_depth3_config.json"
)
FREEZE = CONFIG.with_suffix(".freeze.json")
RUN_ROOT = (
    REPO_ROOT
    / "runs_scbench_moa_kimi_maas_log_query_cp1_"
    "three_arm_boundary_depth3_r1_20260716"
)
OUTPUT_JSON = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_log_query_cp1_three_arm_boundary_depth3_audit_20260716.json"
)
OUTPUT_MD = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_log_query_cp1_three_arm_boundary_depth3_audit_20260716.md"
)
GENERATED_ROOT = REPO_ROOT / "paper_draft" / "generated" / "moa_paper"
OUTPUT_LAYER_CSV = GENERATED_ROOT / "log_query_boundary_layers.csv"
OUTPUT_SUMMARY_CSV = GENERATED_ROOT / "log_query_boundary_summary.csv"

EXPECTED_CORE_TOTAL = 10
EXPECTED_ALL_TOTAL = 134
EXPECTED_HASH = (
    "3deecb18f814ddda765ab2720264da076f8361d7646fe9c922af4c52d11fddac"
)
MODE_LABELS = {
    "no_transfer": "no_transfer",
    "bounded_recent_self_report_acceptance": "bounded_recent",
    "bounded_diverse_self_report_acceptance": "bounded_diverse",
}
BLINDING_PATTERNS = (
    re.compile(r"(?:Local verifier )?Core:\s*\d+/\d+"),
    re.compile(r"\b\d+/134\b"),
    re.compile(r"\ball_passed\b"),
    re.compile(r"\btest_collection_hash\b"),
)
PROHIBITED_PATTERNS = (
    re.compile(r"\.evaluation_tests", re.IGNORECASE),
    re.compile(r"(?:^|\s)/problems(?:/|\s|$)", re.IGNORECASE),
    re.compile(r"(?:^|\s)/outputs(?:/|\s|$)", re.IGNORECASE),
    re.compile(r"tests?/test_checkpoint_1\.py", re.IGNORECASE),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primary_hash(workspace: str) -> str | None:
    path = Path(workspace) / "logql.py"
    return file_hash(path) if path.is_file() else None


def checkpoint(output: dict[str, Any]) -> Path:
    return Path(str(output["workspace"])).parent


def inference_valid(path: Path) -> bool:
    record = load_json(path)
    usage = record.get("usage", {})
    return not (
        bool(record.get("had_error"))
        or record.get("error_message")
        or int(usage.get("steps", 0) or 0) <= 0
    )


def prompt_blinded(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return not any(pattern.search(text) for pattern in BLINDING_PATTERNS)


def trajectory_clean(path: Path) -> bool:
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if str(record.get("role", "")).lower() != "assistant":
            continue
        content = str(record.get("content", ""))
        if any(pattern.search(content) for pattern in PROHIBITED_PATTERNS):
            return False
    return True


def first_lockin(layer_rows: list[dict[str, Any]]) -> int | None:
    for current, following in zip(layer_rows, layer_rows[1:]):
        if (
            int(current["unique_primary_implementations"]) == 1
            and int(following["unique_primary_implementations"]) == 1
        ):
            return int(current["layer"])
    return None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def verify_freeze() -> dict[str, Any]:
    freeze = load_json(FREEZE)
    failures = []
    if file_hash(CONFIG) != str(freeze["sha256"]):
        failures.append("config")
    for relative, expected in freeze["implementation_files"].items():
        if file_hash(REPO_ROOT / relative) != str(expected):
            failures.append(f"implementation:{relative}")
    return {
        "passed": not failures,
        "failures": failures,
        "config_sha256": file_hash(CONFIG),
    }


def audit_arm(
    mode: str,
    arm_id: str,
) -> dict[str, Any]:
    arm_root = RUN_ROOT / arm_id
    manifest_path = arm_root / "manifest.json"
    manifest = load_json(manifest_path)
    label = MODE_LABELS[mode]
    expected_references = 0 if mode == "no_transfer" else 3
    layer_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for layer_index, outputs in enumerate(manifest["layers"], start=1):
        primary_hashes: list[str] = []
        all_passed: list[int] = []
        core_passed: list[int] = []
        input_tokens: list[int] = []
        output_tokens: list[int] = []
        durations: list[float] = []
        received_chars: list[int] = []
        reference_counts: list[int] = []

        for output in outputs:
            worker_id = str(output["worker_id"])
            root = checkpoint(output)
            verification = output["verification"]
            telemetry = output["telemetry"]
            evaluation = load_json(root / "evaluation.json")
            checks = {
                "core_total": (
                    int(verification["core_total"]) == EXPECTED_CORE_TOTAL
                ),
                "all_total": (
                    int(verification["all_total"]) == EXPECTED_ALL_TOTAL
                ),
                "hash": (
                    str(verification["test_collection_hash"]) == EXPECTED_HASH
                    and str(evaluation["test_collection_hash"]) == EXPECTED_HASH
                ),
                "infrastructure": not (
                    bool(verification["infrastructure_failure"])
                    or bool(evaluation["infrastructure_failure"])
                ),
                "collection": (
                    int(evaluation["pytest_collected"]) == EXPECTED_ALL_TOTAL
                ),
                "inference": inference_valid(root / "inference_result.json"),
                "references": (
                    int(telemetry["received_results"]) == expected_references
                ),
                "blinding": (
                    True
                    if mode == "no_transfer"
                    else prompt_blinded(root / "prompt.txt")
                ),
                "prohibited_access": trajectory_clean(
                    root / "agent" / "trajectory.jsonl"
                ),
            }
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                failures.append(
                    {
                        "layer": layer_index,
                        "worker_id": worker_id,
                        "failed_checks": failed,
                    }
                )

            identity = primary_hash(str(output["workspace"]))
            if identity is not None:
                primary_hashes.append(identity)
            all_passed.append(int(verification["all_passed"]))
            core_passed.append(int(verification["core_passed"]))
            input_tokens.append(int(telemetry["input_tokens"]))
            output_tokens.append(int(telemetry["output_tokens"]))
            durations.append(float(telemetry["duration_sec"]))
            received_chars.append(int(telemetry["received_experience_chars"]))
            reference_counts.append(int(telemetry["received_results"]))

        layer_rows.append(
            {
                "arm": label,
                "mode": mode,
                "layer": layer_index,
                "unique_primary_implementations": len(set(primary_hashes)),
                "mean_core_passed": mean(core_passed),
                "min_core_passed": min(core_passed),
                "max_core_passed": max(core_passed),
                "mean_all_passed": mean(all_passed),
                "min_all_passed": min(all_passed),
                "max_all_passed": max(all_passed),
                "core_complete_workers": sum(
                    value == EXPECTED_CORE_TOTAL for value in core_passed
                ),
                "total_input_tokens": sum(input_tokens),
                "total_output_tokens": sum(output_tokens),
                "mean_duration_sec": mean(durations),
                "mean_received_results": mean(reference_counts),
                "mean_received_experience_chars": mean(received_chars),
            }
        )

    post_rows = [row for row in layer_rows if int(row["layer"]) >= 2]
    summary = {
        "arm": label,
        "mode": mode,
        "arm_id": arm_id,
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "manifest_sha256": file_hash(manifest_path),
        "diversity_auc_layers_2_3": sum(
            int(row["unique_primary_implementations"]) for row in post_rows
        ),
        "layer_2_unique_implementations": int(
            layer_rows[1]["unique_primary_implementations"]
        ),
        "layer_3_unique_implementations": int(
            layer_rows[2]["unique_primary_implementations"]
        ),
        "first_two_layer_lockin": first_lockin(layer_rows),
        "mean_core_passed": mean(
            float(row["mean_core_passed"]) for row in layer_rows
        ),
        "mean_all_passed": mean(
            float(row["mean_all_passed"]) for row in layer_rows
        ),
        "minimum_worker_core_passed": min(
            int(row["min_core_passed"]) for row in layer_rows
        ),
        "minimum_worker_all_passed": min(
            int(row["min_all_passed"]) for row in layer_rows
        ),
        "total_input_tokens": sum(
            int(row["total_input_tokens"]) for row in layer_rows
        ),
        "total_output_tokens": sum(
            int(row["total_output_tokens"]) for row in layer_rows
        ),
        "mean_duration_sec": mean(
            float(row["mean_duration_sec"]) for row in layer_rows
        ),
        "valid": not failures,
    }
    return {
        "summary": summary,
        "layer_rows": layer_rows,
        "failures": failures,
    }


def main() -> None:
    freeze = verify_freeze()
    curve = load_json(RUN_ROOT / "curve_report.json")
    audits = [
        audit_arm(mode, str(curve["arms"][mode]))
        for mode in (
            "no_transfer",
            "bounded_recent_self_report_acceptance",
            "bounded_diverse_self_report_acceptance",
        )
    ]
    summaries = [audit["summary"] for audit in audits]
    layer_rows = [row for audit in audits for row in audit["layer_rows"]]
    by_arm = {summary["arm"]: summary for summary in summaries}
    bounded = by_arm["bounded_recent"]
    diverse = by_arm["bounded_diverse"]
    no_transfer = by_arm["no_transfer"]

    cross_task_support = (
        int(bounded["layer_2_unique_implementations"]) == 1
        and int(bounded["layer_3_unique_implementations"]) == 1
        and int(no_transfer["layer_2_unique_implementations"]) >= 2
        and int(no_transfer["layer_3_unique_implementations"]) >= 2
    )
    boundary = (
        int(bounded["layer_2_unique_implementations"]) >= 2
        or int(bounded["layer_3_unique_implementations"]) >= 2
    )
    mitigation_support = (
        int(diverse["diversity_auc_layers_2_3"])
        > int(bounded["diversity_auc_layers_2_3"])
    )
    strong_mitigation_criterion_met = (
        int(diverse["layer_3_unique_implementations"]) >= 2
        and float(diverse["mean_core_passed"])
        >= float(bounded["mean_core_passed"])
    )
    mitigation_identifiable = (
        int(bounded["diversity_auc_layers_2_3"])
        < int(no_transfer["diversity_auc_layers_2_3"])
    )
    strong_mitigation_support = (
        mitigation_support
        and strong_mitigation_criterion_met
        and mitigation_identifiable
    )
    validity = freeze["passed"] and all(
        bool(summary["valid"]) for summary in summaries
    )

    report = {
        "audit_date": "2026-07-16",
        "config": str(CONFIG.relative_to(REPO_ROOT)),
        "freeze": freeze,
        "validity_passed": validity,
        "arm_failures": {
            audit["summary"]["arm"]: audit["failures"] for audit in audits
        },
        "summaries": summaries,
        "layer_rows": layer_rows,
        "outcomes": {
            "cross_task_lockin_support": cross_task_support,
            "cross_task_boundary": boundary,
            "mitigation_identifiable": mitigation_identifiable,
            "mitigation_support": mitigation_support,
            "strong_mitigation_criterion_met": (
                strong_mitigation_criterion_met
            ),
            "strong_mitigation_support": strong_mitigation_support,
        },
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_csv(OUTPUT_LAYER_CSV, layer_rows)
    write_csv(OUTPUT_SUMMARY_CSV, summaries)

    md = [
        "# Prospective log_query Boundary Audit",
        "",
        f"- Freeze passed: **{freeze['passed']}**",
        f"- All validity gates passed: **{validity}**",
        f"- Cross-task lock-in support: **{cross_task_support}**",
        f"- Cross-task boundary observed: **{boundary}**",
        f"- Mitigation effect identifiable: **{mitigation_identifiable}**",
        f"- Diversity-routing support: **{mitigation_support}**",
        "- Raw strong-mitigation criterion met: "
        f"**{strong_mitigation_criterion_met}**",
        f"- Strong mitigation support: **{strong_mitigation_support}**",
        "",
        "## Three-arm summary",
        "",
        "| Arm | Diversity AUC L2-L3 | L2 unique | L3 unique | "
        "Mean Core | Mean all tests | Minimum Core | Input tokens | "
        "Mean duration |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        md.append(
            f"| {summary['arm']} | "
            f"{summary['diversity_auc_layers_2_3']} | "
            f"{summary['layer_2_unique_implementations']} | "
            f"{summary['layer_3_unique_implementations']} | "
            f"{summary['mean_core_passed']:.2f}/10 | "
            f"{summary['mean_all_passed']:.2f}/134 | "
            f"{summary['minimum_worker_core_passed']}/10 | "
            f"{summary['total_input_tokens']:,} | "
            f"{summary['mean_duration_sec']:.1f}s |"
        )
    md.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "The result is interpreted strictly under the frozen "
                "three-layer rules. A boundary result means that the exact "
                "cfgpipe lock-in pattern did not reproduce on log_query within "
                "the observed horizon; it does not prove absence at greater "
                "depth."
                if boundary
                else "The bounded-recent arm reproduced two-layer exact "
                "implementation lock-in while no-transfer retained multiple "
                "implementations, providing a prospective second-task "
                "replication within the three-layer horizon."
            ),
            "",
            (
                "Because bounded-recent already retained the maximum three "
                "implementations at both measured post-transfer layers, the "
                "mitigation contrast is ceiling-limited. The diverse arm met "
                "the raw layer-3 diversity-and-Core criterion, but no "
                "incremental mitigation effect is identifiable."
                if not mitigation_identifiable
                else "The bounded-recent arm left measurable diversity "
                "headroom, so the mitigation contrast is identifiable."
            ),
            "",
            "## Outputs",
            "",
            f"- JSON: `{OUTPUT_JSON.relative_to(REPO_ROOT)}`",
            f"- Layer CSV: `{OUTPUT_LAYER_CSV.relative_to(REPO_ROOT)}`",
            f"- Summary CSV: `{OUTPUT_SUMMARY_CSV.relative_to(REPO_ROOT)}`",
        ]
    )
    OUTPUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(report["outcomes"], indent=2))
    print(f"Validity passed: {validity}")
    print(f"Wrote {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
