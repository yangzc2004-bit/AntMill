from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPO_ROOT / "benchmarks" / "scbench"
OUTPUT_ROOT = REPO_ROOT / "paper_draft" / "generated" / "moa_paper"

MAIN_AUDIT = (
    AUDIT_ROOT
    / "kimi_maas_cfgpipe_cp1_depth12_three_arm_confirmation_audit_20260715.json"
)

RAW_APPEND_AUDITS = (
    (
        "DeepSeek-V4-Flash",
        "deepseek-r1",
        AUDIT_ROOT
        / "deepseek_cfgpipe_cp1_self_report_acceptance_depth10_audit_20260714.json",
    ),
    (
        "GLM-5",
        "glm5-r1",
        AUDIT_ROOT
        / "glm5_cfgpipe_cp1_self_report_acceptance_depth10_audit_20260714.json",
    ),
    (
        "Kimi-K2.6",
        "kimi-coding-r1",
        AUDIT_ROOT
        / "kimi_cfgpipe_cp1_self_report_acceptance_depth8_audit_20260714.json",
    ),
    (
        "Kimi-K2.6",
        "kimi-coding-r2",
        AUDIT_ROOT
        / "kimi_cfgpipe_cp1_self_report_acceptance_depth10_r2_audit_20260714.json",
    ),
    (
        "Kimi-K2.6",
        "kimi-maas-r2",
        MAIN_AUDIT,
    ),
)

RECURSIVE_AUDITS = {
    "kimi_cfgpipe": (
        AUDIT_ROOT / "kimi_cfgpipe_cp1_recursive_synthesis_depth5_audit_20260714.json"
    ),
    "deepseek_cfgpipe": (
        AUDIT_ROOT
        / "deepseek_cfgpipe_cp1_recursive_self_report_probe_depth5_audit_20260714.json"
    ),
    "kimi_log_query": (
        AUDIT_ROOT
        / "kimi_log_query_cp1_bootstrapped_recursive_depth5_audit_20260714.json"
    ),
    "kimi_xjq": (
        AUDIT_ROOT
        / "kimi_xjq_cp2_recursive_self_report_manager_depth5_r1_final_audit_20260714.json"
    ),
    "kimi_cfgpipe_sequential": (
        AUDIT_ROOT
        / "kimi_cfgpipe_sequential_cp1_cp2_early_falsification_audit_20260714.json"
    ),
    "kimi_execution_server_sequential": (
        AUDIT_ROOT
        / "kimi_maas_execution_server_sequential_cp1_cp3_recursive_self_report_pilot_audit_20260714.json"
    ),
}

