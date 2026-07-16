from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from .config import condition_name
from .miniwob_gamma import validate_frozen_browser_runtime, validate_miniwob_tasks
from .miniwob_runner import (
    _parser as p3_parser,
    build_configs,
    run_one_miniwob_gamma,
)


TARGET_CONDITION = (
    "n4_gt_false_seed2_gamma_p3_choose_list_shared_consolidated_expel"
)


def _formal_args(*, family: str, seed: int) -> list[str]:
    return [
        "--tasks",
        family,
        "--model",
        "DeepSeek-V3",
        "--base-url",
        "https://api.modelarts-maas.com/v2",
        "--api-key-env",
        "MODELARTS_MAAS_KEY",
        "--max-steps",
        "15",
        "--episode-concurrency",
        "1",
        "--max-tokens-solver",
        "256",
        "--max-tokens-reviewer",
        "512",
        "--phase",
        "gamma_p3_formal",
        "--out-dir",
        "runs_miniwob_gamma_p3e",
        "--cache-dir",
        "cache_miniwob_gamma_p3e",
        "--cache-policy",
        "read_write",
        "--seeds",
        str(seed),
        "--T",
        "4",
        "--heldout-size",
        "12",
        "--train-size",
        "16",
        "--train-batch",
        "4",
        "--concurrency",
        "4",
        "--skip-final-train",
    ]


def target_config(
    *,
    family: str = "choose-list",
    seed: int = 2,
    arm: str = "consolidated",
) -> tuple[Any, str, argparse.Namespace]:
    args = p3_parser().parse_args(_formal_args(family=family, seed=seed))
    matches = [
        (cfg, config_family)
        for cfg, config_family in build_configs(args)
        if config_family == family
        and cfg.seed == seed
        and cfg.notes == [arm]
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one P3 recovery target, found {len(matches)}."
        )
    cfg, family = matches[0]
    return cfg, family, args


async def _run(*, family: str, seed: int, arm: str) -> Path:
    runtime = validate_frozen_browser_runtime()
    if not runtime.get("ok"):
        raise RuntimeError(f"Frozen browser runtime validation failed: {runtime}")
    task_validation = validate_miniwob_tasks(runtime_manifest=runtime["actual"])
    if not task_validation.get("ok"):
        raise RuntimeError(
            f"MiniWoB task validation failed before recovery: {task_validation}"
        )

    cfg, family, args = target_config(
        family=family,
        seed=seed,
        arm=arm,
    )
    result_path = cfg.output_path() / condition_name(cfg) / "result.json"
    if result_path.exists():
        raise RuntimeError(
            f"Refusing to overwrite completed P3 target: {result_path}"
        )
    await run_one_miniwob_gamma(
        cfg,
        family=family,
        phase=args.phase,
        episode_concurrency=args.episode_concurrency,
    )

    final_runtime = validate_frozen_browser_runtime()
    if not final_runtime.get("ok"):
        raise RuntimeError(
            f"Frozen browser runtime changed during recovery: {final_runtime}"
        )
    return result_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run exactly one not-yet-completed P3e formal condition."
    )
    parser.add_argument("--family", default="choose-list")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument(
        "--arm",
        choices=["frozen", "append", "consolidated"],
        default="consolidated",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    result_path = asyncio.run(
        _run(
            family=args.family,
            seed=args.seed,
            arm=args.arm,
        )
    )
    print(f"p3_recovery_target_complete={result_path}")


if __name__ == "__main__":
    main()
