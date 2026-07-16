from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import uuid
from dataclasses import replace
from pathlib import Path

from sec.scbench_miniswe import (
    MiniSWEConfig,
    OpenAIRecursiveExperienceSynthesizer,
    RecursiveSynthesisConfig,
    ScbenchMiniSWEWorkerBackend,
    api_key_env_for_model,
    api_model_for_model,
    load_local_env_value,
    materialize_checkpoint_subset,
)
from sec.scbench_moa import (
    BestVerifiedAggregator,
    CumulativeLocalAcceptancePolicy,
    CumulativeSelfReportAcceptancePolicy,
    MoARunConfig,
    WorkerOutput,
    WorkerRequest,
    run_moa,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen single-model SCBench MoA curve pilot."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("benchmarks/scbench/pilot_curve_config.json"),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("runs_scbench_moa_curve_pilot"),
    )
    parser.add_argument("--timeout-sec", type=int, default=600)
    return parser.parse_args()


async def run_arm(
    repo_root: Path,
    run_root: Path,
    pilot: dict[str, object],
    mode: str,
    timeout_sec: int,
) -> tuple[str, object]:
    arm_id = f"{mode}-{uuid.uuid4().hex}"
    subset_catalog = run_root / "_problem_catalogs" / arm_id
    problem = str(pilot["problem"])
    checkpoint_limit = int(pilot["checkpoint_limit"])
    materialize_checkpoint_subset(
        source_catalog=repo_root / ".benchmarks" / "scb-problems",
        destination_catalog=subset_catalog,
        problem_name=problem,
        checkpoint_limit=checkpoint_limit,
    )
    model = str(pilot["model"])
    api_key_env = api_key_env_for_model(model)
    load_local_env_value(repo_root, api_key_env)
    backend_config = MiniSWEConfig(
        repo_root=repo_root,
        problem_catalog=subset_catalog,
        problem_name=problem,
        model=model,
        api_key_env=api_key_env,
        checkpoint_limit=checkpoint_limit,
        timeout_sec=timeout_sec,
        experience_char_limit=int(pilot["experience_char_limit_per_source"]),
        step_limit=int(pilot["step_limit_per_worker"]),
        pass_policy=str(pilot.get("pass_policy", "all-core-cases")),
        expected_core_total=(
            int(pilot["expected_core_total"])
            if pilot.get("expected_core_total") is not None
            else None
        ),
        expected_test_collection_hash=(
            str(pilot["expected_test_collection_hash"])
            if pilot.get("expected_test_collection_hash")
            else None
        ),
    )
    recursive_synthesizer = None
    initial_shared_experience: WorkerOutput | None = None
    initial_references: tuple[WorkerOutput, ...] = ()
    bootstrap_record: dict[str, object] | None = None
    bootstrap_outputs: list[WorkerOutput] = []
    source_records: list[dict[str, object]] = []
    raw_bootstrap_sources = pilot.get("bootstrap_sources", [])
    bootstrap_modes = {
        str(item) for item in pilot.get("bootstrap_modes", [])
    }
    if bootstrap_modes and mode not in bootstrap_modes:
        raw_bootstrap_sources = []
    for index, raw_source in enumerate(raw_bootstrap_sources, start=1):
        source = dict(raw_source)
        source_workspace = (
            repo_root / str(source["worker_workspace"])
        ).resolve()
        source_layer = int(source["layer"])
        source_worker = str(
            source.get("worker_id", f"bootstrap_worker_{index}")
        )
        source_backend = ScbenchMiniSWEWorkerBackend(
            source_worker,
            source_workspace,
            backend_config,
        )
        restored = await source_backend.restore(
            WorkerRequest(
                task_id=f"{arm_id}:bootstrap",
                task=(
                    f"Frozen verified source for {problem} "
                    f"checkpoint {checkpoint_limit}."
                ),
                worker_id=source_worker,
                layer=source_layer,
                workspace=str(source_workspace),
                previous_results=(),
            )
        )
        if mode in (
            "cumulative_self_report_acceptance",
            "bounded_recent_self_report_acceptance",
            "bounded_diverse_self_report_acceptance",
            "recursive_self_report_synthesis",
        ):
            if not restored.telemetry.self_reported_success:
                raise RuntimeError(
                    f"Bootstrap source {source_workspace} did not "
                    "self-report successful completion"
                )
            bootstrap_output = (
                CumulativeSelfReportAcceptancePolicy
                ._as_self_report_reference(restored)
            )
            admission = "self_report_completion_proxy"
        elif mode == "cumulative_local_acceptance":
            if not restored.telemetry.local_validation_passed:
                raise RuntimeError(
                    f"Bootstrap source {source_workspace} did not pass "
                    "the local completion-and-smoke proxy"
                )
            bootstrap_output = (
                CumulativeLocalAcceptancePolicy
                ._as_local_reference(restored)
            )
            admission = "local_completion_smoke_proxy"
        else:
            if not restored.verification.core_verified:
                raise RuntimeError(
                    f"Bootstrap source {source_workspace} is not "
                    "strictly Core-verified"
                )
            bootstrap_output = restored
            admission = "strict_core_verification"
        bootstrap_outputs.append(bootstrap_output)
        source_records.append(
            {
                "worker_workspace": str(source_workspace),
                "source_layer": source_layer,
                "artifact_id": restored.artifact.artifact_id,
                "core_passed": restored.verification.core_passed,
                "core_total": restored.verification.core_total,
                "all_passed": restored.verification.all_passed,
                "all_total": restored.verification.all_total,
                "test_collection_hash": (
                    restored.verification.test_collection_hash
                ),
                "admission": admission,
                "delivered_artifact_id": (
                    bootstrap_output.artifact.artifact_id
                ),
            }
        )
    if mode in (
        "recursive_synthesis",
        "recursive_self_report_synthesis",
    ):
        specification_path = (
            subset_catalog
            / problem
            / f"checkpoint_{checkpoint_limit}.md"
        )
        recursive_config = RecursiveSynthesisConfig(
            output_root=run_root / arm_id / "manager",
            model=api_model_for_model(model),
            endpoint=str(pilot["endpoint"]),
            api_key_env=api_key_env,
            specification=specification_path.read_text(encoding="utf-8"),
            temperature=float(pilot.get("temperature", 0.6)),
            max_output_tokens=int(
                pilot.get("manager_max_output_tokens", 4096)
            ),
            experience_char_limit=int(
                pilot.get("manager_experience_char_limit", 12000)
            ),
            timeout_sec=timeout_sec,
            source_admission_label=(
                "workflow-accepted self-reported-success"
                if mode == "recursive_self_report_synthesis"
                else "locally Core-verified"
            ),
            include_source_verification=(
                mode == "recursive_synthesis"
            ),
        )
        recursive_synthesizer = OpenAIRecursiveExperienceSynthesizer(
            recursive_config
        )
        if bootstrap_outputs:
            bootstrap_synthesizer = OpenAIRecursiveExperienceSynthesizer(
                replace(
                    recursive_config,
                    output_root=run_root / "_bootstrap_managers" / arm_id,
                )
            )
            task = (
                f"Solve SCBench problem {problem} through checkpoint "
                f"{checkpoint_limit} using the native MiniSWE coding agent."
            )
            initial_shared_experience = (
                await bootstrap_synthesizer.synthesize_layer(
                    task_id=arm_id,
                    task=task,
                    layer=0,
                    previous_shared=None,
                    verified_results=tuple(bootstrap_outputs),
                )
            )
            bootstrap_record = {
                "sources": source_records,
                "initial_shared_artifact": (
                    initial_shared_experience.artifact.artifact_id
                ),
                "initial_shared_chars": len(
                    initial_shared_experience.artifact.summary
                ),
                "synthesis_path": initial_shared_experience.workspace,
            }
    elif mode in (
        "cumulative_success",
        "cumulative_local_acceptance",
        "cumulative_self_report_acceptance",
        "bounded_recent_self_report_acceptance",
        "bounded_diverse_self_report_acceptance",
    ) and bootstrap_outputs:
        initial_references = tuple(bootstrap_outputs)
        bootstrap_record = {
            "sources": source_records,
            "initial_reference_artifacts": [
                output.artifact.artifact_id for output in bootstrap_outputs
            ],
            "initial_reference_count": len(bootstrap_outputs),
            "initial_reference_chars": sum(
                len(output.artifact.summary) for output in bootstrap_outputs
            ),
        }
    elif bootstrap_outputs:
        raise RuntimeError(
            "bootstrap_sources are only supported for recursive modes or "
            "cumulative assimilation"
        )
    result = await run_moa(
        task=(
            f"Solve SCBench problem {problem} through checkpoint "
            f"{checkpoint_limit} using the native MiniSWE coding agent."
        ),
        worker_backend_factory=lambda worker_id, workspace: (
            ScbenchMiniSWEWorkerBackend(worker_id, workspace, backend_config)
        ),
        aggregator=BestVerifiedAggregator(),
        config=MoARunConfig(
            run_root=run_root,
            worker_count=int(pilot["worker_count"]),
            num_layers=int(pilot["num_layers"]),
            assimilation_mode=mode,  # type: ignore[arg-type]
        ),
        task_id=arm_id,
        recursive_synthesizer=recursive_synthesizer,
        initial_shared_experience=initial_shared_experience,
        initial_references=initial_references,
    )
    if bootstrap_record is not None:
        (run_root / arm_id / "bootstrap_manifest.json").write_text(
            json.dumps(bootstrap_record, indent=2),
            encoding="utf-8",
        )
    return arm_id, result


