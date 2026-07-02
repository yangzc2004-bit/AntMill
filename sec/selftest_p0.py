from __future__ import annotations

import asyncio
import json
import os
import shutil

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .expel import distill_expel_insights, looks_over_specific, sanitize_expel_insight
from .llm import LLMClient
from .maze_alpha import MAZE_EXPEL_ADAPTER, MazeMemoryAudit, run_maze_episode, write_maze_experience
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


# --- T0.4 sanitizer tightening ---------------------------------------------


def _sanitizer_rule_checks() -> None:
    blocked = [
        "go down then left then up at the fork",
        "down, left",
        "move:up -> move:right when blocked",
        "In maze heldout_trap_200008 the exit is south",  # maze id rule (regression)
        "go to (16,21) and turn left",  # coordinate rule (regression)
        "repeat up down left right until free",  # raw-count rule (regression)
    ]
    allowed = [
        "prefer unvisited open directions",
        "choose between left and right by distance to the goal",
        "backtrack toward the most recent fork with an untried direction",
        "submit immediately once the goal is reached",
    ]
    for text in blocked:
        assert looks_over_specific(text), f"should be blocked: {text!r}"
    for text in allowed:
        assert not looks_over_specific(text), f"should pass: {text!r}"
    rejected = sanitize_expel_insight({"kind": "do", "text": "go down then left then up"})
    assert rejected == {}, "rejected insight must be an empty dict, not fallback text"
    assert sanitize_expel_insight({"kind": "do", "text": ""}) == {}
    kept = sanitize_expel_insight({"kind": "avoid", "text": "avoid repeating a failed correction"})
    assert kept["text"] and kept["kind"] == "avoid"
    print("p0 sanitizer rule checks OK")


async def _distill_reject_checks() -> None:
    mixed_json = (
        '[{"kind":"do","text":"Prefer unvisited open directions when progress stalls."},'
        '{"kind":"do","text":"Go down then left then up at the second fork."},'
        '{"kind":"avoid","text":"At (3,4) avoid moving left."},'
        '{"kind":"avoid","text":"Do not repeat a correction pattern after returning to the same cell."}]'
    )

    async def _mixed_chat(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        return mixed_json

    async def _all_bad_chat(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        return '[{"kind":"do","text":"Go down then left."},{"kind":"do","text":"Head to (2,3) first."}]'

    episodes = [{"episode_id": "e0", "agent_id": 0, "outcome": "success", "quality": {}, "trajectory": "step 0"}]
    cfg = _cfg()
    original = LLMClient.chat
    try:
        LLMClient.chat = _mixed_chat  # type: ignore[assignment]
        rejects: list[dict[str, str]] = []
        insights = await distill_expel_insights(episodes, MAZE_EXPEL_ADAPTER, cfg, LLMClient(cfg), reject_log=rejects)
        assert len(insights) == 2, f"expected 2 surviving insights, got {insights}"
        assert all(not looks_over_specific(i["text"]) for i in insights)
        assert len(rejects) == 2 and all(r["reason"] == "over_specific" for r in rejects)

        LLMClient.chat = _all_bad_chat  # type: ignore[assignment]
        rejects = []
        insights = await distill_expel_insights(episodes, MAZE_EXPEL_ADAPTER, cfg, LLMClient(cfg), reject_log=rejects)
        assert insights == [], "all-rejected batch must yield an empty list, not a fallback insight"
        assert len(rejects) == 2
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("p0 distill reject checks OK")


async def _write_experience_reject_checks() -> None:
    async def _mock(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        if tag == "expel_reviewer":
            return '[{"kind":"do","text":"At (1,1) go down then left then up."}]'
        user = messages[-1]["content"]
        if "Manhattan distance: 0" in user:
            return "At the goal. Action: submit"
        return "Explore. Action: move:right"

    original = LLMClient.chat
    LLMClient.chat = _mock  # type: ignore[assignment]
    try:
        cfg = _cfg(memory_mode="shared", maze_write_mode="reviewer", n_solvers=2, max_steps=3)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="train", n=1, seed=6, width=9, height=9, family="benign")[0]
        episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=0, write_mode="reviewer")
        assert memory.size() == 0, "over-specific reviewer insight must not enter the pool"
        assert audit.rejections, "rejection must be recorded in the audit"
        public = audit.public(memory)
        assert public["sanitizer_rejects"] and public["sanitizer_reject_rate"] > 0.0
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("p0 write-experience reject checks OK")


def main() -> None:
    _cache_key_checks()
    asyncio.run(_cache_salt_roundtrip_checks())
    asyncio.run(_solver_salt_integration_checks())
    _sanitizer_rule_checks()
    asyncio.run(_distill_reject_checks())
    asyncio.run(_write_experience_reject_checks())
    print("selftest_p0 OK")


if __name__ == "__main__":
    main()
