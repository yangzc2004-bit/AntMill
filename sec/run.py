from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .config import Config, condition_name, mini_config
from .calibration import calibration_candidates, run_calibration
from .data import load_hotpotqa
from .loop import run_one
from .plotting import plot_compare, plot_condition
from .report import write_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run SEC HotpotQA experiments.")
    parser.add_argument("--tiny", action="store_true", help="Run a tiny rate-limit-safe smoke condition.")
    parser.add_argument("--tiny-all", action="store_true", help="Run tiny N=1 and N=4 conditions.")
    parser.add_argument("--mini", action="store_true", help="Run only the mini smoke condition.")
    parser.add_argument("--mini-all", action="store_true", help="Run mini N=1 and N=4 conditions.")
    parser.add_argument("--full", action="store_true", help="Run full default smoke after mini.")
    parser.add_argument("--with-ground-truth", action="store_true", help="Also run N=4 GT=True comparison.")
    parser.add_argument("--calibrate", action="store_true", help="Run A0 calibration grid and stop.")
    parser.add_argument("--gt-control", action="store_true", help="Run N=4 GT=False and GT=True control only.")
    parser.add_argument("--n-solvers", type=int, default=None, help="Run one full condition with this solver count.")
    parser.add_argument("--out-dir", default="./runs")
    parser.add_argument("--cache-dir", default="./cache")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--rpm", type=float, default=0.0, help="Optional client-side request-per-minute limit.")
    parser.add_argument("--no-context", action="store_true", help="Disable HotpotQA context injection.")
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--max-tokens-solver", type=int, default=None)
    parser.add_argument("--max-tokens-reviewer", type=int, default=None)
    parser.add_argument("--max-tokens-self-eval", type=int, default=None)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    return parser


def _common_params(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": args.model,
        "base_url": args.base_url,
        "api_key_env": args.api_key_env,
        "out_dir": args.out_dir,
        "cache_dir": args.cache_dir,
        "seed": args.seed,
        "concurrency": args.concurrency,
        "rate_limit_per_min": args.rpm,
        "use_context": not args.no_context,
        "max_context_chars": args.max_context_chars,
    }
    if args.max_tokens_solver is not None:
        params["max_tokens_solver"] = args.max_tokens_solver
    if args.max_tokens_reviewer is not None:
        params["max_tokens_reviewer"] = args.max_tokens_reviewer
    if args.max_tokens_self_eval is not None:
        params["max_tokens_self_eval"] = args.max_tokens_self_eval
    return params


def _make_cfg(args: argparse.Namespace, **overrides: Any) -> Config:
    params = _common_params(args)
    params.update(overrides)
    return Config(**params)


async def _run_configs(configs: list[Config]) -> list[dict[str, Any]]:
    max_train = max(int(cfg.n_train or 0) for cfg in configs)
    max_heldout = max(cfg.heldout_size for cfg in configs)
    seed = configs[0].seed
    print(f"Loading HotpotQA validation split: train={max_train}, heldout={max_heldout}, seed={seed}", flush=True)
    train_pool, heldout = load_hotpotqa(max_train, max_heldout, seed)
    results: list[dict[str, Any]] = []
    for cfg in configs:
        print(f"Running {condition_name(cfg)}", flush=True)
        result = await run_one(cfg, train_pool[: int(cfg.n_train or 0)], heldout[: cfg.heldout_size])
        result_dir = Path(cfg.out_dir) / condition_name(cfg)
        plot_condition(result, result_dir)
        results.append(result)
    out_dir = Path(configs[0].out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(results) > 1:
        plot_compare(results, out_dir)
    write_report(
        results,
        out_dir,
        notes=[
            f"Configured LLM endpoint: {configs[0].base_url}; model: {configs[0].model}. This overrides the original Qwen preregistration for this run.",
            "API key was read from an environment variable and is not serialized by the framework.",
        ],
    )
    (out_dir / "summary.json").write_text(
        json.dumps([result["summary"] for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results


def build_config_sequence(args: argparse.Namespace) -> list[Config]:
    if args.n_solvers is not None:
        return [_make_cfg(args, n_solvers=args.n_solvers, use_ground_truth=args.with_ground_truth, run_id="full")]

    if args.gt_control:
        return [
            _make_cfg(args, n_solvers=4, use_ground_truth=False, run_id="gt_control"),
            _make_cfg(args, n_solvers=4, use_ground_truth=True, run_id="gt_control"),
        ]

    if args.mini_all:
        shared = {
            **_common_params(args),
            "T": 3,
            "batch_M": 5,
            "heldout_size": 20,
            "n_train": 15,
            "use_ground_truth": False,
            "run_id": "mini_all",
        }
        return [
            Config(**shared, n_solvers=1),
            Config(**shared, n_solvers=4),
        ]

    if args.tiny_all:
        shared = {
            **_common_params(args),
            "T": 1,
            "batch_M": 2,
            "heldout_size": 3,
            "n_train": 2,
            "use_ground_truth": False,
        }
        return [
            mini_config(**shared, n_solvers=1, run_id="tiny"),
            Config(**shared, n_solvers=4, run_id="tiny"),
        ]

    if args.tiny:
        return [
            mini_config(
                **_common_params(args),
                T=1,
                batch_M=2,
                heldout_size=3,
                n_train=2,
                run_id="tiny",
            )
        ]

    if args.mini and not args.full:
        return [
            mini_config(
                **_common_params(args),
            )
        ]

    configs = [] if args.full else [
        mini_config(
            **_common_params(args),
        )
    ]
    if args.full or not args.mini:
        configs.extend(
            [
                _make_cfg(args, n_solvers=1, use_ground_truth=False, run_id="full"),
                _make_cfg(args, n_solvers=4, use_ground_truth=False, run_id="full"),
            ]
        )
        if args.with_ground_truth:
            configs.append(_make_cfg(args, n_solvers=4, use_ground_truth=True, run_id="full_gt"))
    return configs


def main() -> None:
    args = _parser().parse_args()
    if args.calibrate:
        base = _common_params(args)
        payload = asyncio.run(run_calibration(calibration_candidates(base)))
        print("\ncondition,use_context,max_tokens,A0,C0,G0,trace_tokens,cache_hit_rate")
        for row in payload["rows"]:
            print(
                f"{row['condition']},{row['use_context']},{row['max_tokens_solver']},"
                f"{row['A0']:.3f},{row['C0']:.3f},{row['G0']:.3f},"
                f"{row['trace_total_tokens']},{row['llm']['cache_hit_rate']:.3f}"
            )
        if payload["selected"] is None:
            print("STOP_RULE: no calibration setting reached A0 in [0.25, 0.60].")
        else:
            print(f"SELECTED: {payload['selected']['condition']}")
        return
    configs = build_config_sequence(args)
    results = asyncio.run(_run_configs(configs))
    print("\ncondition,t*,A_peak,A_final,A_drop,total_tokens,cache_hit_rate")
    for result in results:
        summary = result["summary"]
        llm = summary["llm"]
        print(
            f"{summary['condition']},{summary['t_star']},{summary['A_peak']:.3f},"
            f"{summary['A_final']:.3f},{summary['A_drop']:.3f},"
            f"{llm.get('trace_total_tokens', llm['total_tokens'])},{llm['cache_hit_rate']:.3f}"
        )


if __name__ == "__main__":
    main()
