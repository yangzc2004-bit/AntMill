from __future__ import annotations

import argparse

from .maze_alpha import run_cli


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Phase Alpha MazeEval-style strategy-degradation experiments.")
    p.add_argument("--phase", choices=["debug", "smoke", "single", "single_expel_pilot", "mad", "core"], default="smoke")
    p.add_argument("--model", default="", help="OpenAI-compatible model id.")
    p.add_argument("--base-url", default="", help="OpenAI-compatible base URL.")
    p.add_argument("--api-key-env", default="", help="Environment variable holding the API key.")
    p.add_argument("--out-dir", default="./runs_maze_alpha")
    p.add_argument("--cache-dir", default="./cache_maze_alpha")
    p.add_argument("--run-id-filter", default="", help="Comma-separated run_id filter for expensive pilot runs.")
    p.add_argument("--seeds", default="0")
    p.add_argument("--T", type=int, default=3)
    p.add_argument("--train-size", type=int, default=30)
    p.add_argument("--train-batch", type=int, default=5)
    p.add_argument("--heldout-size", type=int, default=10)
    p.add_argument("--max-steps", type=int, default=24)
    p.add_argument("--debate-rounds", type=int, default=1)
    p.add_argument("--retrieval-k", type=int, default=6)
    p.add_argument("--library-cap", type=int, default=80)
    p.add_argument("--maze-width", type=int, default=9)
    p.add_argument("--maze-height", type=int, default=9)
    p.add_argument("--maze-family", default="trap", choices=["benign", "trap", "phase_shift"])
    p.add_argument("--maze-agent-mode", default="prompt_only", choices=["prompt_only", "state_guided", "stateful_dfs", "oracle_dfs"])
    p.add_argument("--maze-min-shortest", type=int, default=0)
    p.add_argument("--maze-max-shortest", type=int, default=0)
    p.add_argument("--solver-temp", type=float, default=0.7)
    p.add_argument("--max-tokens-solver", type=int, default=256)
    p.add_argument("--max-tokens-reviewer", type=int, default=512)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--rpm", type=float, default=0.0)
    p.add_argument("--skip-final-train", action="store_true", help="Skip train/write after the final eval round.")
    return p


def main() -> None:
    run_cli(_parser().parse_args())


if __name__ == "__main__":
    main()
