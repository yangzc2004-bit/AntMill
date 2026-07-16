from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPO_ROOT / "benchmarks" / "scbench"
GENERATED_ROOT = REPO_ROOT / "paper_draft" / "generated" / "moa_paper"
OUTPUT_JSON = AUDIT_ROOT / "kimi_cfgpipe_lockin_replication_audit_20260715.json"
OUTPUT_MD = AUDIT_ROOT / "kimi_cfgpipe_lockin_replication_audit_20260715.md"
OUTPUT_CSV = GENERATED_ROOT / "lockin_replication_layers.csv"

BLINDING_PATTERNS = {
    "numeric_core_score": re.compile(r"(?:Local verifier )?Core:\s*\d+/\d+"),
    "all_test_score": re.compile(r"\b\d+/37\b"),
    "all_passed_field": re.compile(r"\ball_passed\b"),
    "test_hash_field": re.compile(r"\btest_collection_hash\b"),
}
PROHIBITED_PATTERNS = {
    "evaluation_tests": re.compile(r"\.evaluation_tests", re.IGNORECASE),
    "frozen_problem_mount": re.compile(
        r"(?:^|\s)/problems(?:/|\s|$)", re.IGNORECASE
    ),
    "evaluation_output_mount": re.compile(
        r"(?:^|\s)/outputs(?:/|\s|$)", re.IGNORECASE
    ),
    "hidden_test_file": re.compile(
        r"tests?/test_checkpoint_1\.py", re.IGNORECASE
    ),
}

CFGPipe_HASH = (
    "6ee2bfc068272a7fbc92599619db56b345cd93ecd3a321e791fa496a6a0f0615"
)
LOG_QUERY_HASH = (
    "3deecb18f814ddda765ab2720264da076f8361d7646fe9c922af4c52d11fddac"
)

