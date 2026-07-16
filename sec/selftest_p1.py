from __future__ import annotations

import asyncio
import os
import re

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .expel_ops import ADD_INITIAL_VOTES, apply_memory_ops, parse_memory_ops, render_ops_pool
from .llm import LLMClient
from .maze_alpha import MazeMemoryAudit, _agent_query, run_maze_episode, write_maze_experience
from .maze_env import make_maze_tasks
from .memory import InsightMemory
from .metrics import embedding_similarity, stable_hashing_embedding


def _cfg(**overrides):
    params = dict(
        api_key_env="SEC_MOCK_KEY",
        model="mock",
        base_url="http://mock.invalid/v1",
        n_solvers=2,
        memory_mode="shared",
        maze_write_mode="reviewer",
        T=1,
        batch_M=1,
        n_train=1,
        heldout_size=1,
        max_steps=4,
        retrieval_k=2,
        max_retries=1,
        cache_dir="./.sec_mock_cache/p1",
        out_dir="./.sec_mock_runs/p1",
    )
    params.update(overrides)
    return Config(**params)


# --- T1.2 task-conditioned retrieval query -----------------------------------


def _query_checks() -> None:
    tasks = make_maze_tasks(split="heldout", n=6, seed=11, width=9, height=9, family="trap")
    queries = [_agent_query(task) for task in tasks]
    assert len(set(queries)) >= 2, f"queries must vary across tasks, got {set(queries)}"
    for query in queries:
        assert re.search(r"\(\s*\d+\s*,\s*\d+\s*\)", query) is None, "no raw coordinates in the query"
        assert "shortest" not in query and "#" not in query, "no hidden info in the query"
        assert "family trap" in query and "size 9x9" in query
        assert "goal bearing" in query and "start manhattan" in query and "start open" in query
    print("p1 query checks OK")


def _embedding_checks() -> None:
    a = stable_hashing_embedding("prefer unvisited open directions")
    b = stable_hashing_embedding("prefer unvisited open directions")
    assert (a == b).all(), "stable embedding must be deterministic"
    assert abs(embedding_similarity("goal east corridor", "goal east corridor") - 1.0) < 1e-9
    assert embedding_similarity("alpha beta", "gamma delta") == 0.0
    mid = embedding_similarity("maze goal east", "maze goal west")
    assert 0.0 < mid < 1.0
    print("p1 embedding checks OK")


def _query_conditioned_retrieval_checks() -> None:
    cfg = _cfg(retrieval_scoring="ga", ga_lambda=0.0, ga_recency=0.0, retrieval_k=1)
    memory = InsightMemory(cfg)
    east = {"kind": "do", "text": "when the goal bearing is east follow east side corridors", "votes": 0}
    west = {"kind": "do", "text": "when the goal bearing is west follow west side corridors", "votes": 0}
    memory.shared = [east, west]
    got_east = memory.retrieve(0, "maze goal navigation goal bearing east south start open down right")
    got_west = memory.retrieve(0, "maze goal navigation goal bearing west north start open up left")
    assert got_east[0] is east, got_east
    assert got_west[0] is west, got_west
    print("p1 query-conditioned retrieval checks OK")


# --- T1.3 GA scoring ----------------------------------------------------------


