from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from sec.run_scbench_moa_curve import layer_rows, run_arm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run frozen SCBench checkpoint candidate probes in parallel."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=int, default=1200)
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_path = (repo_root / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        config.get("status")
        != "engineering_parallel_candidate_screen_frozen_before_outcomes"
    ):
        raise RuntimeError("Candidate screen config is not frozen")
    run_root = (repo_root / args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    async def run_candidate(raw_candidate: object) -> dict[str, object]:
        candidate = dict(raw_candidate)  # type: ignore[arg-type]
        problem = str(candidate["problem"])
        pilot = {
            **config,
            "problem": problem,
            "model": str(config["model"]),
        }
        try:
            arm_id, result = await run_arm(
                repo_root=repo_root,
                run_root=run_root,
                pilot=pilot,
                mode="no_transfer",
                timeout_sec=args.timeout_sec,
            )
            row = layer_rows("no_transfer", arm_id, result)[0]
            return {
                "problem": problem,
                "reason": str(candidate["reason"]),
                "arm_id": arm_id,
                "status": "completed",
                **row,
            }
        except Exception as exc:
            return {
                "problem": problem,
                "reason": str(candidate["reason"]),
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

    results = await asyncio.gather(
        *[
            run_candidate(candidate)
            for candidate in config["candidates"]
        ]
    )
    report = {
        "screen_config": config,
        "config_path": str(config_path),
        "results": results,
    }
    (run_root / "candidate_screen_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    completed = [
        result for result in results if result["status"] == "completed"
    ]
    if completed:
        fieldnames = list(completed[0])
        with (run_root / "candidate_screen_report.csv").open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(completed)
    print(json.dumps(report, indent=2), flush=True)


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
