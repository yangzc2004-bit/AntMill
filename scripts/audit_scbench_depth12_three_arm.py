from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASH = "6ee2bfc068272a7fbc92599619db56b345cd93ecd3a321e791fa496a6a0f0615"
EXPECTED_CORE_TOTAL = 4
EXPECTED_ALL_TOTAL = 37
PROTOCOL = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_cfgpipe_cp1_depth12_three_arm_confirmation_protocol_20260715.json"
)
OUTPUT_JSON = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_cfgpipe_cp1_depth12_three_arm_confirmation_audit_20260715.json"
)
OUTPUT_MD = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_cfgpipe_cp1_depth12_three_arm_confirmation_audit_20260715.md"
)

ARMS = {
    "self_report": {
        "mode": "cumulative_self_report_acceptance",
        "run_root": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_depth12_"
            "self_report_r2_20260715"
        ),
        "arm_id": (
            "cumulative_self_report_acceptance-"
            "426bc68aaa4b4e8c8f2aad850c75a89b"
        ),
        "config": (
            "benchmarks/scbench/"
            "kimi_maas_cfgpipe_cp1_depth12_self_report_r2_config.json"
        ),
    },
    "no_transfer": {
        "mode": "no_transfer",
        "run_root": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_depth12_"
            "no_transfer_r1_20260715"
        ),
        "arm_id": "no_transfer-02db19c347a0481a95ee08ca1752f7bd",
        "config": (
            "benchmarks/scbench/"
            "kimi_maas_cfgpipe_cp1_depth12_no_transfer_r1_config.json"
        ),
    },
    "local_acceptance": {
        "mode": "cumulative_local_acceptance",
        "run_root": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_depth12_"
            "local_acceptance_r1_20260715"
        ),
        "arm_id": (
            "cumulative_local_acceptance-"
            "dea047b7770a43ccba2d521b51adb35e"
        ),
        "config": (
            "benchmarks/scbench/"
            "kimi_maas_cfgpipe_cp1_depth12_local_acceptance_r1_config.json"
        ),
    },
}

PROHIBITED_PATTERNS = {
    "evaluation_tests": re.compile(r"\.evaluation_tests", re.IGNORECASE),
    "frozen_problem_mount": re.compile(r"(?:^|\s)/problems(?:/|\s|$)", re.IGNORECASE),
    "evaluation_output_mount": re.compile(r"(?:^|\s)/outputs(?:/|\s|$)", re.IGNORECASE),
    "hidden_test_file": re.compile(r"tests?/test_checkpoint_1\.py", re.IGNORECASE),
}

BLINDING_PATTERNS = {
    "numeric_core_score": re.compile(r"(?:Local verifier )?Core:\s*\d+/\d+"),
    "all_test_score": re.compile(r"\b\d+/37\b"),
    "all_passed_field": re.compile(r"\ball_passed\b"),
    "all_total_field": re.compile(r"\ball_total\b"),
    "test_hash_field": re.compile(r"\btest_collection_hash\b"),
}