def _ga_scoring_checks() -> None:
    relevant = {"kind": "do", "text": "prefer the east corridor when navigating toward the goal", "votes": 0}
    popular = {"kind": "do", "text": "explore the maze goal region carefully", "votes": 20}
    filler = {"kind": "do", "text": "unrelated bookkeeping note", "votes": 0}
    query = "maze goal navigation east corridor"

    cfg0 = _cfg(retrieval_scoring="ga", ga_lambda=0.0, ga_recency=0.0, retrieval_k=1)
    mem0 = InsightMemory(cfg0)
    mem0.shared = [popular, relevant, filler]
    assert mem0.retrieve(0, query)[0] is relevant, "lambda=0 must rank by relevance only"

    cfg1 = _cfg(retrieval_scoring="ga", ga_lambda=1.0, ga_recency=0.0, retrieval_k=1)
    mem1 = InsightMemory(cfg1)
    mem1.shared = [popular, relevant, filler]
    assert mem1.retrieve(0, query)[0] is popular, "high votes must win under lambda=1"

    # recency channel: equal relevance and votes, recently accessed item wins.
    old = {"kind": "do", "text": "unrelated lesson alpha", "votes": 0}
    fresh = {"kind": "do", "text": "unrelated lesson beta", "votes": 0, "last_access_t": 5}
    cfg_rec = _cfg(retrieval_scoring="ga", ga_lambda=0.0, ga_recency=1.0, retrieval_k=1)
    mem_rec = InsightMemory(cfg_rec)
    mem_rec.shared = [old, fresh]
    got = mem_rec.retrieve(0, "zzz nothing overlaps")
    assert got[0] is fresh, "recency weight must prefer the recently accessed item"

    # usage feedback: retrieval stamps last_access_t on selected items only.
    selected = mem_rec.retrieve(0, "zzz nothing overlaps", t=7)
    assert selected[0]["last_access_t"] == 7
    assert "last_access_t" not in old, "unselected items must not be refreshed"

    # determinism and single-item pool edge case
    assert mem1.retrieve(0, query) == mem1.retrieve(0, query)
    solo = InsightMemory(cfg1)
    solo.shared = [dict(relevant)]
    assert len(solo.retrieve(0, query)) == 1
    print("p1 GA scoring checks OK")


def _legacy_scoring_regression_checks() -> None:
    cfg = _cfg(retrieval_scoring="similarity", retrieval_k=1)
    memory = InsightMemory(cfg)
    relevant = {"kind": "do", "text": "prefer the east corridor when navigating toward the goal", "votes": 0}
    popular = {"kind": "do", "text": "explore carefully", "votes": 50}
    memory.shared = [popular, relevant]
    got = memory.retrieve(0, "east corridor toward the goal")
    assert got[0] is relevant, "legacy similarity mode must ignore votes"
    print("p1 legacy scoring regression OK")


# --- T1.1 ExpeL LLM-issued operations ----------------------------------------


def _ops_parse_checks() -> None:
    text = (
        "Here are my operations:\n"
        '[{"op":"add","target_id":null,"kind":"do","text":"lesson one"},'
        '{"op":"UPVOTE","target_id":"2"},'
        '{"op":"NUKE","target_id":0,"text":"bad"},'
        '{"op":"EDIT","target_id":"x","kind":"avoid","text":"refined"},'
        '"not-a-dict"]'
    )
    ops = parse_memory_ops(text)
    assert [op["op"] for op in ops] == ["ADD", "UPVOTE", "EDIT"], ops
    assert ops[0]["target_id"] is None and ops[1]["target_id"] == 2 and ops[2]["target_id"] is None
    assert parse_memory_ops("no json here") == []
    many = "[" + ",".join('{"op":"UPVOTE","target_id":0}' for _ in range(10)) + "]"
    assert len(parse_memory_ops(many)) == 6, "ops must be capped per batch"
    print("p1 ops parse checks OK")


