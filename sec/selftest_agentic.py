from __future__ import annotations

import asyncio
import os
import re

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .agentic import aggregate_action, episode_batch_metrics, parse_action, run_episode
from .config import Config
from .llm import LLMClient
from .memory import InsightMemory
from .mock_env import MockToolEnv, make_tasks


async def _mock_chat(self, messages, *, temp=0.0, model=None, max_tokens=None, tag=""):
    user = messages[-1]["content"]
    if "MODE:loop" in user:
        return "I should look again. Action: read"
    target = (re.search(r"enable feature (\w+)", user) or [None, "F0"])[1]
    flags = (re.search(r"State flags: \[(.*?)\]", user) or [None, ""])[1]
    if target in flags:
        return "It is set now. Action: submit"
    return f"Enable it. Action: set:{target}"


def _cfg(**overrides):
    params = dict(
        api_key_env="SEC_MOCK_KEY",
        n_solvers=3,
        debate_rounds=2,
        memory_mode="none",
        max_steps=6,
        loop_window=3,
        max_tokens_solver=64,
        T=1,
        batch_M=0,
        n_train=0,
        heldout_size=4,
        cache_dir="./.sec_mock_cache",
        out_dir="./.sec_mock_runs",
    )
    params.update(overrides)
    return Config(**params)


def _pure_checks() -> None:
    assert parse_action("Reasoning here.\nAction: set:F1") == "set:F1"
    assert parse_action("no marker, last line wins") == "no marker, last line wins"
    act, frac = aggregate_action(["set:F1", "set:F1", "submit"])
    assert act == "set:F1" and abs(frac - 2 / 3) < 1e-9
    print("agentic pure checks OK")


async def _episode_checks() -> None:
    cfg = _cfg()
    original = LLMClient.chat
    LLMClient.chat = _mock_chat  # type: ignore[assignment]
    try:
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        results = []
        for task in make_tasks(n_solve=3, n_loop=2):
            results.append(await run_episode(task, MockToolEnv(), memory, cfg, llm))

        solves = [r for r in results if r.task_id.startswith("solve")]
        loops = [r for r in results if r.task_id.startswith("loop")]
        assert all(r.success and r.terminated and not r.looped for r in solves), [r.public() for r in solves]
        assert all((not r.success) and (not r.terminated) and r.looped for r in loops), [r.public() for r in loops]

        m = episode_batch_metrics(results)
        assert abs(m["A_t"] - 0.6) < 1e-9, m            # 3/5 solved
        assert abs(m["loop_rate"] - 0.4) < 1e-9, m      # 2/5 silently looped
        assert abs(m["nonterm_rate"] - 0.4) < 1e-9, m   # 2/5 never terminated
        assert abs(m["C_t"] - 1.0) < 1e-9, m            # agents agree each step (mock)
        print("agentic episode checks OK:", {k: round(v, 3) for k, v in m.items()})
    finally:
        LLMClient.chat = original  # type: ignore[assignment]


def main() -> None:
    _pure_checks()
    asyncio.run(_episode_checks())
    print("selftest_agentic OK")


if __name__ == "__main__":
    main()
