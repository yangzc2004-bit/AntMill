from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
from dataclasses import asdict
from pathlib import Path

from sec.run_scbench_moa_curve import layer_rows
from sec.scbench_miniswe import (
    MiniSWEConfig,
    ScbenchMiniSWEWorkerBackend,
    api_key_env_for_model,
    load_local_env_value,
)
from sec.scbench_moa import (
    BestVerifiedAggregator,
    BoundedDiverseSelfReportAcceptancePolicy,
    BoundedRecentSelfReportAcceptancePolicy,
    CumulativeLocalAcceptancePolicy,
    CumulativeSelfReportAcceptancePolicy,
    CumulativeSuccessPolicy,
    FinalResult,
    WorkerOutput,
    WorkerRequest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extend a completed bootstrapped cumulative SCBench arm."
    )
    parser.add_argument("--extension-config", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=int, default=900)
    return parser.parse_args()


async def restore_bootstrap_sources(
    repo_root: Path,
    arm_id: str,
    task: str,
    config: dict[str, object],
    backend_config: MiniSWEConfig,
) -> tuple[WorkerOutput, ...]:
    outputs: list[WorkerOutput] = []
    for index, raw_source in enumerate(config["bootstrap_sources"], start=1):
        source = dict(raw_source)
        worker_id = str(
            source.get("worker_id", f"bootstrap_worker_{index}")
        )
        workspace = (
            repo_root / str(source["worker_workspace"])
        ).resolve()
        layer = int(source["layer"])
        backend = ScbenchMiniSWEWorkerBackend(
            worker_id,
            workspace,
            backend_config,
        )
        output = await backend.restore(
            WorkerRequest(
                task_id=f"{arm_id}:bootstrap",
                task=task,
                worker_id=worker_id,
                layer=layer,
                workspace=str(workspace),
                previous_results=(),
            )
        )
        if not output.verification.core_verified:
            raise RuntimeError(
                f"Bootstrap source {workspace} is not Core-verified"
            )
        outputs.append(output)
    return tuple(outputs)


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    extension_path = (repo_root / args.extension_config).resolve()
    extension = json.loads(extension_path.read_text(encoding="utf-8"))
    if (
        extension.get("status")
        != "engineering_depth_extension_frozen_before_outcomes"
    ):
        raise RuntimeError("Depth extension config is not frozen")

    base_config_path = (
        repo_root / str(extension["base_config"])
    ).resolve()
    config = json.loads(base_config_path.read_text(encoding="utf-8"))
    run_root = (repo_root / str(extension["run_root"])).resolve()
    arm_id = str(extension["arm_id"])
    arm_root = run_root / arm_id
    completed_layers = int(extension["completed_layers"])
    target_layers = int(extension["target_layers"])
    if target_layers <= completed_layers:
        raise ValueError("target_layers must exceed completed_layers")

    model = str(config["models"][0]["model"])
    api_key_env = api_key_env_for_model(model)
    load_local_env_value(repo_root, api_key_env)
    problem = str(config["problem"])
    checkpoint_limit = int(config["checkpoint_limit"])
    problem_catalog = run_root / "_problem_catalogs" / arm_id
    task = (
        f"Solve SCBench problem {problem} through checkpoint "
        f"{checkpoint_limit} using the native MiniSWE coding agent."
    )
    backend_config = MiniSWEConfig(
        repo_root=repo_root,
        problem_catalog=problem_catalog,
        problem_name=problem,
        model=model,
        api_key_env=api_key_env,
        checkpoint_limit=checkpoint_limit,
        timeout_sec=args.timeout_sec,
        experience_char_limit=int(config["experience_char_limit_per_source"]),
        step_limit=int(config["step_limit_per_worker"]),
        pass_policy=str(config.get("pass_policy", "all-core-cases")),
        expected_core_total=int(config["expected_core_total"]),
        expected_test_collection_hash=str(
            config["expected_test_collection_hash"]
        ),
    )
    worker_count = int(config["worker_count"])
    backends = {
        f"worker_{index}": ScbenchMiniSWEWorkerBackend(
            f"worker_{index}",
            arm_root / "workers" / f"worker_{index}",
            backend_config,
        )
        for index in range(1, worker_count + 1)
    }
    restored_bootstrap = await restore_bootstrap_sources(
        repo_root=repo_root,
        arm_id=arm_id,
        task=task,
        config=config,
        backend_config=backend_config,
    )
    mode = str(
        extension.get(
            "assimilation_mode",
            config["models"][0]["replicates"][0]["mode_order"][0],
        )
    )
    if mode == "cumulative_success":
        bootstrap = restored_bootstrap
        policy = CumulativeSuccessPolicy(seed_results=bootstrap)
    elif mode == "cumulative_local_acceptance":
        bootstrap = tuple(
            CumulativeLocalAcceptancePolicy._as_local_reference(output)
            for output in restored_bootstrap
        )
        policy = CumulativeLocalAcceptancePolicy(seed_results=bootstrap)
    elif mode in (
        "cumulative_self_report_acceptance",
        "bounded_recent_self_report_acceptance",
        "bounded_diverse_self_report_acceptance",
    ):
        bootstrap = tuple(
            CumulativeSelfReportAcceptancePolicy._as_self_report_reference(
                output
            )
            for output in restored_bootstrap
        )
        if mode == "bounded_recent_self_report_acceptance":
            policy = BoundedRecentSelfReportAcceptancePolicy(
                seed_results=bootstrap
            )
        elif mode == "bounded_diverse_self_report_acceptance":
            policy = BoundedDiverseSelfReportAcceptancePolicy(
                seed_results=bootstrap
            )
        else:
            policy = CumulativeSelfReportAcceptancePolicy(
                seed_results=bootstrap
            )
    else:
        raise ValueError(f"Unsupported cumulative extension mode: {mode}")

    history: list[tuple[WorkerOutput, ...]] = []
    for layer in range(1, target_layers + 1):
        previous_layer = history[-1] if history else ()
        references = policy.select(previous_layer, history)

        async def run_or_restore(
            worker_id: str,
            backend: ScbenchMiniSWEWorkerBackend,
        ) -> WorkerOutput:
            request = WorkerRequest(
                task_id=arm_id,
                task=task,
                worker_id=worker_id,
                layer=layer,
                workspace=str(arm_root / "workers" / worker_id),
                previous_results=references,
            )
            layer_dir = (
                arm_root / "workers" / worker_id / f"layer_{layer}"
            )
            if layer_dir.is_dir():
                return await backend.restore(request)
            return await backend.run(request)

        outputs = tuple(
            await asyncio.gather(
                *[
                    run_or_restore(worker_id, backend)
                    for worker_id, backend in backends.items()
                ]
            )
        )
        history.append(outputs)
        scores = [output.verification.score for output in outputs]
        print(
            json.dumps(
                {
                    "layer": layer,
                    "restored": layer <= completed_layers,
                    "reference_count": len(references),
                    "mean_core": statistics.mean(scores),
                    "worker_core": [
                        [
                            output.verification.core_passed,
                            output.verification.core_total,
                        ]
                        for output in outputs
                    ],
                }
            ),
            flush=True,
        )

    aggregator = BestVerifiedAggregator()
    answer = await aggregator.synthesize(arm_id, task, history[-1])
    result = FinalResult(
        task_id=arm_id,
        answer=answer,
        layers=tuple(history),
    )
    manifest_path = arm_root / f"manifest_depth{target_layers}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "task_id": arm_id,
                "task": task,
                "worker_count": worker_count,
                "num_layers": target_layers,
                "assimilation_mode": mode,
                "resumed_from_layers": completed_layers,
                "bootstrap_sources": [
                    asdict(output) for output in bootstrap
                ],
                "answer": answer,
                "layers": [
                    [asdict(output) for output in layer]
                    for layer in history
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "model": model,
            "replicate": 1,
            **row,
        }
        for row in layer_rows(
            mode,
            arm_id,
            result,
        )
    ]
    report = {
        "extension_config": extension,
        "extension_config_path": str(extension_path),
        "base_config": config,
        "base_config_path": str(base_config_path),
        "arm_id": arm_id,
        "rows": rows,
    }
    report_path = run_root / f"depth{target_layers}_extension_report.json"
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    csv_path = run_root / f"depth{target_layers}_extension_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "report": str(report_path),
                "csv": str(csv_path),
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