def _ops_apply_checks() -> None:
    cfg = _cfg()
    pool: list[dict] = []
    ops = [{"op": "ADD", "target_id": None, "kind": "do", "text": "prefer unvisited open directions when progress stalls"}]
    pool, applied = apply_memory_ops(pool, ops, cfg=cfg)
    assert len(pool) == 1 and pool[0]["votes"] == ADD_INITIAL_VOTES
    assert applied[0]["op"] == "ADD"

    # duplicate ADD converts to UPVOTE
    pool, applied = apply_memory_ops(
        pool,
        [{"op": "ADD", "target_id": None, "kind": "do", "text": "prefer unvisited open directions when progress stalls"}],
        cfg=cfg,
    )
    assert len(pool) == 1 and pool[0]["votes"] == ADD_INITIAL_VOTES + 1
    assert applied[0]["op"] == "UPVOTE" and applied[0].get("converted_from") == "ADD"

    # EDIT rewrites; over-specific EDIT is rejected and leaves the text intact
    rejects: list[dict] = []
    pool, applied = apply_memory_ops(
        pool,
        [
            {"op": "EDIT", "target_id": 0, "kind": "do", "text": "prefer untried open directions after a revisit"},
            {"op": "EDIT", "target_id": 0, "kind": "do", "text": "at (3,4) go down then left"},
        ],
        cfg=cfg,
        reject_log=rejects,
    )
    assert pool[0]["text"] == "prefer untried open directions after a revisit"
    assert len(rejects) == 1 and rejects[0]["reason"] == "over_specific" and rejects[0]["op"] == "EDIT"

    # DOWNVOTE to zero removes the item (ExpeL removal rule)
    votes_now = pool[0]["votes"]
    downs = [{"op": "DOWNVOTE", "target_id": 0} for _ in range(votes_now)]
    pool, _ = apply_memory_ops(pool, downs, cfg=cfg)
    assert pool == [], "votes reaching zero must remove the insight"

    # invalid target is rejected, not crashed
    rejects = []
    pool, applied = apply_memory_ops([], [{"op": "UPVOTE", "target_id": 3}], cfg=cfg, reject_log=rejects)
    assert applied == [] and rejects[0]["reason"] == "invalid_target"

    # library cap keeps the highest-voted items
    cap_cfg = _cfg(library_cap=2)
    base = [
        {"kind": "do", "text": "lesson alpha", "votes": 3},
        {"kind": "do", "text": "lesson beta", "votes": 1},
        {"kind": "do", "text": "lesson gamma", "votes": 2},
    ]
    pool, _ = apply_memory_ops(base, [], cfg=cap_cfg)
    assert [item["votes"] for item in pool] == [3, 2]

    # Amendment 01 tie rule evicts the oldest equal-vote item.
    recency_cfg = _cfg(library_cap=2, tie_rule="oldest_evicted_recency_retaining")
    tied = [
        {"kind": "do", "text": "oldest", "votes": 1, "insertion_order": 0},
        {"kind": "do", "text": "middle", "votes": 1, "insertion_order": 1},
        {"kind": "do", "text": "newest", "votes": 1, "insertion_order": 2},
    ]
    pool, _ = apply_memory_ops(tied, [], cfg=recency_cfg)
    assert [item["text"] for item in pool] == ["newest", "middle"], pool
    print("p1 ops apply checks OK")


async def _ops_e2e_checks() -> None:
    reviewer_calls = {"n": 0}

    async def _mock(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        user = messages[-1]["content"]
        if tag == "expel_ops_reviewer":
            reviewer_calls["n"] += 1
            assert temp == 0.2
            assert "EXISTING INSIGHT POOL" in user, "reviewer must see the pool"
            if reviewer_calls["n"] == 1:
                return (
                    '[{"op":"ADD","target_id":null,"kind":"do","text":"submit promptly after reaching the goal"},'
                    '{"op":"ADD","target_id":null,"kind":"avoid","text":"avoid repeating a failed correction pattern"}]'
                )
            return (
                '[{"op":"UPVOTE","target_id":0},'
                '{"op":"ADD","target_id":null,"kind":"do","text":"at (2,2) go down then left"}]'
            )
        if "Manhattan distance: 0" in user:
            return "At the goal. Action: submit"
        return "Explore. Action: move:right"

    original = LLMClient.chat
    LLMClient.chat = _mock  # type: ignore[assignment]
    try:
        cfg = _cfg(memory_write_protocol="expel_ops", n_solvers=2, max_steps=3)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="train", n=1, seed=12, width=9, height=9, family="benign")[0]
        episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=0, write_mode="reviewer")
        assert memory.size() == 2, memory.snapshot()
        assert all(item["votes"] == ADD_INITIAL_VOTES for item in memory.shared)

        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=1, write_mode="reviewer")
        assert memory.size() == 2, "over-specific ADD must be rejected, UPVOTE applied"
        assert max(item["votes"] for item in memory.shared) == ADD_INITIAL_VOTES + 1
        modes = {w["write_mode"] for w in audit.writes}
        assert "reviewer_ops:ADD" in modes and "reviewer_ops:UPVOTE" in modes, modes
        assert any(r["reason"] == "over_specific" for r in audit.rejections)
        assert all(item.get("sources") for item in memory.shared), "ops writes must carry provenance"
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("p1 ops e2e checks OK:", {"reviewer_calls": reviewer_calls["n"]})