def layer_rows(mode: str, arm_id: str, result: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    layers = result.layers  # type: ignore[attr-defined]
    for layer_index, layer in enumerate(layers, start=1):
        core_scores = [output.verification.score for output in layer]
        all_scores = [output.verification.all_score for output in layer]
        rows.append(
            {
                "mode": mode,
                "arm_id": arm_id,
                "layer": layer_index,
                "workers": len(layer),
                "mean_core_score": statistics.mean(core_scores),
                "min_core_score": min(core_scores),
                "max_core_score": max(core_scores),
                "mean_all_test_score": statistics.mean(all_scores),
                "min_all_test_score": min(all_scores),
                "max_all_test_score": max(all_scores),
                "full_pass_workers": sum(
                    output.verification.passed for output in layer
                ),
                "full_core_workers": sum(
                    output.verification.core_verified for output in layer
                ),
                "mean_duration_sec": statistics.mean(
                    output.telemetry.duration_sec for output in layer
                ),
                "total_input_tokens": sum(
                    output.telemetry.input_tokens for output in layer
                ),
                "total_output_tokens": sum(
                    output.telemetry.output_tokens for output in layer
                ),
                "mean_received_results": statistics.mean(
                    output.telemetry.received_results for output in layer
                ),
                "mean_received_experience_chars": statistics.mean(
                    output.telemetry.received_experience_chars
                    for output in layer
                ),
                "mean_snapshot_bytes": statistics.mean(
                    output.telemetry.snapshot_bytes for output in layer
                ),
                "mean_output_experience_chars": statistics.mean(
                    output.telemetry.experience_chars for output in layer
                ),
            }
        )
    return rows


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (repo_root / args.config).resolve()
    pilot = json.loads(config_path.read_text(encoding="utf-8"))
    if pilot.get("status") != "engineering_pilot_frozen_before_outcomes":
        raise RuntimeError("Pilot config is not frozen")
    load_local_env_value(
        repo_root,
        api_key_env_for_model(str(pilot["model"])),
    )
    run_root = (repo_root / args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    arms: dict[str, str] = {}
    for raw_mode in pilot["modes"]:
        mode = str(raw_mode)
        print(f"Starting curve arm: {mode}", flush=True)
        arm_id, result = await run_arm(
            repo_root=repo_root,
            run_root=run_root,
            pilot=pilot,
            mode=mode,
            timeout_sec=args.timeout_sec,
        )
        arms[mode] = arm_id
        rows.extend(layer_rows(mode, arm_id, result))
        print(f"Completed curve arm: {mode} ({arm_id})", flush=True)

    report = {
        "pilot_config": pilot,
        "config_path": str(config_path),
        "arms": arms,
        "rows": rows,
    }
    report_path = run_root / "curve_report.json"
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    csv_path = run_root / "curve_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(report, indent=2))


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