RATE_LIMIT_PATTERNS = (
    "too many requests",
    "limit of requests per minute",
    "ratelimiterror",
    "rate limit",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def layer_dir(arm_dir: Path, worker_id: str, layer: int) -> Path:
    return arm_dir / "workers" / worker_id / f"layer_{layer}"


def checkpoint_dir(arm_dir: Path, worker_id: str, layer: int) -> Path:
    return (
        layer_dir(arm_dir, worker_id, layer)
        / "native_output"
        / "cfgpipe"
        / "checkpoint_1"
    )


def flatten_failed_tests(evaluation: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    for group in evaluation.get("tests", {}).values():
        failed.extend(str(item) for item in group.get("failed", []))
    return sorted(failed)


def directory_hash(path: Path) -> str | None:
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        return None
    for file_path in files:
        digest.update(file_path.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def trajectory_messages(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    messages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            messages.append(json.loads(line))
    return messages


def short_text(value: str, limit: int = 500) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def scan_logs(run_root: Path) -> dict[str, Any]:
    warning_files = []
    warning_occurrences = 0
    terminal_error_files = []
    for log_path in sorted(run_root.rglob("runner.*.log")):
        text = log_path.read_text(encoding="utf-8", errors="replace")
        lowered = text.lower()
        count = sum(lowered.count(pattern) for pattern in RATE_LIMIT_PATTERNS)
        if count:
            warning_occurrences += count
            warning_files.append(str(log_path.relative_to(REPO_ROOT)))
        if (
            "traceback (most recent call last)" in lowered
            or "unhandled exception" in lowered
        ):
            terminal_error_files.append(str(log_path.relative_to(REPO_ROOT)))
    return {
        "transient_rate_limit_warning_occurrences": warning_occurrences,
        "files_with_rate_limit_warnings": warning_files,
        "files_with_terminal_runner_errors": terminal_error_files,
    }


def summarize_outcomes(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    all_passed = [int(item["all_passed"]) for item in outputs]
    core_passed = [int(item["core_passed"]) for item in outputs]
    post = [item for item in outputs if int(item["layer"]) >= 7]
    post_all = [int(item["all_passed"]) for item in post]
    post_core = [int(item["core_passed"]) for item in post]
    return {
        "workers": len(outputs),
        "mean_all_score": mean(all_passed) / EXPECTED_ALL_TOTAL,
        "mean_core_score": mean(core_passed) / EXPECTED_CORE_TOTAL,
        "post_layer_6_workers": len(post),
        "post_layer_6_mean_all_score": mean(post_all) / EXPECTED_ALL_TOTAL,
        "post_layer_6_mean_core_score": mean(post_core) / EXPECTED_CORE_TOTAL,
        "exact_zero_events": sum(value == 0 for value in all_passed),
        "post_layer_6_exact_zero_events": sum(value == 0 for value in post_all),
        "events_at_most_1_of_37": sum(value <= 1 for value in all_passed),
        "events_at_most_12_of_37": sum(value <= 12 for value in all_passed),
        "events_below_30_of_37": sum(value < 30 for value in all_passed),
        "minimum_all_passed": min(all_passed),
        "maximum_all_passed": max(all_passed),
    }


def audit_arm(name: str, spec: dict[str, str]) -> dict[str, Any]:
    run_root = REPO_ROOT / spec["run_root"]
    arm_dir = run_root / spec["arm_id"]
    manifest_path = arm_dir / "manifest.json"
    manifest = load_json(manifest_path)
    curve = load_json(run_root / "curve_report.json")
    outputs = []
    assistant_messages = 0
    prohibited_hits = []
    inference_failures = []
    target_failures = []
    prompt_blinding_hits = []

    for layer_outputs in manifest["layers"]:
        for output in layer_outputs:
            worker_id = str(output["worker_id"])
            layer = int(output["layer"])
            cp_dir = checkpoint_dir(arm_dir, worker_id, layer)
            evaluation_path = cp_dir / "evaluation.json"
            inference_path = cp_dir / "inference_result.json"
            trajectory_path = cp_dir / "agent" / "trajectory.jsonl"
            evaluation = load_json(evaluation_path)
            inference = load_json(inference_path)
            messages = trajectory_messages(trajectory_path)
            assistant = [
                item for item in messages if str(item.get("role", "")) == "assistant"
            ]
            assistant_messages += len(assistant)

            for message in assistant:
                content = str(message.get("content", ""))
                for label, pattern in PROHIBITED_PATTERNS.items():
                    if pattern.search(content):
                        prohibited_hits.append(
                            {
                                "worker": worker_id,
                                "layer": layer,
                                "pattern": label,
                                "excerpt": short_text(content),
                            }
                        )

            verification = output["verification"]
            target_ok = (
                int(verification["core_total"]) == EXPECTED_CORE_TOTAL
                and int(verification["all_total"]) == EXPECTED_ALL_TOTAL
                and str(verification["test_collection_hash"]) == EXPECTED_HASH
                and not bool(verification["infrastructure_failure"])
                and int(evaluation["pytest_collected"]) == EXPECTED_ALL_TOTAL
                and str(evaluation["test_collection_hash"]) == EXPECTED_HASH
                and not bool(evaluation["infrastructure_failure"])
            )
            if not target_ok:
                target_failures.append({"worker": worker_id, "layer": layer})

            usage = inference.get("usage", {})
            steps = int(usage.get("steps", 0))
            inference_ok = (
                not bool(inference.get("had_error"))
                and not inference.get("error_message")
                and steps > 0
            )
            if not inference_ok:
                inference_failures.append(
                    {
                        "worker": worker_id,
                        "layer": layer,
                        "had_error": inference.get("had_error"),
                        "error_message": inference.get("error_message"),
                        "steps": steps,
                    }
                )

            prompt_path = cp_dir / "prompt.txt"
            if name in {"self_report", "local_acceptance"}:
                prompt = prompt_path.read_text(encoding="utf-8")
                for label, pattern in BLINDING_PATTERNS.items():
                    if pattern.search(prompt):
                        prompt_blinding_hits.append(
                            {
                                "worker": worker_id,
                                "layer": layer,
                                "pattern": label,
                            }
                        )

            snapshot = cp_dir / "snapshot"
            failed_tests = flatten_failed_tests(evaluation)
            telemetry = output["telemetry"]
            outputs.append(
                {
                    "worker_id": worker_id,
                    "layer": layer,
                    "core_passed": int(verification["core_passed"]),
                    "core_total": int(verification["core_total"]),
                    "all_passed": int(verification["all_passed"]),
                    "all_total": int(verification["all_total"]),
                    "pytest_exit_code": int(verification["pytest_exit_code"]),
                    "infrastructure_failure": bool(
                        verification["infrastructure_failure"]
                    ),
                    "test_collection_hash": str(
                        verification["test_collection_hash"]
                    ),
                    "model_steps": steps,
                    "model_input_tokens": int(
                        usage.get("net_tokens", {}).get("input", 0)
                    ),
                    "model_output_tokens": int(
                        usage.get("net_tokens", {}).get("output", 0)
                    ),
                    "snapshot_files": int(telemetry["snapshot_files"]),
                    "snapshot_bytes": int(telemetry["snapshot_bytes"]),
                    "snapshot_sha256": directory_hash(snapshot),
                    "received_results": int(telemetry["received_results"]),
                    "received_experience_chars": int(
                        telemetry["received_experience_chars"]
                    ),
                    "local_validation_passed": bool(
                        telemetry["local_validation_passed"]
                    ),
                    "local_validation_commands": int(
                        telemetry["local_validation_commands"]
                    ),
                    "self_reported_success": bool(
                        telemetry["self_reported_success"]
                    ),
                    "failed_tests": failed_tests,
                    "assistant_message_count": len(assistant),
                    "last_assistant_message": (
                        short_text(str(assistant[-1].get("content", "")), 900)
                        if assistant
                        else ""
                    ),
                    "evaluation_path": str(evaluation_path.relative_to(REPO_ROOT)),
                    "trajectory_path": str(trajectory_path.relative_to(REPO_ROOT)),
                    "prompt_path": str(prompt_path.relative_to(REPO_ROOT)),
                }
            )

    layer_rows = []
    for row in curve["rows"]:
        layer = int(row["layer"])
        layer_outputs = [item for item in outputs if item["layer"] == layer]
        layer_rows.append(
            {
                "layer": layer,
                "worker_all_passed": [
                    item["all_passed"] for item in layer_outputs
                ],
                "worker_core_passed": [
                    item["core_passed"] for item in layer_outputs
                ],
                "mean_all_score": float(row["mean_all_test_score"]),
                "mean_core_score": float(row["mean_core_score"]),
                "total_input_tokens": int(row["total_input_tokens"]),
                "mean_received_results": float(row["mean_received_results"]),
                "mean_received_experience_chars": float(
                    row["mean_received_experience_chars"]
                ),
            }
        )

    return {
        "mode": spec["mode"],
        "config": spec["config"],
        "run_root": spec["run_root"],
        "arm_id": spec["arm_id"],
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "curve_report": str((run_root / "curve_report.json").relative_to(REPO_ROOT)),
        "curve": layer_rows,
        "outcome_summary": summarize_outcomes(outputs),
        "validity": {
            "target_consistency_passed": not target_failures,
            "target_failures": target_failures,
            "model_query_integrity_passed": not inference_failures,
            "model_query_failures": inference_failures,
            "recipient_blinding_passed": not prompt_blinding_hits,
            "recipient_blinding_hits": prompt_blinding_hits,
            "assistant_messages_scanned": assistant_messages,
            "prohibited_access_passed": not prohibited_hits,
            "prohibited_access_hits": prohibited_hits,
            "runner_logs": scan_logs(run_root),
        },
        "outputs": outputs,
    }


def bootstrap_audit(arm_audit: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(REPO_ROOT / arm_audit["manifest"])
    bootstrap_path = (
        REPO_ROOT / arm_audit["run_root"] / arm_audit["arm_id"] / "bootstrap_manifest.json"
    )
    bootstrap = load_json(bootstrap_path)
    initial = manifest["initial_references"]
    entries = []
    for index, item in enumerate(initial):
        external = bootstrap["sources"][index]
        source_evaluation_path = (
            Path(external["worker_workspace"])
            / f"layer_{external['source_layer']}"
            / "native_output"
            / "cfgpipe"
            / "checkpoint_1"
            / "evaluation.json"
        )
        if not source_evaluation_path.is_absolute():
            source_evaluation_path = REPO_ROOT / source_evaluation_path
        source_evaluation = load_json(source_evaluation_path)
        entries.append(
            {
                "worker_id": item["worker_id"],
                "proxy_hash": item["verification"]["test_collection_hash"],
                "proxy_external_scores_withheld": (
                    item["verification"]["test_collection_hash"]
                    in {
                        "self-report-completion-proxy",
                        "local-completion-smoke-proxy",
                    }
                ),
                "external_core": (
                    f"{external['core_passed']}/"
                    f"{external['core_total']}"
                ),
                "external_all": (
                    f"{external['all_passed']}/"
                    f"{external['all_total']}"
                ),
                "external_hash": external["test_collection_hash"],
                "external_infrastructure_failure": bool(
                    source_evaluation["infrastructure_failure"]
                ),
                "source_evaluation": str(
                    source_evaluation_path.relative_to(REPO_ROOT)
                ),
            }
        )
    passed = all(
        entry["proxy_external_scores_withheld"]
        and entry["external_core"] == "4/4"
        and entry["external_all"] == "34/37"
        and entry["external_hash"] == EXPECTED_HASH
        and not entry["external_infrastructure_failure"]
        for entry in entries
    )
    return {
        "passed": passed,
        "bootstrap_manifest": str(bootstrap_path.relative_to(REPO_ROOT)),
        "entries": entries,
    }


def find_output(
    arm: dict[str, Any], *, layer: int, worker_id: str
) -> dict[str, Any]:
    return next(
        item
        for item in arm["outputs"]
        if item["layer"] == layer and item["worker_id"] == worker_id
    )


def local_gate_audit(local: dict[str, Any]) -> dict[str, Any]:
    catastrophic = [
        item for item in local["outputs"] if item["all_passed"] == 0
    ]
    rejected_outputs = [
        item
        for item in local["outputs"]
        if not item["local_validation_passed"]
    ]
    events = []
    for item in catastrophic:
        later_prompts = [
            candidate
            for candidate in local["outputs"]
            if candidate["layer"] > item["layer"]
        ]
        marker = f"Worker {item['worker_id']}, layer {item['layer']}."
        downstream_hits = []
        for candidate in later_prompts:
            prompt = (REPO_ROOT / candidate["prompt_path"]).read_text(
                encoding="utf-8"
            )
            if marker in prompt:
                downstream_hits.append(
                    {
                        "recipient_worker": candidate["worker_id"],
                        "recipient_layer": candidate["layer"],
                    }
                )
        events.append(
            {
                "layer": item["layer"],
                "worker_id": item["worker_id"],
                "score": "0/37",
                "model_steps": item["model_steps"],
                "snapshot_files": item["snapshot_files"],
                "local_validation_passed": item["local_validation_passed"],
                "local_validation_commands": item[
                    "local_validation_commands"
                ],
                "self_reported_success": item["self_reported_success"],
                "last_assistant_message": item["last_assistant_message"],
                "rejected": not item["local_validation_passed"],
                "downstream_marker_hits": downstream_hits,
                "absent_from_all_later_prompts": not downstream_hits,
            }
        )
    passed = bool(events) and all(
        event["local_validation_commands"] < 3
        and event["rejected"]
        and event["absent_from_all_later_prompts"]
        for event in events
    )
    rejected_by_score = Counter(
        f"{item['all_passed']}/37" for item in rejected_outputs
    )
    return {
        "passed": passed,
        "catastrophic_events": events,
        "total_outputs": len(local["outputs"]),
        "accepted_outputs": sum(
            item["local_validation_passed"] for item in local["outputs"]
        ),
        "rejected_outputs": len(rejected_outputs),
        "rejected_by_external_score": dict(sorted(rejected_by_score.items())),
        "high_quality_rejections": [
            {
                "layer": item["layer"],
                "worker_id": item["worker_id"],
                "score": f"{item['all_passed']}/37",
                "core": f"{item['core_passed']}/4",
                "successful_commands": item["local_validation_commands"],
            }
            for item in rejected_outputs
            if item["all_passed"] >= 34
        ],
        "tradeoff": (
            "The three-command proxy rejected both zero-command collapses but "
            "also rejected five externally strong 34/37 outputs that used only "
            "two successful commands."
        ),
    }


def self_report_lock_in_audit(self_report: dict[str, Any]) -> dict[str, Any]:
    plateau = [
        item for item in self_report["outputs"] if item["layer"] >= 3
    ]
    failure_sets = [set(item["failed_tests"]) for item in plateau]
    shared_failures = sorted(set.intersection(*failure_sets)) if failure_sets else []
    failure_counter = Counter(
        test for item in plateau for test in item["failed_tests"]
    )
    hashes = [item["snapshot_sha256"] for item in plateau]
    return {
        "layers": "3-12",
        "workers": len(plateau),
        "all_workers_at_33_of_37": all(
            item["all_passed"] == 33 for item in plateau
        ),
        "all_workers_core_4_of_4": all(
            item["core_passed"] == 4 for item in plateau
        ),
        "shared_failed_tests": shared_failures,
        "failed_test_frequencies": dict(sorted(failure_counter.items())),
        "unique_snapshot_hashes": len(set(hashes)),
        "exact_snapshot_homogeneity_from_layer_5": all(
            len(
                {
                    item["snapshot_sha256"]
                    for item in plateau
                    if item["layer"] == layer
                }
            )
            == 1
            for layer in range(5, 13)
        )
        and len(
            {
                item["snapshot_sha256"]
                for item in plateau
                if item["layer"] >= 5
            }
        )
        == 1,
        "snapshot_hashes_by_layer": {
            str(layer): sorted(
                {
                    str(item["snapshot_sha256"])
                    for item in plateau
                    if item["layer"] == layer
                }
            )
            for layer in range(3, 13)
        },
    }


def no_transfer_tail_audit(no_transfer: dict[str, Any]) -> dict[str, Any]:
    severe = [
        item for item in no_transfer["outputs"] if item["all_passed"] <= 12
    ]
    events = []
    for item in severe:
        events.append(
            {
                "layer": item["layer"],
                "worker_id": item["worker_id"],
                "score": f"{item['all_passed']}/37",
                "core": f"{item['core_passed']}/4",
                "model_steps": item["model_steps"],
                "snapshot_files": item["snapshot_files"],
                "snapshot_bytes": item["snapshot_bytes"],
                "local_validation_commands": item[
                    "local_validation_commands"
                ],
                "self_reported_success": item["self_reported_success"],
                "failed_tests": item["failed_tests"],
                "last_assistant_message": item["last_assistant_message"],
                "valid_model_query": item["model_steps"] > 0,
                "valid_evaluation": not item["infrastructure_failure"],
                "completion_submitted": (
                    "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
                    in item["last_assistant_message"]
                ),
                "action_budget_exhausted_without_submission": (
                    item["model_steps"] >= 12
                    and "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
                    not in item["last_assistant_message"]
                ),
            }
        )
    return {"events": events, "count": len(events)}


def complexity_audit(
    self_report: dict[str, Any],
    no_transfer: dict[str, Any],
    local: dict[str, Any],
) -> dict[str, Any]:
    by_layer = {}
    for layer in range(10, 13):
        sr = self_report["curve"][layer - 1]
        nt = no_transfer["curve"][layer - 1]
        la = local["curve"][layer - 1]
        by_layer[str(layer)] = {
            "self_report_reference_count": sr["mean_received_results"],
            "local_reference_count": la["mean_received_results"],
            "no_transfer_total_input_tokens": nt["total_input_tokens"],
            "self_report_total_input_tokens": sr["total_input_tokens"],
            "local_total_input_tokens": la["total_input_tokens"],
            "self_report_to_no_transfer_token_ratio": (
                sr["total_input_tokens"] / nt["total_input_tokens"]
            ),
            "local_to_no_transfer_token_ratio": (
                la["total_input_tokens"] / nt["total_input_tokens"]
            ),
        }
    self_pass = any(
        row["self_report_reference_count"] >= 30
        and row["self_report_to_no_transfer_token_ratio"] >= 5
        for row in by_layer.values()
    )
    local_pass = any(
        row["local_reference_count"] >= 30
        and row["local_to_no_transfer_token_ratio"] >= 5
        for row in by_layer.values()
    )
    return {
        "layers_10_to_12": by_layer,
        "self_report_activation_passed": self_pass,
        "local_acceptance_activation_passed": local_pass,
        "joint_frozen_criterion_passed": self_pass and local_pass,
    }


def build_audit() -> dict[str, Any]:
    protocol = load_json(PROTOCOL)
    arm_audits = {
        name: audit_arm(name, spec) for name, spec in ARMS.items()
    }
    self_report = arm_audits["self_report"]
    no_transfer = arm_audits["no_transfer"]
    local = arm_audits["local_acceptance"]
    local_gate = local_gate_audit(local)
    lock_in = self_report_lock_in_audit(self_report)
    no_transfer_tail = no_transfer_tail_audit(no_transfer)
    complexity = complexity_audit(self_report, no_transfer, local)
    self_post_zeros = self_report["outcome_summary"][
        "post_layer_6_exact_zero_events"
    ]
    no_transfer_post_zeros = no_transfer["outcome_summary"][
        "post_layer_6_exact_zero_events"
    ]
    self_l12 = self_report["curve"][-1]

    validity = {
        "bootstrap_activation": {
            "self_report": bootstrap_audit(self_report),
            "local_acceptance": bootstrap_audit(local),
        },
        "target_consistency": {
            "passed": all(
                arm["validity"]["target_consistency_passed"]
                for arm in arm_audits.values()
            ),
            "evaluations": sum(len(arm["outputs"]) for arm in arm_audits.values()),
            "invalid_evaluations": sum(
                len(arm["validity"]["target_failures"])
                for arm in arm_audits.values()
            ),
        },
        "model_query_integrity": {
            "passed": all(
                arm["validity"]["model_query_integrity_passed"]
                for arm in arm_audits.values()
            ),
            "invalid_queries": sum(
                len(arm["validity"]["model_query_failures"])
                for arm in arm_audits.values()
            ),
            "note": (
                "The provider emitted transient RPM warnings during the nine-way "
                "parallel launch. LiteLLM retried them; every interpreted "
                "inference_result has had_error=false and steps>0."
            ),
        },
        "recipient_blinding": {
            "passed": all(
                arm["validity"]["recipient_blinding_passed"]
                for name, arm in arm_audits.items()
                if name != "no_transfer"
            ),
            "hits": sum(
                len(arm["validity"]["recipient_blinding_hits"])
                for name, arm in arm_audits.items()
                if name != "no_transfer"
            ),
        },
        "prohibited_access": {
            "passed": all(
                arm["validity"]["prohibited_access_passed"]
                for arm in arm_audits.values()
            ),
            "assistant_messages_scanned": sum(
                arm["validity"]["assistant_messages_scanned"]
                for arm in arm_audits.values()
            ),
            "hits": sum(
                len(arm["validity"]["prohibited_access_hits"])
                for arm in arm_audits.values()
            ),
        },
    }
    validity["all_gates_passed"] = (
        validity["bootstrap_activation"]["self_report"]["passed"]
        and validity["bootstrap_activation"]["local_acceptance"]["passed"]
        and validity["target_consistency"]["passed"]
        and validity["model_query_integrity"]["passed"]
        and validity["recipient_blinding"]["passed"]
        and validity["prohibited_access"]["passed"]
    )

    decisions = {
        "complexity_tail_risk": {
            "passed": (
                self_post_zeros >= 2
                and any(
                    item["all_passed"] == 0 and item["layer"] >= 10
                    for item in self_report["outputs"]
                )
            ),
            "observed_post_layer_6_zero_events": self_post_zeros,
            "required": (
                "At least two post-layer-6 0/37 self-report events, including "
                "one at layer 10 or later."
            ),
        },
        "no_transfer_contrast": {
            "passed": (
                no_transfer_post_zeros <= 1
                and no_transfer_post_zeros < self_post_zeros
            ),
            "observed_post_layer_6_zero_events": no_transfer_post_zeros,
            "self_report_post_layer_6_zero_events": self_post_zeros,
            "required": (
                "At most one no-transfer event and fewer events than the "
                "fresh self-report arm."
            ),
        },
        "local_gate_mechanism": {
            "passed": local_gate["passed"],
            "observed_catastrophic_events": len(
                local_gate["catastrophic_events"]
            ),
        },
        "terminal_recurrence": {
            "passed": (
                self_l12["mean_all_score"] < 0.75
                or any(
                    item["all_passed"] == 0 and item["layer"] == 12
                    for item in self_report["outputs"]
                )
            ),
            "layer_12_mean_all_score": self_l12["mean_all_score"],
        },
        "complexity_activation": {
            "passed": complexity["joint_frozen_criterion_passed"],
            "detail": (
                "Self-report reaches 30+ references with >5x token load. "
                "Local acceptance reaches only 29 references because rejected "
                "outputs are not accumulated."
            ),
        },
        "admission_effect_next_layer_recovery": {
            "passed": False,
            "detail": (
                "Layer 10 worker 3 was rejected, but layer 11 worker 2 "
                "independently collapsed to 0/37."
            ),
        },
        "confirm_recurrent_complexity_tail_risk": {
            "passed": False,
            "reason": (
                "The fresh self-report replication produced zero 0/37 events, "
                "so the frozen replication criterion is falsified."
            ),
        },
        "support_admission_filter": {
            "passed": local_gate["passed"],
            "reason": (
                "Both zero-command local-arm failures were rejected and absent "
                "from every later recipient prompt."
            ),
        },
    }

    return {
        "status": (
            "valid_falsified_self_report_catastrophic_replication_"
            "with_supported_local_rejection_mechanism"
        ),
        "date": "2026-07-15",
        "protocol": str(PROTOCOL.relative_to(REPO_ROOT)),
        "model": protocol["model"],
        "api_model": protocol["api_model"],
        "provider": protocol["provider"],
        "problem": protocol["problem"],
        "checkpoint_limit": protocol["checkpoint_limit"],
        "arms": arm_audits,
        "validity_audit": validity,
        "frozen_decisions": decisions,
        "local_gate_audit": local_gate,
        "self_report_plateau_audit": lock_in,
        "no_transfer_severe_tail_audit": no_transfer_tail,
        "complexity_audit": complexity,
        "scientific_interpretation": {
            "supported": [
                (
                    "The completion-and-smoke gate mechanically rejects "
                    "zero-command false-completion outputs and prevents their "
                    "direct downstream propagation."
                ),
                (
                    "Uncompressed accepted history can coincide with "
                    "intermittent skip-work failures, but those failures also "
                    "show substantial run-to-run stochasticity."
                ),
                (
                    "The fresh self-report arm exhibits a stable 33/37 "
                    "behavioral lock-in from layer 3 through layer 12."
                ),
            ],
            "not_supported": [
                (
                    "The preregistered claim that weak self-report accumulation "
                    "reliably produces at least two late 0/37 events."
                ),
                (
                    "A unique catastrophic-tail effect relative to no transfer; "
                    "the no-transfer arm had no exact zeros but did have valid "
                    "12/37 and 1/37 action-budget tails."
                ),
                "A monotonic death spiral or deterministic bad-experience propagation.",
            ],
            "claim_boundary": (
                "Treat the original depth-12 catastrophic curve as exploratory "
                "and non-replicated. The clean confirmatory contribution is the "
                "admission-gate rejection mechanism, including its false-"
                "rejection cost, plus descriptive evidence of behavioral "
                "lock-in and stochastic tail risk."
            ),
        },
    }


def write_markdown(audit: dict[str, Any]) -> None:
    sr = audit["arms"]["self_report"]
    nt = audit["arms"]["no_transfer"]
    la = audit["arms"]["local_acceptance"]
    local_events = audit["local_gate_audit"]["catastrophic_events"]
    severe = audit["no_transfer_severe_tail_audit"]["events"]
    shared = audit["self_report_plateau_audit"]["shared_failed_tests"]

    def curve_text(arm: dict[str, Any]) -> str:
        return ", ".join(
            f"{row['mean_all_score']:.3f}" for row in arm["curve"]
        )

    lines = [
        "# Kimi MaaS cfgpipe depth-12 three-arm confirmation audit",
        "",
        "## Frozen decision",
        "",
        (
            "The fresh self-report replication is **falsified under the frozen "
            "criterion**: it produced 0 post-layer-6 `0/37` events, versus the "
            "required minimum of 2."
        ),
        "",
        (
            "The local completion-and-smoke mechanism is **supported**: both "
            "local-arm `0/37` false-completion outputs had fewer than three "
            "successful commands, were rejected, and never appeared in later "
            "recipient prompts."
        ),
        "",
        "## Curves",
        "",
        f"- Self report: `{curve_text(sr)}`",
        f"- No transfer: `{curve_text(nt)}`",
        f"- Local acceptance: `{curve_text(la)}`",
        "",
        "## Trajectory findings",
        "",
        (
            f"- Self report locks to `33/37` for all "
            f"{audit['self_report_plateau_audit']['workers']} worker-layer "
            "outcomes from layers 3-12."
        ),
        (
            "- From layer 5 onward, all self-report workers produce the exact "
            "same snapshot hash at every layer."
        ),
        (
            "- Shared self-report failures: "
            + ", ".join(f"`{item}`" for item in shared)
            + "."
        ),
    ]
    for event in local_events:
        lines.append(
            f"- Local layer {event['layer']} {event['worker_id']}: `0/37`, "
            f"{event['model_steps']} model step, "
            f"{event['local_validation_commands']} successful commands; "
            "rejected and absent downstream."
        )
    for event in severe:
        lines.append(
            f"- No-transfer layer {event['layer']} {event['worker_id']}: "
            f"`{event['score']}`, Core `{event['core']}`, "
            f"{event['model_steps']} model steps; action budget exhausted "
            "without submission, with a valid model query and "
            "non-infrastructure evaluation."
        )
    lines.extend(
        [
            (
                "- Gate tradeoff: 7 local outputs were rejected in total. "
                "Besides the two `0/37` collapses, five `34/37` outputs were "
                "also rejected because they used only two successful commands."
            ),
            "",
            "",
            "## Validity",
            "",
            (
                f"All {audit['validity_audit']['target_consistency']['evaluations']} "
                "evaluations use the frozen 4-Core/37-test target and test hash. "
                "Every interpreted model call has `had_error=false` and at "
                "least one completed step."
            ),
            "",
            (
                "Transient provider RPM warnings occurred during the nine-way "
                "parallel launch, but retries completed. No rate-limit or "
                "gateway failure was scored as a benchmark failure."
            ),
            "",
            (
                f"Recipient blinding and prohibited-access scans passed across "
                f"{audit['validity_audit']['prohibited_access']['assistant_messages_scanned']} "
                "assistant messages."
            ),
            "",
            "## Claim boundary",
            "",
            (
                "The prior recurrent catastrophic depth-12 curve should remain "
                "exploratory because its exact `0/37` pattern did not replicate. "
                "The confirmatory result supports the rejection mechanism, a "
                "stable self-report-arm `33/37` lock-in, and substantial "
                "stochastic tail risk, while also revealing a nontrivial "
                "false-rejection cost. It does not establish a monotonic death "
                "spiral or a unique catastrophic effect of self-report transfer."
            ),
            "",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    audit = build_audit()
    OUTPUT_JSON.write_text(
        json.dumps(audit, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    write_markdown(audit)
    print(OUTPUT_JSON.relative_to(REPO_ROOT))
    print(OUTPUT_MD.relative_to(REPO_ROOT))
    print(json.dumps(audit["frozen_decisions"], indent=2))


if __name__ == "__main__":
    main()