ARM_LABELS = {
    "self_report": "Cumulative self-report",
    "no_transfer": "No transfer",
    "local_acceptance": "Local admission",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError(f"Cannot write empty source-data table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def pairwise_jaccard(signatures: list[set[str]]) -> float:
    values = []
    for left, right in combinations(signatures, 2):
        union = left | right
        values.append(1.0 if not union else len(left & right) / len(union))
    return mean(values) if values else 1.0


def main_curve_rows(main: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    no_transfer_tokens = {
        int(row["layer"]): int(row["total_input_tokens"])
        for row in main["arms"]["no_transfer"]["curve"]
    }
    for arm_key in ("no_transfer", "self_report", "local_acceptance"):
        for row in main["arms"][arm_key]["curve"]:
            layer = int(row["layer"])
            tokens = int(row["total_input_tokens"])
            rows.append(
                {
                    "arm": arm_key,
                    "arm_label": ARM_LABELS[arm_key],
                    "layer": layer,
                    "mean_all_score": float(row["mean_all_score"]),
                    "mean_core_score": float(row["mean_core_score"]),
                    "min_all_score": min(row["worker_all_passed"]) / 37,
                    "max_all_score": max(row["worker_all_passed"]) / 37,
                    "zero_score_workers": sum(
                        int(value) == 0 for value in row["worker_all_passed"]
                    ),
                    "total_input_tokens": tokens,
                    "token_ratio_to_no_transfer": (
                        tokens / no_transfer_tokens[layer]
                        if no_transfer_tokens[layer]
                        else None
                    ),
                    "mean_received_results": float(row["mean_received_results"]),
                    "mean_received_experience_chars": float(
                        row["mean_received_experience_chars"]
                    ),
                }
            )
    return rows


def main_diversity_rows(main: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for arm_key in ("no_transfer", "self_report", "local_acceptance"):
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for output in main["arms"][arm_key]["outputs"]:
            grouped[int(output["layer"])].append(output)
        for layer, outputs in sorted(grouped.items()):
            snapshot_hashes = [
                str(item["snapshot_sha256"])
                for item in outputs
                if item.get("snapshot_sha256")
            ]
            snapshot_counts = Counter(snapshot_hashes)
            signatures = [
                frozenset(str(name) for name in item["failed_tests"])
                for item in outputs
            ]
            signature_counts = Counter(signatures)
            rows.append(
                {
                    "arm": arm_key,
                    "arm_label": ARM_LABELS[arm_key],
                    "layer": layer,
                    "workers": len(outputs),
                    "valid_snapshots": len(snapshot_hashes),
                    "unique_valid_snapshots": len(snapshot_counts),
                    "distinct_snapshot_fraction": (
                        len(snapshot_counts) / len(snapshot_hashes)
                        if snapshot_hashes
                        else 0.0
                    ),
                    "dominant_snapshot_share": (
                        max(snapshot_counts.values()) / len(snapshot_hashes)
                        if snapshot_hashes
                        else 0.0
                    ),
                    "unique_failure_signatures": len(signature_counts),
                    "dominant_failure_signature_share": (
                        max(signature_counts.values()) / len(outputs)
                    ),
                    "mean_pairwise_failure_jaccard": pairwise_jaccard(
                        [set(signature) for signature in signatures]
                    ),
                    "mean_all_score": mean(
                        int(item["all_passed"]) / int(item["all_total"])
                        for item in outputs
                    ),
                }
            )
    return rows


def gate_threshold_rows(main: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = main["arms"]["local_acceptance"]["outputs"]
    rows = []
    for threshold in range(0, 7):
        accepted = [
            item
            for item in outputs
            if item["self_reported_success"]
            and int(item["local_validation_commands"]) >= threshold
        ]
        rejected = [item for item in outputs if item not in accepted]
        catastrophic = [item for item in outputs if int(item["all_passed"]) == 0]
        high_quality = [item for item in outputs if int(item["all_passed"]) >= 33]
        rows.append(
            {
                "minimum_successful_commands": threshold,
                "accepted_outputs": len(accepted),
                "rejected_outputs": len(rejected),
                "catastrophic_total": len(catastrophic),
                "catastrophic_rejected": sum(
                    item in rejected for item in catastrophic
                ),
                "catastrophic_recall": (
                    sum(item in rejected for item in catastrophic)
                    / len(catastrophic)
                    if catastrophic
                    else None
                ),
                "high_quality_total": len(high_quality),
                "high_quality_accepted": sum(
                    item in accepted for item in high_quality
                ),
                "high_quality_retention": (
                    sum(item in accepted for item in high_quality)
                    / len(high_quality)
                    if high_quality
                    else None
                ),
                "mean_external_score_of_accepted": (
                    mean(
                        int(item["all_passed"]) / int(item["all_total"])
                        for item in accepted
                    )
                    if accepted
                    else None
                ),
            }
        )
    return rows


def raw_append_row(
    model: str, replicate: str, path: Path, audit: dict[str, Any]
) -> dict[str, Any]:
    if path == MAIN_AUDIT:
        arm = audit["arms"]["self_report"]
        curve = arm["curve"]
        zero_events = int(arm["outcome_summary"]["exact_zero_events"])
        worker_outcomes = int(arm["outcome_summary"]["workers"])
        depth = len(curve)
        terminal = float(curve[-1]["mean_all_score"])
        token_ratio = float(
            audit["complexity_audit"]["layers_10_to_12"]["12"][
                "self_report_to_no_transfer_token_ratio"
            ]
        )
        verdict = "fresh catastrophic-tail replication falsified"
    elif model == "DeepSeek-V4-Flash":
        curve = audit["curve"]
        zero_events = int(
            audit["aggregate"]["catastrophic_zero_of_37_outcomes"]
        )
        worker_outcomes = int(audit["aggregate"]["worker_outcomes"])
        depth = len(curve)
        terminal = float(curve[-1]["mean_all_tests"])
        token_ratio = float(audit["aggregate"]["layer_10_vs_control_input_ratio"])
        verdict = "intermittent tails; no sustained degradation"
    elif model == "GLM-5":
        run = audit["run"]
        curve = run["mean_all_test_curve"]
        zero_events = 0
        worker_outcomes = len(curve) * 3
        depth = len(curve)
        terminal = float(curve[-1])
        token_ratio = float(run["layer_10_input_ratio_to_matching_control"])
        verdict = "flat negative result"
    elif replicate == "kimi-coding-r2":
        run = audit["run"]
        curve = run["mean_all_test_curve"]
        zero_events = 0
        worker_outcomes = int(audit["integrity"]["worker_outcomes"])
        depth = len(curve)
        terminal = float(curve[-1])
        token_ratio = float(run["layer_10_input_ratio_to_matching_control"])
        verdict = "flat preregistered replication"
    elif replicate == "kimi-coding-r1":
        run = audit["depth8_run"]
        curve = run["mean_all_test_curve"]
        zero_events = 1
        depth = len(curve)
        worker_outcomes = depth * 3
        terminal = float(curve[-1])
        token_ratio = float(
            run["layer_8_input_token_ratio_to_matching_control"]
        )
        verdict = "single terminal tail; later extension invalid"
    else:
        curve = audit["curve"]
        zero_events = len(audit.get("catastrophic_events", []))
        depth = len(curve)
        worker_outcomes = depth * 3
        terminal = float(curve[-1]["mean_all_tests"])
        aggregate = audit.get("aggregate", {})
        token_ratio = aggregate.get("terminal_input_ratio_to_control")
        if token_ratio is None:
            token_ratio = aggregate.get("layer_8_vs_control_input_ratio")
        verdict = "single late tail; later extension invalid"
    return {
        "model": model,
        "replicate": replicate,
        "depth": depth,
        "worker_outcomes": worker_outcomes,
        "zero_score_events": zero_events,
        "zero_score_rate": zero_events / worker_outcomes,
        "terminal_mean_all_score": terminal,
        "terminal_input_ratio_to_control": token_ratio,
        "interpretation": verdict,
        "audit_file": path.relative_to(REPO_ROOT).as_posix(),
    }


def raw_append_rows() -> list[dict[str, Any]]:
    rows = []
    for model, replicate, path in RAW_APPEND_AUDITS:
        rows.append(raw_append_row(model, replicate, path, load_json(path)))
    return rows


def recursive_boundary_rows(audits: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    kimi_cfg = audits["kimi_cfgpipe"]
    deepseek_cfg = audits["deepseek_cfgpipe"]
    log_query = audits["kimi_log_query"]
    xjq = audits["kimi_xjq"]
    cfg_seq = audits["kimi_cfgpipe_sequential"]
    exec_seq = audits["kimi_execution_server_sequential"]
    return [
        {
            "setting": "cfgpipe checkpoint 1",
            "model": "Kimi-K2.6",
            "manager_admission": "external Core gate",
            "terminal_treatment": kimi_cfg["curve"]["recursive_synthesis"][
                "mean_all_tests"
            ][-1],
            "terminal_control": kimi_cfg["curve"]["no_transfer"]["mean_all_tests"][
                -1
            ],
            "treatment_minus_control": (
                kimi_cfg["curve"]["recursive_synthesis"]["mean_all_tests"][-1]
                - kimi_cfg["curve"]["no_transfer"]["mean_all_tests"][-1]
            ),
            "lock_in": "exact snapshot and failure-signature convergence",
            "confirmatory_status": "primary degradation criterion falsified",
        },
        {
            "setting": "cfgpipe checkpoint 1",
            "model": "DeepSeek-V4-Flash",
            "manager_admission": "self-report",
            "terminal_treatment": deepseek_cfg["curve"]["mean_all_tests"][-1],
            "terminal_control": None,
            "treatment_minus_control": None,
            "lock_in": "behavioral convergence across distinct snapshots",
            "confirmatory_status": "stress probe; mixed-quality bootstrap",
        },
        {
            "setting": "log_query checkpoint 1",
            "model": "Kimi-K2.6",
            "manager_admission": "external Core gate",
            "terminal_treatment": log_query["curves"]["treatment_mean_all_test"][-1],
            "terminal_control": log_query["curves"]["control_mean_all_test"][-1],
            "treatment_minus_control": log_query["terminal_effects"][
                "all_test_treatment_minus_control"
            ],
            "lock_in": "behavioral convergence, snapshots remain distinct",
            "confirmatory_status": "valid opposite-direction boundary",
        },
        {
            "setting": "xjq checkpoint 2",
            "model": "Kimi-K2.6",
            "manager_admission": "self-report",
            "terminal_treatment": xjq["curves"][
                "recursive_self_report_mean_all_tests"
            ][-1],
            "terminal_control": xjq["curves"]["no_transfer_mean_all_tests"][-1],
            "treatment_minus_control": (
                xjq["curves"]["recursive_self_report_mean_all_tests"][-1]
                - xjq["curves"]["no_transfer_mean_all_tests"][-1]
            ),
            "lock_in": "transient drop followed by full recovery",
            "confirmatory_status": "valid opposite-direction boundary",
        },
        {
            "setting": "cfgpipe sequential checkpoint 2",
            "model": "Kimi-K2.6",
            "manager_admission": "self-report",
            "terminal_treatment": cfg_seq["scores"]["checkpoint_2"][
                "treatment_mean"
            ],
            "terminal_control": cfg_seq["scores"]["checkpoint_2"][
                "no_transfer_mean"
            ],
            "treatment_minus_control": cfg_seq["scores"]["checkpoint_2"][
                "treatment_minus_control"
            ],
            "lock_in": "shared rule propagated",
            "confirmatory_status": "valid early falsification; noisy control",
        },
        {
            "setting": "execution_server sequential checkpoint 3",
            "model": "Kimi-K2.6 MaaS",
            "manager_admission": "self-report",
            "terminal_treatment": exec_seq["checkpoint_results"]["3"][
                "recursive_self_report_synthesis"
            ]["all_test_score"],
            "terminal_control": exec_seq["checkpoint_results"]["3"][
                "no_transfer"
            ]["all_test_score"],
            "treatment_minus_control": exec_seq["checkpoint_results"]["3"][
                "treatment_minus_control_all_test_gap"
            ],
            "lock_in": "two recursive manager updates",
            "confirmatory_status": "invalid control action-boundary censoring",
        },
    ]


def build_manifest(
    generated_files: list[Path],
    source_files: list[Path],
    main: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "paper_evidence_frozen_from_audited_runs",
        "date": "2026-07-15",
        "paper_claim": (
            "Shared experience in layered parallel agents can rapidly reduce "
            "behavioral diversity and create stable lock-in, while catastrophic "
            "performance collapse is intermittent and non-replicated. Local "
            "admission blocks zero-command false completions but introduces a "
            "threshold-dependent false-rejection cost."
        ),
        "claim_boundaries": [
            "Do not claim a monotonic ant-mill or death-spiral curve.",
            "Do not claim catastrophic tails are unique to experience transfer.",
            "Do not claim the command threshold generalizes beyond retrospective replay.",
            "Do not pool task-normalized effects as a universal manager-synthesis effect.",
            "Treat DeepSeek recursive synthesis as a stress probe because its bootstrap contained an externally failed source.",
            "Treat execution_server sequential results as descriptive because the no-transfer control hit the frozen action boundary.",
        ],
        "main_protocol": main["protocol"],
        "source_files": {
            path.relative_to(REPO_ROOT).as_posix(): file_sha256(path)
            for path in source_files
        },
        "generated_files": {
            path.relative_to(REPO_ROOT).as_posix(): file_sha256(path)
            for path in generated_files
        },
    }


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    main_audit = load_json(MAIN_AUDIT)
    recursive = {key: load_json(path) for key, path in RECURSIVE_AUDITS.items()}

    tables = {
        "main_depth12_curves.csv": main_curve_rows(main_audit),
        "main_depth12_diversity.csv": main_diversity_rows(main_audit),
        "local_gate_threshold_replay.csv": gate_threshold_rows(main_audit),
        "raw_append_cross_model.csv": raw_append_rows(),
        "recursive_manager_boundaries.csv": recursive_boundary_rows(recursive),
    }

    generated_paths = []
    for filename, rows in tables.items():
        path = OUTPUT_ROOT / filename
        write_csv(path, rows)
        generated_paths.append(path)

    source_files = [MAIN_AUDIT]
    source_files.extend(path for _, _, path in RAW_APPEND_AUDITS if path != MAIN_AUDIT)
    source_files.extend(RECURSIVE_AUDITS.values())
    source_files = list(dict.fromkeys(source_files))

    manifest_path = OUTPUT_ROOT / "evidence_manifest.json"
    manifest = build_manifest(generated_paths, source_files, main_audit)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(generated_paths)} source-data tables to {OUTPUT_ROOT}")
    print(f"Wrote evidence manifest to {manifest_path}")


if __name__ == "__main__":
    main()
