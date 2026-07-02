from __future__ import annotations

import asyncio
import json
import os
import shutil

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .llm import LLMClient
from .maze_alpha import MazeMemoryAudit, run_maze_episode
from .maze_env import make_maze_tasks
from .memory import InsightMemory


def _cfg(**overrides):
    params = dict(
        api_key_env="SEC_MOCK_KEY",
        model="mock",
        base_url="http://mock.invalid/v1",
        n_solvers=2,
        memory_mode="none",
        maze_write_mode="none",
        T=1,
        batch_M=1,
        n_train=1,
        heldout_size=1,
        max_steps=4,
        retrieval_k=2,
        max_retries=1,
        cache_dir="./.sec_mock_cache/p0",
        out_dir="./.sec_mock_runs/p0",
    )
    params.update(overrides)
    return Config(**params)


# --- T0.1 cache salt -------------------------------------------------------


def _cache_key_checks() -> None:
    llm = LLMClient(_cfg())
    messages = [{"role": "user", "content": "hello"}]
    base = llm._key(model="m", messages=messages, temp=0.0, max_tokens=16)
    salted_a = llm._key(model="m", messages=messages, temp=0.0, max_tokens=16, cache_salt="A")
    salted_a2 = llm._key(model="m", messages=messages, temp=0.0, max_tokens=16, cache_salt="A")
    salted_b = llm._key(model="m", messages=messages, temp=0.0, max_tokens=16, cache_salt="B")
    assert salted_a == salted_a2, "same salt must give same key"
    assert salted_a != salted_b, "different salts must give different keys"
    assert base != salted_a, "salted key must differ from unsalted key"
    assert base == llm._key(model="m", messages=messages, temp=0.0, max_tokens=16, cache_salt="")
    print("p0 cache key checks OK")


class _RaisingCompletions:
    async def create(self, **kwargs):
        raise RuntimeError("network disabled in selftest")


class _RaisingChat:
    completions = _RaisingCompletions()


class _RaisingClient:
    chat = _RaisingChat()


async def _cache_salt_roundtrip_checks() -> None:
    cfg = _cfg(cache_dir="./.sec_mock_cache/p0_salt")
    shutil.rmtree(cfg.cache_dir, ignore_errors=True)
    llm = LLMClient(cfg)
    llm.client = _RaisingClient()  # type: ignore[assignment]
    messages = [{"role": "user", "content": "salted"}]
    key_a = llm._key(model=cfg.model, messages=messages, temp=0.0, max_tokens=None, cache_salt="A")
    record = {"response": {"content": "cached-A", "reasoning_content": None}, "usage": {}}
    (llm.cache_dir / f"{key_a}.json").write_text(json.dumps(record), encoding="utf-8")
    out = await llm.chat(messages, cache_salt="A")
    assert out == "cached-A", "salt A must hit the pre-written cache entry"
    hit_network = False
    try:
        await llm.chat(messages, cache_salt="B")
    except RuntimeError:
        hit_network = True
    assert hit_network, "salt B must miss the salt-A cache entry and reach the (disabled) network"
    print("p0 cache salt roundtrip checks OK")


async def _solver_salt_integration_checks() -> None:
    recorded: list[tuple[str, str]] = []

    async def _recording_chat(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        recorded.append((tag, cache_salt))
        user = messages[-1]["content"]
        if "Manhattan distance: 0" in user:
            return "At the goal. Action: submit"
        return "Explore. Action: move:right"

    original = LLMClient.chat
    LLMClient.chat = _recording_chat  # type: ignore[assignment]
    try:
        cfg = _cfg(n_solvers=2, max_steps=3)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="heldout", n=1, seed=5, width=9, height=9, family="benign")[0]
        for t in (0, 1):
            await run_maze_episode(task, memory, cfg, llm, audit=audit, t=t)
        solver_salts = [salt for tag, salt in recorded if tag.startswith("maze_agent")]
        assert solver_salts, "solver calls must be recorded"
        assert all(salt for salt in solver_salts), "every solver call must carry a cache salt"
        assert any("|t0|" in salt for salt in solver_salts), "round 0 salt missing"
        assert any("|t1|" in salt for salt in solver_salts), "round 1 salt missing"
        assert all(task.task_id in salt for salt in solver_salts), "task id must be in the salt"
        assert any("|a0|" in salt for salt in solver_salts) and any("|a1|" in salt for salt in solver_salts)
        assert len(set(solver_salts)) == len(solver_salts), "each solver step must get a unique salt"
        print("p0 solver salt integration checks OK:", len(solver_salts), "solver calls")
    finally:
        LLMClient.chat = original  # type: ignore[assignment]


def main() -> None:
    _cache_key_checks()
    asyncio.run(_cache_salt_roundtrip_checks())
    asyncio.run(_solver_salt_integration_checks())
    print("selftest_p0 OK")


if __name__ == "__main__":
    main()
