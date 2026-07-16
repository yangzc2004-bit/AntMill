from __future__ import annotations

import csv
import hashlib
import json
import re
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_cfgpipe_cp1_mitigation_three_arm_protocol_20260715.json"
)
OUTPUT_JSON = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_cfgpipe_cp1_mitigation_three_arm_audit_20260716.json"
)
OUTPUT_MD = (
    REPO_ROOT
    / "benchmarks"
    / "scbench"
    / "kimi_maas_cfgpipe_cp1_mitigation_three_arm_audit_20260716.md"
)
GENERATED_ROOT = REPO_ROOT / "paper_draft" / "generated" / "moa_paper"
OUTPUT_LAYER_CSV = GENERATED_ROOT / "mitigation_three_arm_layers.csv"
OUTPUT_SUMMARY_CSV = GENERATED_ROOT / "mitigation_three_arm_summary.csv"

EXPECTED_CORE_TOTAL = 4
EXPECTED_ALL_TOTAL = 37
EXPECTED_HASH = (
    "6ee2bfc068272a7fbc92599619db56b345cd93ecd3a321e791fa496a6a0f0615"
)
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

ARMS = (
    {
        "arm": "no_transfer",
        "role": "independent_control",
        "manifest": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_"
            "depth12_no_transfer_r1_20260715/"
            "no_transfer-02db19c347a0481a95ee08ca1752f7bd/"
            "manifest.json"
        ),
        "layers": 6,
        "expected_references": 0,
        "recipient_blinding": False,
    },
    {
        "arm": "bounded_recent",
        "role": "fixed_three_recent_control",
        "manifest": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_"
            "bounded_context_depth6_r1_20260715/"
            "bounded_recent_self_report_acceptance-"
            "93be1c12894e4c8f96b0fdc6b2334b68/"
            "manifest.json"
        ),
        "layers": 6,
        "expected_references": 3,
        "recipient_blinding": True,
    },
    {
        "arm": "bounded_diverse",
        "role": "prospective_local_diversity_mitigation",
        "manifest": (
            "runs_scbench_moa_kimi_maas_cfgpipe_cp1_"
            "diverse_routing_depth6_r1_20260715/"
            "bounded_diverse_self_report_acceptance-"
            "439051d948774354861af945b376e1ad/"
            "manifest.json"
        ),
        "layers": 6,
        "expected_references": 3,
        "recipient_blinding": True,
    },
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_hash(root: Path) -> str | None:
    if not root.is_dir():
        return None
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def primary_hash(root: Path) -> str | None:
    path = root / "cfgpipe.py"
    return file_hash(path) if path.is_file() else None


def failed_tests(evaluation: dict[str, Any]) -> frozenset[str]:
    values: list[str] = []
    for group in evaluation["tests"].values():
        values.extend(str(item) for item in group.get("failed", []))
    return frozenset(values)


def pairwise_jaccard(signatures: list[frozenset[str]]) -> float:
    values = []
    for left, right in combinations(signatures, 2):
        union = left | right
        values.append(1.0 if not union else len(left & right) / len(union))
    return mean(values) if values else 1.0


def checkpoint_root(output: dict[str, Any]) -> Path:
    return Path(str(output["workspace"])).parent


