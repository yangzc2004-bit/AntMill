from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from sec.run_scbench_moa_curve import layer_rows
from sec.run_scbench_moa_multimodel import write_report
from sec.scbench_miniswe import (
    MiniSWEConfig,
    OpenAIRecursiveExperienceSynthesizer,
    RecursiveSynthesisConfig,
    SequentialCheckpointMiniSWEWorkerBackend,
    api_key_env_for_model,
    api_model_for_model,
    load_local_env_value,
    materialize_checkpoint_subset,
)
from sec.scbench_moa import BestVerifiedAggregator, MoARunConfig, run_moa


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a recursive MoA curve over sequential SCBench checkpoints."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=int, default=1200)
    return parser.parse_args()


def cumulative_specification(
    catalog: Path,
    problem: str,
    checkpoint: int,
) -> str:
    sections = []
    for checkpoint_number in range(1, checkpoint + 1):
        spec_path = (
            catalog
            / problem
            / f"checkpoint_{checkpoint_number}.md"
        )
        sections.append(
            f"# Checkpoint {checkpoint_number}\n\n"
            f"{spec_path.read_text(encoding='utf-8')}"
        )
    return "\n\n".join(sections)


async def run_arm(
    *,
    repo_root: Path,
    run_root: Path,
    config: dict[str, object],
    mode: str,
    timeout_sec: int,
) -> tuple[str, object]:
    model = str(config["model"])
    problem = str(config["problem"])
    checkpoint_sequence = [
        int(value) for value in config["checkpoint_sequence"]
    ]
    expected_targets = {
        int(checkpoint): dict(target)
        for checkpoint, target in dict(
            config["expected_targets"]
        ).items()
    }
    arm_id = f"{mode}-{uuid.uuid4().hex}"
    configs_by_layer: dict[int, MiniSWEConfig] = {}
    specifications_by_layer: dict[int, str] = {}
    api_key_env = api_key_env_for_model(model)
    load_local_env_value(repo_root, api_key_env)

    for layer, checkpoint in enumerate(checkpoint_sequence, start=1):
        catalog = (
            run_root
            / "_problem_catalogs"
            / arm_id
            / f"layer_{layer}_checkpoint_{checkpoint}"
        )
        materialize_checkpoint_subset(
            source_catalog=repo_root / ".benchmarks" / "scb-problems",
            destination_catalog=catalog,
            problem_name=problem,
            checkpoint_limit=checkpoint,
        )
        target = expected_targets[checkpoint]
        configs_by_layer[layer] = MiniSWEConfig(
            repo_root=repo_root,
            problem_catalog=catalog,
            problem_name=problem,
            model=model,
            api_key_env=api_key_env,
            checkpoint_limit=checkpoint,
            timeout_sec=timeout_sec,
            experience_char_limit=int(
                config["experience_char_limit_per_source"]
            ),
            step_limit=int(config["step_limit_per_checkpoint"]),
            pass_policy=str(config.get("pass_policy", "all-core-cases")),
            expected_core_total=int(target["core_total"]),
            expected_test_collection_hash=str(
                target["test_collection_hash"]
            ),
        )
        specifications_by_layer[layer] = cumulative_specification(
            catalog,
            problem,
            checkpoint,
        )

    recursive_synthesizer = None
    if mode in (
        "recursive_synthesis",
        "recursive_self_report_synthesis",
    ):
        recursive_synthesizer = OpenAIRecursiveExperienceSynthesizer(
            RecursiveSynthesisConfig(
                output_root=run_root / arm_id / "manager",
                model=api_model_for_model(model),
                endpoint=str(config["endpoint"]),
                api_key_env=api_key_env,
                specification="",
                specifications_by_layer=specifications_by_layer,
                temperature=float(config.get("temperature", 0.6)),
                max_output_tokens=int(
                    config.get("manager_max_output_tokens", 5000)
                ),
                experience_char_limit=int(
                    config.get("manager_experience_char_limit", 20000)
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
        )

    task = (
        f"Incrementally solve SCBench project {problem} across target "
        f"checkpoints {checkpoint_sequence} using native MiniSWE agents."
    )
    result = await run_moa(
        task=task,
        worker_backend_factory=lambda worker_id, workspace: (
            SequentialCheckpointMiniSWEWorkerBackend(
                worker_id=worker_id,
                workspace=workspace,
                configs_by_layer=configs_by_layer,
            )
        ),
        aggregator=BestVerifiedAggregator(),
        config=MoARunConfig(
            run_root=run_root,
            worker_count=int(config["worker_count"]),
            num_layers=len(checkpoint_sequence),
            assimilation_mode=mode,  # type: ignore[arg-type]
        ),
        task_id=arm_id,
        recursive_synthesizer=recursive_synthesizer,
    )
    return arm_id, result


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (repo_root / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        config.get("status")
        != "engineering_sequential_checkpoint_curve_frozen_before_outcomes"
    ):
        raise RuntimeError("Sequential checkpoint config is not frozen")
    run_root = (repo_root / args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    checkpoint_sequence = [
        int(value) for value in config["checkpoint_sequence"]
    ]

    arms: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []

    async def execute_mode(
        mode: str,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        print(f"Starting sequential arm: {mode}", flush=True)
        arm_id, result = await run_arm(
            repo_root=repo_root,
            run_root=run_root,
            config=config,
            mode=mode,
            timeout_sec=args.timeout_sec,
        )
        arm = {
            "model": str(config["model"]),
            "replicate": 1,
            "mode": mode,
            "arm_id": arm_id,
        }
        arm_rows: list[dict[str, object]] = []
        for row, checkpoint in zip(
            layer_rows(mode, arm_id, result),
            checkpoint_sequence,
            strict=True,
        ):
            arm_rows.append(
                {
                    "model": str(config["model"]),
                    "replicate": 1,
                    "checkpoint": checkpoint,
                    **row,
                }
            )
        print(
            f"Completed sequential arm: {mode} ({arm_id})",
            flush=True,
        )
        return arm, arm_rows

    modes = [str(mode) for mode in config["mode_order"]]
    if bool(config.get("parallel_arms", False)):
        completed_arms = await asyncio.gather(
            *(execute_mode(mode) for mode in modes)
        )
        for arm, arm_rows in completed_arms:
            arms.append(arm)
            rows.extend(arm_rows)
        write_report(
            run_root=run_root,
            config=config,
            config_path=config_path,
            arms=arms,
            rows=rows,
        )
    else:
        for mode in modes:
            arm, arm_rows = await execute_mode(mode)
            arms.append(arm)
            rows.extend(arm_rows)
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
                "report": str(run_root / "contrast_report.json"),
                "csv": str(run_root / "contrast_report.csv"),
                "arms": arms,
                "rows": rows,
            },
            indent=2,
        ),
        flush=True,
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