def _render_pool_checks() -> None:
    assert render_ops_pool([]) == "(empty)"
    rendered = render_ops_pool([{"kind": "do", "text": "lesson", "votes": 2}])
    assert "[0]" in rendered and "votes=2" in rendered and "lesson" in rendered
    print("p1 render pool checks OK")


# --- P2 append protocol and preregistered phases ------------------------------


async def _append_protocol_checks() -> None:
    reviewer_temps: list[float] = []

    async def _mock(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        user = messages[-1]["content"]
        if tag == "expel_reviewer":
            reviewer_temps.append(float(temp))
            return '[{"kind":"do","text":"prefer untried open directions after a revisit"}]'
        if "Manhattan distance: 0" in user:
            return "At the goal. Action: submit"
        return "Explore. Action: move:right"

    original = LLMClient.chat
    LLMClient.chat = _mock  # type: ignore[assignment]
    try:
        cfg = _cfg(memory_write_protocol="append", n_solvers=2, max_steps=3)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="train", n=1, seed=13, width=9, height=9, family="benign")[0]
        episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=0, write_mode="reviewer")
        # Two agents independently derive the same lesson: one entry, agreement upvote.
        assert memory.size() == 1, memory.snapshot()
        assert memory.shared[0]["votes"] == 2, memory.shared
        modes = [w["write_mode"] for w in audit.writes]
        assert "reviewer_append:append" in modes and "reviewer_append:agree" in modes, modes
        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=1, write_mode="reviewer")
        assert memory.size() == 1 and memory.shared[0]["votes"] == 4, "agreement must keep accumulating"

        raw_cfg = _cfg(
            memory_write_protocol="append",
            append_dedup=False,
            tie_rule="oldest_evicted_recency_retaining",
            n_solvers=2,
            max_steps=3,
        )
        raw_llm = LLMClient(raw_cfg)
        raw_memory = InsightMemory(raw_cfg)
        raw_audit = MazeMemoryAudit()
        await write_maze_experience(
            episode,
            raw_memory,
            raw_cfg,
            raw_llm,
            audit=raw_audit,
            t=0,
            write_mode="reviewer",
        )
        assert raw_memory.size() == 2, raw_memory.snapshot()
        assert all(item["votes"] == 1 for item in raw_memory.shared)
        raw_modes = [write["write_mode"] for write in raw_audit.writes]
        assert "reviewer_append:agree" not in raw_modes, raw_modes
        assert raw_modes == ["reviewer_append_raw:append", "reviewer_append_raw:append"], raw_modes
        assert reviewer_temps and all(temp == 0.2 for temp in reviewer_temps), reviewer_temps
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("p1 append protocol checks OK")


