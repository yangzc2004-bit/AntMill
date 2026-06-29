from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .config import Config, condition_name
from .data import load_hotpotqa
from .loop_v2 import run_one_v2
from .phases import build_phase


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run SEC v2 (MAD + memory) pre-registered phases.")
    p.add_argument("--phase", choices=["A0", "A1", "P0"], required=True)
    p.add_argument("--model", default="", help="LLM model id (user-specified; left blank by default).")
    p.add_argument("--base-url", default="", help="OpenAI-compatible base URL (user-specified).")
    p.add_argument("--api-key-env", default="", help="Env var holding the API key (user-specified).")
    p.add_argument("--out-dir", default="./runs_v2")
    p.add_argument("--cache-dir", default="./cache_v2")
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--rpm", type=float, default=0.0)
    p.add_argument("--heldout-size", type=int, default=None, help="Override held-out size (smoke/budget).")
    p.add_argument("--T", type=int, default=None, help="Override number of rounds (smoke/budget).")
    return p


def _common(args: argparse.Namespace) -> dict[str, Any]:
    common: dict[str, Any] = {
        "out_dir": args.out_dir,
        "cache_dir": args.cache_dir,
        "concurrency": args.concurrency,
        "rate_limit_per_min": args.rpm,
    }
    if args.model:
        common["model"] = args.model
    if args.base_url:
        common["base_url"] = args.base_url
    if args.api_key_env:
        common["api_key_env"] = args.api_key_env
    return common


async def _run(configs: list[Config]) -> list[dict[str, Any]]:
    max_train = max(int(c.n_train or 0) for c in configs)
    max_heldout = max(c.heldout_size for c in configs)
    seed = configs[0].seed
    print(f"Loading HotpotQA: train={max_train}, heldout={max_heldout}, seed={seed}", flush=True)
    train_pool, heldout = load_hotpotqa(max_train, max_heldout, seed)
    results: list[dict[str, Any]] = []
    for cfg in configs:
        # reload per-seed split when the seed changes
        if cfg.seed != seed:
            seed = cfg.seed
            train_pool, heldout = load_hotpotqa(max_train, max_heldout, seed)
        print(f"Running {condition_name(cfg)}", flush=True)
        result = await run_one_v2(cfg, train_pool[: int(cfg.n_train or 0)], heldout[: cfg.heldout_size])
        results.append(result)
    return results


def main() -> None:
    args = _parser().parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    overrides: dict[str, Any] = {}
    if args.heldout_size is not None:
        overrides["heldout_size"] = args.heldout_size
    if args.T is not None:
        overrides["T"] = args.T
    configs = build_phase(args.phase, _common(args), seeds, **overrides)
    results = asyncio.run(_run(configs))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = [r["summary"] for r in results]
    (out_dir / f"summary_{args.phase}.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\ncondition,A_final,A_peak,A_drop,C_final,D_first,D_final,t_star,collapsed,tokens")
    for s in summaries:
        col = s["collapse"]
        llm = s["llm"]
        print(
            f"{s['condition']},{s['A_final']:.3f},{s['A_peak']:.3f},{s['A_drop']:.3f},"
            f"{s['C_final']:.3f},{s['D_first']:.3f},{s['D_final']:.3f},{s['t_star']},"
            f"{col['collapsed_within_run']},{llm.get('trace_total_tokens', llm['total_tokens'])}"
        )


if __name__ == "__main__":
    main()