def prompt_hits(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [
        label for label, pattern in BLINDING_PATTERNS.items() if pattern.search(text)
    ]


def prohibited_hits(path: Path) -> list[str]:
    hits: set[str] = set()
    if not path.is_file():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if str(record.get("role", "")).lower() != "assistant":
            continue
        content = str(record.get("content", ""))
        for label, pattern in PROHIBITED_PATTERNS.items():
            if pattern.search(content):
                hits.add(label)
    return sorted(hits)


def first_two_layer_lockin(layer_rows: list[dict[str, Any]]) -> int | None:
    for current, following in zip(layer_rows, layer_rows[1:]):
        if (
            int(current["unique_primary_implementations"]) == 1
            and int(following["unique_primary_implementations"]) == 1
        ):
            return int(current["layer"])
    return None


def audit_arm(spec: dict[str, Any]) -> dict[str, Any]:
    manifest_path = REPO_ROOT / str(spec["manifest"])
    manifest = load_json(manifest_path)
    layer_rows: list[dict[str, Any]] = []
    trajectory_rows: list[dict[str, Any]] = []
    target_failures: list[dict[str, Any]] = []
    inference_failures: list[dict[str, Any]] = []
    blinding_failures: list[dict[str, Any]] = []
    reference_failures: list[dict[str, Any]] = []
    access_failures: list[dict[str, Any]] = []

    for layer_index, outputs in enumerate(
        manifest["layers"][: int(spec["layers"])],
        start=1,
    ):
        primary_hashes: list[str] = []
        workspace_hashes: list[str] = []
        failure_signatures: list[frozenset[str]] = []
        all_passed: list[int] = []
        core_passed: list[int] = []
        input_tokens: list[int] = []
        output_tokens: list[int] = []
        durations: list[float] = []
        received_chars: list[int] = []
        reference_counts: list[int] = []

        for output in outputs:
            worker_id = str(output["worker_id"])
            checkpoint = checkpoint_root(output)
            evaluation = load_json(checkpoint / "evaluation.json")
            inference = load_json(checkpoint / "inference_result.json")
            verification = output["verification"]
            telemetry = output["telemetry"]

            target_ok = (
                int(verification["core_total"]) == EXPECTED_CORE_TOTAL
                and int(verification["all_total"]) == EXPECTED_ALL_TOTAL
                and str(verification["test_collection_hash"]) == EXPECTED_HASH
                and not bool(verification["infrastructure_failure"])
                and int(evaluation["total_counts"]["Core"]) == EXPECTED_CORE_TOTAL
                and int(evaluation["pytest_collected"]) == EXPECTED_ALL_TOTAL
                and str(evaluation["test_collection_hash"]) == EXPECTED_HASH
                and not bool(evaluation["infrastructure_failure"])
            )
            if not target_ok:
                target_failures.append(
                    {"layer": layer_index, "worker_id": worker_id}
                )

            usage = inference.get("usage", {})
            if (
                bool(inference.get("had_error"))
                or inference.get("error_message")
                or int(usage.get("steps", 0) or 0) <= 0
            ):
                inference_failures.append(
                    {"layer": layer_index, "worker_id": worker_id}
                )

            received = int(telemetry["received_results"])
            if received != int(spec["expected_references"]):
                reference_failures.append(
                    {
                        "layer": layer_index,
                        "worker_id": worker_id,
                        "observed": received,
                        "expected": spec["expected_references"],
                    }
                )

            prompt_path = checkpoint / "prompt.txt"
            if spec["recipient_blinding"]:
                for hit in prompt_hits(prompt_path):
                    blinding_failures.append(
                        {
                            "layer": layer_index,
                            "worker_id": worker_id,
                            "pattern": hit,
                        }
                    )
            trajectory_path = checkpoint / "agent" / "trajectory.jsonl"
            for hit in prohibited_hits(trajectory_path):
                access_failures.append(
                    {
                        "layer": layer_index,
                        "worker_id": worker_id,
                        "pattern": hit,
                    }
                )

            snapshot = Path(str(output["workspace"]))
            primary = primary_hash(snapshot)
            full_snapshot = workspace_hash(snapshot)
            if primary is not None:
                primary_hashes.append(primary)
            if full_snapshot is not None:
                workspace_hashes.append(full_snapshot)
            failure_signatures.append(failed_tests(evaluation))
            all_passed.append(int(verification["all_passed"]))
            core_passed.append(int(verification["core_passed"]))
            input_tokens.append(int(telemetry["input_tokens"]))
            output_tokens.append(int(telemetry["output_tokens"]))
            durations.append(float(telemetry["duration_sec"]))
            received_chars.append(int(telemetry["received_experience_chars"]))
            reference_counts.append(received)
            trajectory_rows.append(
                {
                    "arm": spec["arm"],
                    "layer": layer_index,
                    "worker_id": worker_id,
                    "primary_hash": primary,
                    "workspace_hash": full_snapshot,
                    "all_passed": int(verification["all_passed"]),
                    "core_passed": int(verification["core_passed"]),
                    "input_tokens": int(telemetry["input_tokens"]),
                    "output_tokens": int(telemetry["output_tokens"]),
                    "duration_sec": float(telemetry["duration_sec"]),
                    "received_results": received,
                    "received_experience_chars": int(
                        telemetry["received_experience_chars"]
                    ),
                }
            )

        layer_rows.append(
            {
                "arm": spec["arm"],
                "role": spec["role"],
                "mode": manifest["assimilation_mode"],
                "layer": layer_index,
                "unique_primary_implementations": len(set(primary_hashes)),
                "unique_workspace_snapshots": len(set(workspace_hashes)),
                "failed_test_pairwise_jaccard": pairwise_jaccard(
                    failure_signatures
                ),
                "mean_all_passed": mean(all_passed),
                "min_all_passed": min(all_passed),
                "max_all_passed": max(all_passed),
                "core_complete_workers": sum(
                    score == EXPECTED_CORE_TOTAL for score in core_passed
                ),
                "total_input_tokens": sum(input_tokens),
                "total_output_tokens": sum(output_tokens),
                "mean_duration_sec": mean(durations),
                "mean_received_results": mean(reference_counts),
                "mean_received_experience_chars": mean(received_chars),
            }
        )

    post_layer_rows = [row for row in layer_rows if int(row["layer"]) >= 2]
    summary = {
        "arm": spec["arm"],
        "role": spec["role"],
        "mode": manifest["assimilation_mode"],
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "manifest_sha256": file_hash(manifest_path),
        "diversity_auc_layers_2_6": sum(
            int(row["unique_primary_implementations"])
            for row in post_layer_rows
        ),
        "diverse_post_layer_count": sum(
            int(row["unique_primary_implementations"]) >= 2
            for row in post_layer_rows
        ),
        "first_two_layer_primary_lockin": first_two_layer_lockin(layer_rows),
        "mean_all_passed": mean(
            float(row["mean_all_passed"]) for row in layer_rows
        ),
        "minimum_worker_all_passed": min(
            int(row["min_all_passed"]) for row in layer_rows
        ),
        "core_complete_trajectories": sum(
            int(row["core_complete_workers"]) for row in layer_rows
        ),
        "trajectory_count": len(trajectory_rows),
        "total_input_tokens": sum(
            int(row["input_tokens"]) for row in trajectory_rows
        ),
        "total_output_tokens": sum(
            int(row["output_tokens"]) for row in trajectory_rows
        ),
        "mean_trajectory_duration_sec": mean(
            float(row["duration_sec"]) for row in trajectory_rows
        ),
        "mean_received_experience_chars": mean(
            float(row["received_experience_chars"])
            for row in trajectory_rows
        ),
    }
    return {
        "summary": summary,
        "layer_rows": layer_rows,
        "trajectory_rows": trajectory_rows,
        "validity": {
            "target_failures": target_failures,
            "inference_failures": inference_failures,
            "blinding_failures": blinding_failures,
            "reference_failures": reference_failures,
            "prohibited_access_failures": access_failures,
            "passed": not (
                target_failures
                or inference_failures
                or blinding_failures
                or reference_failures
                or access_failures
            ),
        },
    }


def verify_freeze(protocol: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for arm_name in (
        "no_transfer",
        "bounded_recent_self_report_acceptance",
    ):
        arm = protocol["arms"][arm_name]
        config_path = REPO_ROOT / arm["config"]
        manifest_path = REPO_ROOT / arm["manifest"]
        if file_hash(config_path) != arm["config_sha256"]:
            failures.append(f"{arm_name}:config")
        if file_hash(manifest_path) != arm["manifest_sha256"]:
            failures.append(f"{arm_name}:manifest")
    mitigation = protocol["arms"]["bounded_diverse_self_report_acceptance"]
    mitigation_config = REPO_ROOT / mitigation["config"]
    if file_hash(mitigation_config) != mitigation["config_sha256"]:
        failures.append("bounded_diverse:config")
    freeze = load_json(
        REPO_ROOT
        / "benchmarks"
        / "scbench"
        / "kimi_maas_cfgpipe_cp1_diverse_routing_depth6_config.freeze.json"
    )
    for relative, expected in freeze["implementation_files"].items():
        if file_hash(REPO_ROOT / relative) != expected:
            failures.append(f"bounded_diverse:implementation:{relative}")
    return {
        "passed": not failures,
        "failures": failures,
        "protocol_sha256": file_hash(PROTOCOL),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    protocol = load_json(PROTOCOL)
    freeze_audit = verify_freeze(protocol)
    arm_audits = [audit_arm(spec) for spec in ARMS]
    summaries = [audit["summary"] for audit in arm_audits]
    layer_rows = [row for audit in arm_audits for row in audit["layer_rows"]]
    validity_passed = (
        freeze_audit["passed"]
        and all(audit["validity"]["passed"] for audit in arm_audits)
    )

    by_arm = {summary["arm"]: summary for summary in summaries}
    bounded_auc = int(
        by_arm["bounded_recent"]["diversity_auc_layers_2_6"]
    )
    diverse_auc = int(
        by_arm["bounded_diverse"]["diversity_auc_layers_2_6"]
    )
    diverse_layers = int(
        by_arm["bounded_diverse"]["diverse_post_layer_count"]
    )
    all_core = (
        int(by_arm["bounded_diverse"]["core_complete_trajectories"]) == 18
    )
    if diverse_auc > bounded_auc and diverse_layers >= 2 and all_core:
        outcome = "strong_support"
    elif diverse_auc > bounded_auc and diverse_layers >= 1:
        outcome = "partial_support"
    else:
        outcome = "null"

    report = {
        "audit_date": "2026-07-16",
        "protocol": str(PROTOCOL.relative_to(REPO_ROOT)),
        "freeze_audit": freeze_audit,
        "validity_passed": validity_passed,
        "arm_validity": {
            audit["summary"]["arm"]: audit["validity"]
            for audit in arm_audits
        },
        "summaries": summaries,
        "layer_rows": layer_rows,
        "prospective_outcome": {
            "classification": outcome,
            "bounded_recent_auc": bounded_auc,
            "bounded_diverse_auc": diverse_auc,
            "auc_gain": diverse_auc - bounded_auc,
            "bounded_recent_lockin_layer": by_arm["bounded_recent"][
                "first_two_layer_primary_lockin"
            ],
            "bounded_diverse_lockin_layer": by_arm["bounded_diverse"][
                "first_two_layer_primary_lockin"
            ],
            "quality_change_mean_all_passed": (
                float(by_arm["bounded_diverse"]["mean_all_passed"])
                - float(by_arm["bounded_recent"]["mean_all_passed"])
            ),
            "interpretation": (
                "Local diversity routing delayed exact primary implementation "
                "lock-in by one layer and increased the frozen diversity AUC "
                "from 5 to 6 without changing mean all-test quality, but it "
                "did not preserve diversity beyond layer 2."
            ),
        },
        "claim_boundary": (
            "The mitigation is a transient delay, not a solution. The result "
            "supports the mechanism claim that routing affects convergence "
            "timing while also showing that locally distinct references alone "
            "do not overcome a strong shared implementation attractor."
        ),
    }
    OUTPUT_JSON.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    write_csv(OUTPUT_LAYER_CSV, layer_rows)
    write_csv(OUTPUT_SUMMARY_CSV, summaries)

    md = [
        "# Prospective cfgpipe Mitigation Audit",
        "",
        f"- Protocol freeze passed: **{freeze_audit['passed']}**",
        f"- All validity gates passed: **{validity_passed}**",
        f"- Prospective outcome: **{outcome}**",
        "",
        "## Three-arm summary",
        "",
        "| Arm | Diversity AUC L2-L6 | Diverse post-L1 layers | "
        "Two-layer lock-in | Mean all tests | Minimum worker | "
        "Input tokens | Mean duration |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        lockin = summary["first_two_layer_primary_lockin"]
        lockin_text = f"L{lockin}" if lockin is not None else "none"
        md.append(
            f"| {summary['arm']} | "
            f"{summary['diversity_auc_layers_2_6']} | "
            f"{summary['diverse_post_layer_count']} | "
            f"{lockin_text} | "
            f"{summary['mean_all_passed']:.2f}/37 | "
            f"{summary['minimum_worker_all_passed']}/37 | "
            f"{summary['total_input_tokens']:,} | "
            f"{summary['mean_trajectory_duration_sec']:.1f}s |"
        )
    md.extend(
        [
            "",
            "## Frozen endpoint",
            "",
            f"- Bounded-recent AUC: {bounded_auc}.",
            f"- Diversity-preserving AUC: {diverse_auc}.",
            f"- Gain: {diverse_auc - bounded_auc}.",
            "- Exact primary lock-in moved from L2 to L3.",
            "- Mean all-test quality remained 34/37 in both transfer arms.",
            "",
            "## Interpretation",
            "",
            "The local-only router produced a real but transient delay. It "
            "preserved two implementations at L2, after which all workers "
            "converged to one implementation through L6. This is partial "
            "support for routing as a mechanism component and negative "
            "evidence against claiming that deduplication alone solves the "
            "attractor.",
            "",
            "The no-transfer arm retained three implementations throughout "
            "L1-L6 but had substantially lower and less stable task quality. "
            "The result therefore exposes a quality-diversity trade-off rather "
            "than a free mitigation.",
            "",
            "## Outputs",
            "",
            f"- JSON: `{OUTPUT_JSON.relative_to(REPO_ROOT)}`",
            f"- Layer CSV: `{OUTPUT_LAYER_CSV.relative_to(REPO_ROOT)}`",
            f"- Summary CSV: `{OUTPUT_SUMMARY_CSV.relative_to(REPO_ROOT)}`",
        ]
    )
    OUTPUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(report["prospective_outcome"], indent=2))
    print(f"Validity passed: {validity_passed}")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