def _prereg_phase_checks() -> None:
    from .maze_alpha import _arms_for_phase

    e1 = _arms_for_phase("e1_gate")
    assert [arm["run_id"] for arm in e1] == ["e1_single_nomem", "e1_single_reviewer_ops", "e1_single_reviewer_append"]
    assert all(arm["n_solvers"] == 1 for arm in e1)
    assert e1[1]["memory_write_protocol"] == "expel_ops" and e1[2]["memory_write_protocol"] == "append"
    assert all(arm.get("ga_lambda") == 0.0 for arm in e1[1:])

    e2 = _arms_for_phase("core_v2")
    assert len(e2) == 5 and all(arm["n_solvers"] == 4 for arm in e2)
    by_id = {arm["run_id"]: arm for arm in e2}
    assert by_id["e2_shared_append_ga"]["memory_write_protocol"] == "append"
    assert by_id["e2_shared_consolidated_expel"]["memory_write_protocol"] == "expel_ops"
    assert by_id["e2_frozen_reviewer"]["memory_mode"] == "frozen"
    assert by_id["e2_private_reviewer"]["memory_mode"] == "private"
    assert by_id["e2_mas_nomem"]["memory_mode"] == "none"

    e3 = _arms_for_phase("e3_lambda")
    assert [arm["ga_lambda"] for arm in e3] == [0.0, 0.5, 1.0]
    assert all(arm["memory_write_protocol"] == "append" and arm["memory_mode"] == "shared" for arm in e3)

    e4 = _arms_for_phase("e4_stress")
    e4_by_id = {arm["run_id"]: arm for arm in e4}
    assert set(e4_by_id) == {"e4_frozen_reviewer", "e4_shared_consolidated_expel", "e4_shared_append_lam1"}
    assert e4_by_id["e4_frozen_reviewer"]["memory_mode"] == "frozen"
    assert e4_by_id["e4_shared_consolidated_expel"]["memory_write_protocol"] == "expel_ops"
    assert e4_by_id["e4_shared_append_lam1"]["memory_write_protocol"] == "append"
    assert e4_by_id["e4_shared_append_lam1"]["ga_lambda"] == 1.0
    assert all(arm["n_solvers"] == 4 for arm in e4)

    # per-arm overrides must survive config construction
    from .maze_alpha import build_maze_alpha_configs
    from .run_maze_alpha import _parser

    args = _parser().parse_args(["--phase", "e3_lambda", "--api-key-env", "SEC_MOCK_KEY"])
    configs = build_maze_alpha_configs(args)
    assert sorted(c.ga_lambda for c in configs) == [0.0, 0.5, 1.0]
    assert all(c.memory_write_protocol == "append" and c.retrieval_scoring == "ga" for c in configs)
    print("p1 prereg phase checks OK")


def _cli_wiring_checks() -> None:
    from .maze_alpha import build_maze_alpha_configs
    from .run_maze_alpha import _parser

    args = _parser().parse_args(
        [
            "--phase", "core",
            "--write-protocol", "expel_ops",
            "--retrieval-scoring", "ga",
            "--ga-lambda", "0.5",
            "--ga-recency", "1.0",
            "--api-key-env", "SEC_MOCK_KEY",
        ]
    )
    configs = build_maze_alpha_configs(args)
    assert configs, "core phase must produce arms"
    for cfg in configs:
        assert cfg.memory_write_protocol == "expel_ops"
        assert cfg.retrieval_scoring == "ga"
        assert cfg.ga_lambda == 0.5 and cfg.ga_recency == 1.0
        assert cfg.reviewer_temp == 0.2
    defaults = build_maze_alpha_configs(_parser().parse_args(["--phase", "core", "--api-key-env", "SEC_MOCK_KEY"]))
    assert all(c.memory_write_protocol == "distill" and c.retrieval_scoring == "similarity" for c in defaults)
    print("p1 CLI wiring checks OK")


# --- infra resilience: content filter and degraded calls ----------------------


class _FilteredThenOkCompletions:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def create(self, *, model, messages, temperature, max_tokens):
        self.calls.append([dict(m) for m in messages])
        if len(self.calls) == 1:
            raise RuntimeError("Error code: 403 - ModelArts.81011 Output text May contain sensitive information")

        class _Msg:
            content = "Recovered. Action: inspect"
            reasoning_content = None

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]
            usage = None

        return _Resp()


