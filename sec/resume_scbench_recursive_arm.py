from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from sec.run_scbench_moa_curve import layer_rows
from sec.run_scbench_moa_multimodel import write_report
from sec.scbench_miniswe import (
    MiniSWEConfig,
    OpenAIRecursiveExperienceSynthesizer,
    RecursiveSynthesisConfig,
    ScbenchMiniSWEWorkerBackend,
    api_key_env_for_model,
    load_local_env_value,
)
from sec.scbench_moa import (
    BestVerifiedAggregator,
    CumulativeSelfReportAcceptancePolicy,
    ExperienceArtifact,
    FinalResult,
    VerificationResult,
    WorkerOutput,
    WorkerRequest,
    WorkerTelemetry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resume a partially completed recursive SCBench MoA arm."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--arm-id", required=True)
    parser.add_argument(
        "--mode",
        choices=(
            "recursive_synthesis",
            "recursive_self_report_synthesis",
        ),
    )
    parser.add_argument("--timeout-sec", type=int, default=900)
    return parser.parse_args()


def load_manager_output(
    manager_root: Path,
    task_id: str,
    layer: int,
    experience_char_limit: int,
) -> WorkerOutput:
    synthesis_path = manager_root / f"layer_{layer}" / "synthesis.json"
    record = json.loads(synthesis_path.read_text(encoding="utf-8"))
    source_count = int(
        record.get(
            "accepted_source_count",
            record["verified_source_count"],
        )
    )
    source_label = str(
        record.get("source_admission_label", "locally Core-verified")
    )
    scores_withheld = bool(record.get("external_scores_withheld", False))
    playbook = str(record["playbook"])
    summary = (
        "Recursive MoA manager synthesis from "
        f"{source_count} {source_label} source(s).\n"
        f"{playbook}"
    )[:experience_char_limit]
    usage = dict(record.get("usage", {}))
    verification = VerificationResult(
        core_passed=source_count,
        core_total=source_count,
        pytest_exit_code=0,
        infrastructure_failure=False,
        test_collection_hash=(
            "recursive-manager-self-report-proxy"
            if scores_withheld
            else "recursive-manager-verified-sources"
        ),
        pytest_collected=source_count,
    )
    artifact = ExperienceArtifact(
        artifact_id=f"{task_id}:moa_manager:{layer}",
        source_worker="moa_manager",
        source_layer=layer,
        summary=summary,
        verification=verification,
        complexity=len(playbook),
    )
    return WorkerOutput(
        worker_id="moa_manager",
        layer=layer,
        workspace=str(synthesis_path),
        summary=summary,
        verification=verification,
        artifact=artifact,
        telemetry=WorkerTelemetry(
            model_calls=1,
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            received_results=source_count
            + (1 if record.get("previous_shared_artifact") else 0),
            received_experience_chars=int(
                record.get("previous_shared_chars", 0) or 0
            ),
            experience_chars=len(summary),
        ),
    )


