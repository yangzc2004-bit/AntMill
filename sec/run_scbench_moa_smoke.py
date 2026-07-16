from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sec.scbench_moa import (
    BestVerifiedAggregator,
    FixtureWorkerBackend,
    MoARunConfig,
    ScbenchSnapshotEvaluator,
    run_moa,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an infrastructure-only MoA smoke against SCBench."
    )
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
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path("runs_scbench_moa_smoke"),
    )
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    runner = repo_root / ".benchmarks" / "slop-code-bench"
    fixture_root = runner / "tests" / "evaluation" / "fixtures" / "word_stats"
    evaluator = ScbenchSnapshotEvaluator(
        repo_root=repo_root,
        problem_name="problem",
        checkpoint=1,
        problem_catalog=fixture_root,
    )
    result = await run_moa(
        task="SCBench infrastructure fixture: word_stats checkpoint 1.",
        worker_backend_factory=lambda worker_id, workspace: FixtureWorkerBackend(
            worker_id=worker_id,
            workspace=workspace,
            fixture_submission=fixture_root / "submission",
            evaluator=evaluator,
        ),
        aggregator=BestVerifiedAggregator(),
        config=MoARunConfig(
            run_root=(repo_root / args.run_root).resolve(),
            worker_count=args.workers,
            num_layers=args.layers,
            assimilation_mode=args.mode,
        ),
    )
    print(
        json.dumps(
            {
                "task_id": result.task_id,
                "layers": len(result.layers),
                "workers_per_layer": [len(layer) for layer in result.layers],
                "core": [
                    [
                        f"{output.verification.core_passed}/"
                        f"{output.verification.core_total}"
                        for output in layer
                    ]
                    for layer in result.layers
                ],
                "selected_workspace": result.answer,
            },
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
