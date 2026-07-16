from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path

from sec.scbench_miniswe import (
    MiniSWEConfig,
    ScbenchMiniSWEWorkerBackend,
    api_key_env_for_model,
    load_local_env_value,
    materialize_checkpoint_subset,
)
from sec.scbench_moa import BestVerifiedAggregator, MoARunConfig, run_moa


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SCBench's native MiniSWE agents under standard MoA."
    )
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--problem", default="file_backup")
    parser.add_argument("--checkpoint-limit", type=int, default=1)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument(
        "--mode",
        choices=(
            "no_transfer",
            "source_success",
            "cumulative_success",
            "cumulative_local_acceptance",
            "cumulative_self_report_acceptance",
            "bounded_recent_self_report_acceptance",
            "bounded_diverse_self_report_acceptance",
            "recipient_credit",
        ),
        default="source_success",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("runs_scbench_moa_miniswe"),
    )
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--experience-char-limit", type=int, default=6000)
    parser.add_argument("--step-limit", type=int, default=8)
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    api_key_env = api_key_env_for_model(args.model)
    load_local_env_value(repo_root, api_key_env)
    run_id = uuid.uuid4().hex
    run_root = (repo_root / args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    subset_catalog = run_root / "_problem_catalogs" / run_id
    materialize_checkpoint_subset(
        source_catalog=repo_root / ".benchmarks" / "scb-problems",
        destination_catalog=subset_catalog,
        problem_name=args.problem,
        checkpoint_limit=args.checkpoint_limit,
    )
    backend_config = MiniSWEConfig(
        repo_root=repo_root,
        problem_catalog=subset_catalog,
        problem_name=args.problem,
        model=args.model,
        api_key_env=api_key_env,
        checkpoint_limit=args.checkpoint_limit,
        timeout_sec=args.timeout_sec,
        experience_char_limit=args.experience_char_limit,
        step_limit=args.step_limit,
    )
    result = await run_moa(
        task=(
            f"Solve SCBench problem {args.problem} through checkpoint "
            f"{args.checkpoint_limit} using the native MiniSWE coding agent."
        ),
        worker_backend_factory=lambda worker_id, workspace: (
            ScbenchMiniSWEWorkerBackend(worker_id, workspace, backend_config)
        ),
        aggregator=BestVerifiedAggregator(),
        config=MoARunConfig(
            run_root=run_root,
            worker_count=args.workers,
            num_layers=args.layers,
            assimilation_mode=args.mode,
        ),
        task_id=run_id,
    )
    print(
        json.dumps(
            {
                "run_id": run_id,
                "model": args.model,
                "problem": args.problem,
                "checkpoint_limit": args.checkpoint_limit,
                "step_limit": args.step_limit,
                "mode": args.mode,
                "layers": [
                    [
                        {
                            "worker": output.worker_id,
                            "core": (
                                f"{output.verification.core_passed}/"
                                f"{output.verification.core_total}"
                            ),
                            "calls": output.telemetry.model_calls,
                            "input_tokens": output.telemetry.input_tokens,
                            "output_tokens": output.telemetry.output_tokens,
                            "duration_sec": round(
                                output.telemetry.duration_sec, 2
                            ),
                        }
                        for output in layer
                    ]
                    for layer in result.layers
                ],
                "selected_workspace": result.answer,
                "manifest": str(run_root / run_id / "manifest.json"),
            },
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