def archive_retryable_setup_failure(
    layer_dir: Path,
    worker_root: Path,
) -> Path | None:
    log_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (
            layer_dir / "runner.stdout.log",
            layer_dir / "runner.stderr.log",
        )
        if path.is_file()
    )
    is_zero_cost_dependency_timeout = (
        "TimeoutExpired: Command 'uv pip install" in log_text
        and "total_cost=0.0" in log_text
    )
    if not is_zero_cost_dependency_timeout:
        return None

    resolved_worker_root = worker_root.resolve()
    resolved_layer_dir = layer_dir.resolve()
    if not resolved_layer_dir.is_relative_to(resolved_worker_root):
        raise RuntimeError(
            f"Refusing to archive layer outside worker root: {layer_dir}"
        )
    attempt = 1
    while True:
        archive_dir = (
            resolved_worker_root
            / f"{layer_dir.name}_infra_failure_attempt_{attempt}"
        )
        if not archive_dir.exists():
            break
        attempt += 1
    audit = {
        "reason": "pre_model_dependency_install_timeout",
        "model_cost": 0.0,
        "source": str(resolved_layer_dir),
        "archive": str(archive_dir),
        "eligible_for_exact_rerun": True,
    }
    (resolved_layer_dir / "infra_failure_retry_audit.json").write_text(
        json.dumps(audit, indent=2),
        encoding="utf-8",
    )
    resolved_layer_dir.rename(archive_dir)
    return archive_dir


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (repo_root / args.config).resolve()
    run_root = (repo_root / args.run_root).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    configured_mode = config.get("resume_mode")
    if args.mode is not None:
        mode = str(args.mode)
    elif configured_mode is not None:
        mode = str(configured_mode)
    elif args.arm_id.startswith("recursive_self_report_synthesis-"):
        mode = "recursive_self_report_synthesis"
    else:
        mode = "recursive_synthesis"
    if mode not in (
        "recursive_synthesis",
        "recursive_self_report_synthesis",
    ):
        raise ValueError(f"Unsupported recursive resume mode: {mode}")
    model = str(config["models"][0]["model"])
    api_key_env = api_key_env_for_model(model)
    load_local_env_value(repo_root, api_key_env)

    problem = str(config["problem"])
    checkpoint_limit = int(config["checkpoint_limit"])
    arm_root = run_root / args.arm_id
    problem_catalog = run_root / "_problem_catalogs" / args.arm_id
    manager_root = arm_root / "manager"
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
        expected_core_total=int(config["expected_core_total"]),
        expected_test_collection_hash=str(
            config["expected_test_collection_hash"]
        ),
    )
    backends = {
        f"worker_{index}": ScbenchMiniSWEWorkerBackend(
            f"worker_{index}",
            arm_root / "workers" / f"worker_{index}",
            backend_config,
        )
        for index in range(1, int(config["worker_count"]) + 1)
    }

    manager_synthesizer = OpenAIRecursiveExperienceSynthesizer(
        RecursiveSynthesisConfig(
            output_root=manager_root,
            model=model,
            endpoint=str(config["endpoint"]),
            api_key_env=api_key_env,
            specification=(
                problem_catalog
                / problem
                / f"checkpoint_{checkpoint_limit}.md"
            ).read_text(encoding="utf-8"),
            temperature=float(config.get("temperature", 0.6)),
            max_output_tokens=int(
                config.get("manager_max_output_tokens", 4096)
            ),
            experience_char_limit=int(
                config.get("manager_experience_char_limit", 12000)
            ),
            timeout_sec=args.timeout_sec,
            source_admission_label=(
                "workflow-accepted self-reported-success"
                if mode == "recursive_self_report_synthesis"
                else "locally Core-verified"
            ),
            include_source_verification=(mode == "recursive_synthesis"),
        )
    )

    history: list[tuple[WorkerOutput, ...]] = []
    shared_experience: WorkerOutput | None = None
    num_layers = int(config["num_layers"])
    for layer in range(1, num_layers + 1):
        references = (
            (shared_experience,)
            if shared_experience is not None
            else ()
        )

        async def finish_worker(
            worker_id: str,
            backend: ScbenchMiniSWEWorkerBackend,
        ) -> WorkerOutput:
            request = WorkerRequest(
                task_id=args.arm_id,
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
                try:
                    return await backend.restore(request)
                except RuntimeError:
                    archived = archive_retryable_setup_failure(
                        layer_dir,
                        arm_root / "workers" / worker_id,
                    )
                    if archived is None:
                        raise
            return await backend.run(request)

        outputs = tuple(
            await asyncio.gather(
                *[
                    finish_worker(worker_id, backend)
                    for worker_id, backend in backends.items()
                ]
            )
        )
        history.append(outputs)
        if layer == num_layers:
            continue

        manager_path = manager_root / f"layer_{layer}" / "synthesis.json"
        if manager_path.is_file():
            shared_experience = load_manager_output(
                manager_root=manager_root,
                task_id=args.arm_id,
                layer=layer,
                experience_char_limit=int(
                    config["manager_experience_char_limit"]
                ),
            )
            continue

        if mode == "recursive_synthesis":
            synthesis_sources = tuple(
                output
                for output in outputs
                if output.verification.core_verified
            )
        else:
            synthesis_sources = tuple(
                CumulativeSelfReportAcceptancePolicy
                ._as_self_report_reference(output)
                for output in outputs
                if output.telemetry.self_reported_success
            )
        if synthesis_sources:
            shared_experience = (
                await manager_synthesizer.synthesize_layer(
                    task_id=args.arm_id,
                    task=task,
                    layer=layer,
                    previous_shared=shared_experience,
                    verified_results=synthesis_sources,
                )
            )

    aggregator = BestVerifiedAggregator()
    answer = await aggregator.synthesize(
        args.arm_id,
        task,
        history[-1],
    )
    result = FinalResult(
        task_id=args.arm_id,
        answer=answer,
        layers=tuple(history),
    )
    manifest = {
        "task_id": result.task_id,
        "task": task,
        "worker_count": int(config["worker_count"]),
        "num_layers": int(config["num_layers"]),
        "assimilation_mode": mode,
        "resumed": True,
        "answer": result.answer,
        "layers": [
            [asdict(output) for output in layer]
            for layer in result.layers
        ],
    }
    (arm_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
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
            args.arm_id,
            result,
        )
    ]
    report_path = run_root / "contrast_report.json"
    if report_path.is_file():
        existing_report = json.loads(
            report_path.read_text(encoding="utf-8")
        )
        arms = [
            dict(item)
            for item in existing_report.get("arms", [])
            if str(item.get("arm_id")) != args.arm_id
        ]
        existing_rows = [
            dict(item)
            for item in existing_report.get("rows", [])
            if str(item.get("arm_id")) != args.arm_id
        ]
    else:
        arms = []
        existing_rows = []
    arms.append(
        {
            "model": model,
            "replicate": 1,
            "mode": mode,
            "arm_id": args.arm_id,
        }
    )
    rows = existing_rows + rows
    write_report(
        run_root=run_root,
        config=config,
        config_path=config_path,
        arms=arms,
        rows=rows,
    )
    print(
        json.dumps(
            {
                "arm_id": args.arm_id,
                "manifest": str(arm_root / "manifest.json"),
                "report": str(run_root / "contrast_report.json"),
                "layer_rows": rows,
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