async def _content_filter_retry_checks() -> None:
    import shutil

    from .llm import _is_content_filter_error, _perturb_messages

    assert _is_content_filter_error(RuntimeError("ModelArts.81011 blah"))
    assert _is_content_filter_error(RuntimeError("Output text May contain SENSITIVE information"))
    assert not _is_content_filter_error(RuntimeError("rate limit exceeded"))
    perturbed = _perturb_messages([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], 2)
    assert "[retry 2" in perturbed[1]["content"] and perturbed[0]["content"] == "s"

    cfg = _cfg(cache_dir="./.sec_mock_cache/p1_filter", max_retries=3)
    shutil.rmtree(cfg.cache_dir, ignore_errors=True)
    llm = LLMClient(cfg)
    fake = _FilteredThenOkCompletions()

    class _Chat:
        completions = fake

    class _Client:
        chat = _Chat()

    llm.client = _Client()  # type: ignore[assignment]
    messages = [{"role": "user", "content": "original prompt"}]
    out = await llm.chat(messages, tag="maze_agent:0", cache_salt="X")
    assert out == "Recovered. Action: inspect"
    assert len(fake.calls) == 2, "one filtered attempt plus one perturbed retry"
    assert fake.calls[0][-1]["content"] == "original prompt", "first attempt must be unperturbed"
    assert "[retry 2" in fake.calls[1][-1]["content"], "content-filter retry must perturb the request"
    assert llm.stats.content_filter_hits == 1
    out2 = await llm.chat(messages, tag="maze_agent:0", cache_salt="X")
    assert out2 == out and len(fake.calls) == 2, "result must be cached under the ORIGINAL key"
    print("p1 content filter retry checks OK")


async def _llm_error_resilience_checks() -> None:
    async def _always_fail(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        raise RuntimeError("LLM call failed after 6 attempts: 403 sensitive")

    async def _solver_ok(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        if tag.startswith("maze_agent"):
            return "Explore. Action: move:right"
        raise RuntimeError("LLM call failed after 6 attempts: 403 sensitive")

    original = LLMClient.chat
    try:
        # solver degradation: every step falls back to inspect, run survives
        LLMClient.chat = _always_fail  # type: ignore[assignment]
        cfg = _cfg(memory_mode="none", maze_write_mode="none", n_solvers=2, max_steps=3)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="heldout", n=1, seed=14, width=9, height=9, family="benign")[0]
        episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
        route = episode.agents[0].route
        assert route["llm_error_count"] == 3, route.get("llm_error_count")
        assert audit.llm_errors, "solver llm errors must be audited"
        from .maze_alpha import maze_batch_metrics as _mbm

        assert _mbm([episode])["llm_error_count"] == 6.0  # 2 agents x 3 steps

        # reviewer degradation: writes skipped, no crash, audit records the error
        LLMClient.chat = _solver_ok  # type: ignore[assignment]
        for protocol in ("distill", "expel_ops", "append"):
            cfg = _cfg(memory_write_protocol=protocol, n_solvers=2, max_steps=3)
            llm = LLMClient(cfg)
            memory = InsightMemory(cfg)
            audit = MazeMemoryAudit()
            episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
            await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=0, write_mode="reviewer")
            assert memory.size() == 0, f"{protocol}: failed reviewer must not write"
            assert audit.llm_errors, f"{protocol}: reviewer llm error must be audited"
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("p1 llm error resilience checks OK")


def main() -> None:
    _query_checks()
    _embedding_checks()
    _query_conditioned_retrieval_checks()
    _ga_scoring_checks()
    _legacy_scoring_regression_checks()
    _ops_parse_checks()
    _ops_apply_checks()
    _render_pool_checks()
    asyncio.run(_ops_e2e_checks())
    _cli_wiring_checks()
    asyncio.run(_append_protocol_checks())
    _prereg_phase_checks()
    asyncio.run(_content_filter_retry_checks())
    asyncio.run(_llm_error_resilience_checks())
    print("selftest_p1 OK")


if __name__ == "__main__":
    main()