RUNS = (
    {
        "run_id": "kimi-coding-no-transfer",
        "role": "no_transfer_control",
        "provider": "Kimi Coding",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_cfgpipe_cp1_recursive_synthesis_depth5_20260714",
        "arm_id": "no_transfer-e92d8453f0d84861aa032e075e0257c8",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
        "recipient_blinding": True,
    },
    {
        "run_id": "kimi-coding-self-report-r1",
        "role": "legacy_bootstrap_score_exposure",
        "provider": "Kimi Coding",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_cfgpipe_cp1_self_report_cumulative_depth8_r1_20260714",
        "arm_id": "cumulative_self_report_acceptance-f2b7a1da5b7d46ddaf4c32f82b443573",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
    },
    {
        "run_id": "kimi-coding-self-report-r2",
        "role": "independent_self_report_replication",
        "provider": "Kimi Coding",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_cfgpipe_cp1_self_report_cumulative_depth10_r2_20260714",
        "arm_id": "cumulative_self_report_acceptance-4997d3ec1cdf498c9ea5a6f650d2844b",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
        "recipient_blinding": True,
    },
    {
        "run_id": "kimi-maas-self-report-r1",
        "role": "independent_self_report_replication",
        "provider": "ModelArts MaaS",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_maas_cfgpipe_cp1_self_report_depth12_clean_extension_20260715",
        "arm_id": "cumulative_self_report_acceptance-76477a1fd4384da3a1a069b3fe2b32e4",
        "manifest_file": "manifest_depth12.json",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
        "recipient_blinding": True,
    },
    {
        "run_id": "kimi-maas-no-transfer",
        "role": "no_transfer_control",
        "provider": "ModelArts MaaS",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_maas_cfgpipe_cp1_depth12_no_transfer_r1_20260715",
        "arm_id": "no_transfer-02db19c347a0481a95ee08ca1752f7bd",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
    },
    {
        "run_id": "kimi-maas-self-report-r2",
        "role": "frozen_main_self_report",
        "provider": "ModelArts MaaS",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_maas_cfgpipe_cp1_depth12_self_report_r2_20260715",
        "arm_id": "cumulative_self_report_acceptance-426bc68aaa4b4e8c8f2aad850c75a89b",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
        "recipient_blinding": True,
    },
    {
        "run_id": "kimi-maas-bounded-context-r1",
        "role": "prospective_context_growth_control",
        "provider": "ModelArts MaaS",
        "problem": "cfgpipe",
        "run_root": "runs_scbench_moa_kimi_maas_cfgpipe_cp1_bounded_context_depth6_r1_20260715",
        "arm_id_from_report": "bounded_recent_self_report_acceptance",
        "expected_core_total": 4,
        "expected_all_total": 37,
        "expected_hash": CFGPipe_HASH,
        "recipient_blinding": True,
    },
    {
        "run_id": "log-query-no-transfer",
        "role": "second_task_no_transfer",
        "provider": "Kimi Coding",
        "problem": "log_query",
        "run_root": "runs_scbench_moa_kimi_log_query_cp1_recursive_synthesis_depth5_20260714",
        "arm_id": "no_transfer-0e9568d083944a74922b08223c7088dc",
        "expected_core_total": 10,
        "expected_all_total": 134,
        "expected_hash": LOG_QUERY_HASH,
    },
    {
        "run_id": "log-query-cumulative-verified",
        "role": "second_task_transfer_boundary",
        "provider": "Kimi Coding",
        "problem": "log_query",
        "run_root": "runs_scbench_moa_kimi_log_query_cp1_bootstrapped_cumulative_depth5_20260714",
        "arm_id": "cumulative_success-c62abb3ab42d41bdb5c57fc159f292ba",
        "expected_core_total": 10,
        "expected_all_total": 134,
        "expected_hash": LOG_QUERY_HASH,
    },
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def directory_hash(path: Path) -> str | None:
    if not path.is_dir():
        return None
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        return None
    digest = hashlib.sha256()
    for file_path in files:
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def failed_tests(evaluation: dict[str, Any]) -> frozenset[str]:
    values: list[str] = []
    for group in evaluation.get("tests", {}).values():
        values.extend(str(item) for item in group.get("failed", []))
    return frozenset(values)


def pairwise_jaccard(signatures: list[frozenset[str]]) -> float:
    values: list[float] = []
    for left, right in combinations(signatures, 2):
        union = left | right
        values.append(1.0 if not union else len(left & right) / len(union))
    return mean(values) if values else 1.0


def report_arm_id(spec: dict[str, Any], run_root: Path) -> str:
    if "arm_id" in spec:
        return str(spec["arm_id"])
    report = load_json(run_root / "curve_report.json")
    return str(report["arms"][spec["arm_id_from_report"]])


def audit_run(spec: dict[str, Any]) -> dict[str, Any]:
    run_root = REPO_ROOT / str(spec["run_root"])
    arm_id = report_arm_id(spec, run_root)
    arm_root = run_root / arm_id
    manifest = load_json(
        arm_root / str(spec.get("manifest_file", "manifest.json"))
    )
    layer_rows: list[dict[str, Any]] = []
    target_failures: list[dict[str, Any]] = []
    inference_failures: list[dict[str, Any]] = []
    stale_evaluation_files: list[dict[str, Any]] = []
    blinding_hits: list[dict[str, Any]] = []
    prohibited_hits: list[dict[str, Any]] = []

    for layer_index, layer_outputs in enumerate(manifest["layers"], start=1):
        scores: list[int] = []
        snapshots: list[str] = []
        signatures: list[frozenset[str]] = []
        reference_counts: list[int] = []
        experience_chars: list[int] = []
        input_tokens: list[int] = []

        for output in layer_outputs:
            worker_id = str(output["worker_id"])
            checkpoint = (
                arm_root
                / "workers"
                / worker_id
                / f"layer_{layer_index}"
                / "native_output"
                / str(spec["problem"])
                / "checkpoint_1"
            )
            evaluation = load_json(checkpoint / "evaluation.json")
            inference = load_json(checkpoint / "inference_result.json")
            verification = output["verification"]
            telemetry = output["telemetry"]

            if spec.get("recipient_blinding"):
                prompt = (checkpoint / "prompt.txt").read_text(
                    encoding="utf-8"
                )
                for label, pattern in BLINDING_PATTERNS.items():
                    if pattern.search(prompt):
                        blinding_hits.append(
                            {
                                "worker_id": worker_id,
                                "layer": layer_index,
                                "pattern": label,
                            }
                        )

            trajectory_path = checkpoint / "agent" / "trajectory.jsonl"
            if trajectory_path.is_file():
                for line in trajectory_path.read_text(
                    encoding="utf-8"
                ).splitlines():
                    if not line.strip():
                        continue
                    message = json.loads(line)
                    if str(message.get("role", "")).lower() != "assistant":
                        continue
                    content = str(message.get("content", ""))
                    for label, pattern in PROHIBITED_PATTERNS.items():
                        if pattern.search(content):
                            prohibited_hits.append(
                                {
                                    "worker_id": worker_id,
                                    "layer": layer_index,
                                    "pattern": label,
                                }
                            )

            target_ok = (
                int(verification["core_total"])
                == int(spec["expected_core_total"])
                and int(verification["all_total"])
                == int(spec["expected_all_total"])
                and str(verification["test_collection_hash"])
                == str(spec["expected_hash"])
                and not bool(verification["infrastructure_failure"])
            )
            if not target_ok:
                target_failures.append(
                    {"worker_id": worker_id, "layer": layer_index}
                )
            evaluation_current = (
                int(evaluation["pytest_collected"])
                == int(spec["expected_all_total"])
                and str(evaluation["test_collection_hash"])
                == str(spec["expected_hash"])
                and not bool(evaluation["infrastructure_failure"])
            )
            if not evaluation_current:
                stale_evaluation_files.append(
                    {"worker_id": worker_id, "layer": layer_index}
                )

            usage = inference.get("usage", {})
            steps = int(usage.get("steps", 0))
            if (
                bool(inference.get("had_error"))
                or inference.get("error_message")
                or steps <= 0
            ):
                inference_failures.append(
                    {"worker_id": worker_id, "layer": layer_index}
                )

            scores.append(int(verification["all_passed"]))
            snapshot = directory_hash(checkpoint / "snapshot")
            if snapshot is not None:
                snapshots.append(snapshot)
            if evaluation_current:
                signatures.append(failed_tests(evaluation))
            reference_counts.append(int(telemetry["received_results"]))
            experience_chars.append(
                int(telemetry["received_experience_chars"])
            )
            input_tokens.append(int(telemetry["input_tokens"]))

        snapshot_counts = Counter(snapshots)
        signature_counts = Counter(signatures)
        full_snapshot_convergence = (
            len(snapshots) == len(layer_outputs)
            and len(snapshot_counts) == 1
        )
        layer_rows.append(
            {
                "run_id": spec["run_id"],
                "role": spec["role"],
                "provider": spec["provider"],
                "problem": spec["problem"],
                "layer": layer_index,
                "workers": len(layer_outputs),
                "mean_all_score": mean(scores)
                / int(spec["expected_all_total"]),
                "worker_all_passed": scores,
                "valid_snapshots": len(snapshots),
                "unique_valid_snapshots": len(snapshot_counts),
                "dominant_snapshot_share": (
                    max(snapshot_counts.values()) / len(snapshots)
                    if snapshots
                    else 0.0
                ),
                "full_snapshot_convergence": full_snapshot_convergence,
                "valid_failure_signatures": len(signatures),
                "unique_failure_signatures": len(signature_counts),
                "dominant_failure_signature_share": (
                    max(signature_counts.values()) / len(signatures)
                    if signatures
                    else None
                ),
                "mean_pairwise_failure_jaccard": (
                    pairwise_jaccard(signatures) if signatures else None
                ),
                "mean_received_results": mean(reference_counts),
                "mean_received_experience_chars": mean(experience_chars),
                "total_input_tokens": sum(input_tokens),
            }
        )

    consecutive_starts = [
        left["layer"]
        for left, right in zip(layer_rows, layer_rows[1:])
        if left["full_snapshot_convergence"]
        and right["full_snapshot_convergence"]
    ]
    return {
        "run_id": spec["run_id"],
        "role": spec["role"],
        "provider": spec["provider"],
        "problem": spec["problem"],
        "run_root": spec["run_root"],
        "arm_id": arm_id,
        "layers": layer_rows,
        "summary": {
            "depth": len(layer_rows),
            "target_consistency_passed": not target_failures,
            "model_query_integrity_passed": not inference_failures,
            "target_failures": target_failures,
            "inference_failures": inference_failures,
            "stale_evaluation_files": stale_evaluation_files,
            "recipient_blinding_passed": not blinding_hits,
            "recipient_blinding_hits": blinding_hits,
            "prohibited_access_passed": not prohibited_hits,
            "prohibited_access_hits": prohibited_hits,
            "full_snapshot_convergence_layers": [
                row["layer"]
                for row in layer_rows
                if row["full_snapshot_convergence"]
            ],
            "first_two_layer_lockin_start": (
                min(consecutive_starts) if consecutive_starts else None
            ),
            "terminal_unique_valid_snapshots": layer_rows[-1][
                "unique_valid_snapshots"
            ],
            "terminal_failure_jaccard": layer_rows[-1][
                "mean_pairwise_failure_jaccard"
            ],
            "terminal_mean_all_score": layer_rows[-1]["mean_all_score"],
            "terminal_mean_received_results": layer_rows[-1][
                "mean_received_results"
            ],
        },
    }


def write_csv(runs: list[dict[str, Any]]) -> None:
    rows = []
    for run in runs:
        for row in run["layers"]:
            rows.append(
                {
                    **{
                        key: value
                        for key, value in row.items()
                        if key != "worker_all_passed"
                    },
                    "worker_all_passed": "|".join(
                        str(value) for value in row["worker_all_passed"]
                    ),
                }
            )
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(audit: dict[str, Any]) -> None:
    by_id = {run["run_id"]: run for run in audit["runs"]}
    lines = [
        "# Kimi cfgpipe lock-in replication and context-control audit",
        "",
        "## Decision",
        "",
        audit["decision"]["statement"],
        "",
        "## Run summary",
        "",
        "| Run | Role | Depth | First two-layer exact lock-in | Terminal snapshots | Terminal score |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for run in audit["runs"]:
        summary = run["summary"]
        start = summary["first_two_layer_lockin_start"]
        lines.append(
            f"| {run['run_id']} | {run['role']} | {summary['depth']} | "
            f"{start if start is not None else '--'} | "
            f"{summary['terminal_unique_valid_snapshots']} | "
            f"{summary['terminal_mean_all_score']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            "- The two additional lock-in replications are independent trajectories, but the lock-in metric was audited retrospectively.",
            "- The earliest Kimi Coding r1 trajectory exposed bootstrap Core scores and is retained only as a protocol-drift observation.",
            "- The bounded-context arm prospectively fixes reference count at three; it does not equalize total tokens with no transfer.",
            "- The log-query comparison is a second-task boundary with strict Core-gated transfer, not an exchangeable replication of self-report transfer.",
            "- No layer is treated as an independent statistical sample.",
            "",
            "## Key source paths",
            "",
            f"- JSON audit: `{OUTPUT_JSON.relative_to(REPO_ROOT)}`",
            f"- Layer source data: `{OUTPUT_CSV.relative_to(REPO_ROOT)}`",
            f"- Bounded run: `{by_id['kimi-maas-bounded-context-r1']['run_root']}`",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    runs = [audit_run(dict(spec)) for spec in RUNS]
    by_id = {run["run_id"]: run for run in runs}
    independent = all(
        by_id[run_id]["summary"]["first_two_layer_lockin_start"] is not None
        for run_id in (
            "kimi-coding-self-report-r2",
            "kimi-maas-self-report-r1",
        )
    )
    controls_clean = all(
        by_id[run_id]["summary"]["first_two_layer_lockin_start"] is None
        for run_id in (
            "kimi-coding-no-transfer",
            "kimi-maas-no-transfer",
        )
    )
    bounded = by_id["kimi-maas-bounded-context-r1"]
    bounded_reference_count = all(
        row["mean_received_results"] == 3 for row in bounded["layers"]
    )
    bounded_lockin = (
        bounded["summary"]["first_two_layer_lockin_start"] is not None
    )
    all_valid = all(
        run["summary"]["target_consistency_passed"]
        and run["summary"]["model_query_integrity_passed"]
        and run["summary"]["recipient_blinding_passed"]
        and run["summary"]["prohibited_access_passed"]
        for run in runs
    )
    bounded_config = (
        AUDIT_ROOT / "kimi_maas_cfgpipe_cp1_bounded_context_depth6_config.json"
    )
    bounded_freeze = load_json(
        AUDIT_ROOT
        / "kimi_maas_cfgpipe_cp1_bounded_context_depth6_config.freeze.json"
    )
    bounded_config_hash_passed = (
        file_hash(bounded_config) == str(bounded_freeze["sha256"])
    )
    all_valid = all_valid and bounded_config_hash_passed

    if bounded_lockin and bounded_reference_count:
        context_statement = (
            "The prospective bounded-transfer arm also reaches exact "
            "implementation lock-in while reference count remains fixed at "
            "three; cumulative history growth is therefore not necessary in "
            "this tested setting."
        )
    else:
        context_statement = (
            "The bounded-transfer arm does not meet the frozen exact lock-in "
            "criterion, so cumulative context growth remains a plausible "
            "contributor."
        )
    statement = (
        "Two independent cumulative self-report trajectories beyond the "
        "frozen main run retrospectively reproduce multi-layer exact "
        "snapshot lock-in, while both no-transfer controls retain "
        "implementation diversity. "
        + context_statement
    )
    audit = {
        "status": "valid" if all_valid else "invalid",
        "date": "2026-07-15",
        "runs": runs,
        "decision": {
            "all_runs_valid": all_valid,
            "independent_lockin_replications_observed": independent,
            "no_transfer_controls_avoid_two_layer_exact_lockin": controls_clean,
            "bounded_reference_count_passed": bounded_reference_count,
            "bounded_context_lockin_criterion_passed": bounded_lockin,
            "bounded_config_hash_passed": bounded_config_hash_passed,
            "statement": statement,
        },
        "claim_boundary": {
            "independent_replications_are_retrospective_for_lockin": True,
            "bounded_control_is_prospective": True,
            "bounded_control_does_not_equalize_total_tokens": True,
            "second_task_uses_strict_verified_transfer": True,
            "layers_are_not_independent_samples": True,
        },
    }
    OUTPUT_JSON.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    write_csv(runs)
    write_markdown(audit)
    print(json.dumps(audit["decision"], indent=2))


if __name__ == "__main__":
    main()
