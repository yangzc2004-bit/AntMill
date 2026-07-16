from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .expel import distill_expel_insights, looks_over_specific, sanitize_expel_insight
from .llm import LLMClient
from .maze_alpha import (
    MAZE_EXPEL_ADAPTER,
    AgentRouteResult,
    MazeEpisodeResult,
    MazeMemoryAudit,
    _episode_route_diversity,
    _episode_route_diversity_efficient,
    maze_batch_metrics,
    memory_effective_size,
    retrieval_entropy_norm,
    retrieval_top1_share,
    run_maze_episode,
    write_maze_experience,
)
from .maze_env import make_maze_tasks
from .memory import InsightMemory
from .summarize_maze_alpha import (
    _mean_rows as _sum_mean_rows,
    _memory_rows as _sum_memory_rows,
    _rows as _sum_rows,
    _write_report as _sum_write_report,
)


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


# --- T0.3 mechanism metrics --------------------------------------------------


def _entropy_metric_checks() -> None:
    def items(counts):
        return [{"retrieval_count": c} for c in counts]

    assert retrieval_entropy_norm(items([10, 0, 0])) == 0.0, "single used item must have zero entropy"
    assert abs(retrieval_entropy_norm(items([5, 5, 5])) - 1.0) < 1e-9, "uniform spread must be 1.0"
    assert retrieval_entropy_norm(items([])) == 0.0
    assert retrieval_entropy_norm(items([7])) == 0.0, "one-item pool: the old max/total metric scored 1.0 here"
    assert retrieval_top1_share(items([7])) == 1.0  # documents exactly that pathology
    assert memory_effective_size(items([])) == 0.0
    assert abs(memory_effective_size(items([10])) - 1.0) < 1e-9
    assert abs(memory_effective_size(items([5, 5, 5])) - 3.0) < 1e-9
    mid = retrieval_entropy_norm(items([8, 2]))
    assert 0.0 < mid < 1.0
    print("p0 entropy metric checks OK")


def _retrieval_share_series_checks() -> None:
    audit = MazeMemoryAudit()
    item_a = {"id": "A", "kind": "do", "text": "a"}
    item_b = {"id": "B", "kind": "do", "text": "b"}
    for agent_id in range(4):
        audit.record_retrieval(t=0, task_id="x", agent_id=agent_id, items=[item_a])
    audit.record_retrieval(t=1, task_id="x", agent_id=0, items=[item_a])
    audit.record_retrieval(t=1, task_id="x", agent_id=1, items=[item_b])
    series = audit.retrieval_share_series()
    assert series["A"] == {"0": 1.0, "1": 0.5}, series
    assert series["B"] == {"1": 0.5}, series
    print("p0 retrieval share series checks OK")


def _mk_route(*, success: bool, path: list[tuple[int, int]], shortest: int = 10, looped: bool = False, cost: float | None = None):
    steps = max(len(path) - 1, 0)
    return {
        "success": success,
        "steps": steps,
        "shortest_path_length": shortest,
        "cost_ratio": cost if cost is not None else steps / shortest,
        "excess_steps": steps - shortest,
        "invalid_move_rate": 0.0,
        "revisit_max": 1,
        "looped": looped,
        "stagnation_rate": 0.0,
        "path": [list(p) for p in path],
    }


def _mk_episode(task, routes) -> MazeEpisodeResult:
    agents = [AgentRouteResult(agent_id=i, route=route, trace=[]) for i, route in enumerate(routes)]
    return MazeEpisodeResult(task_id=task.task_id, task=task, agents=agents)


def _diversity_and_batch_metric_checks() -> None:
    task = make_maze_tasks(split="heldout", n=1, seed=7, width=9, height=9, family="benign")[0]
    fast = [(1, 1), (2, 1), (3, 1), (4, 1)]
    wander = [(1, 1), (1, 2), (1, 3), (1, 2), (1, 3), (1, 2), (5, 5), (6, 5)]

    ep = _mk_episode(
        task,
        [
            _mk_route(success=True, path=fast, cost=1.2),
            _mk_route(success=True, path=fast, cost=1.2),
            _mk_route(success=True, path=wander, cost=5.0, looped=True),
        ],
    )
    efficient = _episode_route_diversity_efficient(ep)
    assert efficient == 0.0, f"identical efficient routes must be homogeneous, got {efficient}"
    assert _episode_route_diversity(ep) > 0.0, "the wandering route must inflate unconditional diversity"
    only_one = _mk_episode(task, [_mk_route(success=True, path=fast, cost=1.2), _mk_route(success=False, path=wander, cost=6.0)])
    assert _episode_route_diversity_efficient(only_one) is None, "fewer than 2 qualifying routes must yield None"

    # success-conditional efficiency separation: excess 5 and 15 succeed, excess 100 fails.
    shortest = 10
    ep2 = _mk_episode(
        task,
        [
            _mk_route(success=True, path=[(0, 0)] * (shortest + 5 + 1), shortest=shortest),
            _mk_route(success=True, path=[(0, 0)] * (shortest + 15 + 1), shortest=shortest),
            _mk_route(success=False, path=[(0, 0)] * (shortest + 100 + 1), shortest=shortest),
        ],
    )
    metrics = maze_batch_metrics([ep2])
    assert abs(metrics["success_excess_steps"] - 10.0) < 1e-9, metrics["success_excess_steps"]
    assert abs(metrics["failure_rate"] - 1.0 / 3.0) < 1e-9
    assert metrics["n_success"] == 2.0
    all_fail = _mk_episode(task, [_mk_route(success=False, path=wander, cost=6.0)])
    metrics_fail = maze_batch_metrics([all_fail])
    assert metrics_fail["success_excess_steps"] == 0.0 and metrics_fail["n_success"] == 0.0

    # ant-mill joint signature: majority looped AND overlapping routes.
    both_loop_same = _mk_episode(
        task,
        [_mk_route(success=False, path=wander, looped=True), _mk_route(success=False, path=wander, looped=True)],
    )
    disjoint = [(7, 7), (7, 8), (8, 8), (7, 8), (8, 8), (7, 8)]
    both_loop_disjoint = _mk_episode(
        task,
        [_mk_route(success=False, path=wander, looped=True), _mk_route(success=False, path=disjoint, looped=True)],
    )
    assert maze_batch_metrics([both_loop_same])["mas_antmill_rate"] == 1.0
    assert maze_batch_metrics([both_loop_disjoint])["mas_antmill_rate"] == 0.0
    print("p0 diversity and batch metric checks OK")


def _summarize_compat_checks() -> None:
    sample = Path("runs_maze_alpha_mas_shared_h3_t3_v1_v3_c4/n4_gt_false_seed0_maze_mad_shared_reviewer/result.json")
    if not sample.exists():
        print("p0 summarize compat checks SKIPPED (sample run not present)")
        return
    result = json.loads(sample.read_text(encoding="utf-8"))
    runs = {("shared_reviewer", "0"): result}
    rows = _sum_rows(runs)
    assert rows and all(row.get("success_rate") is not None for row in rows)
    assert all(row.get("retrieval_entropy_norm") is None for row in rows), "pre-P0 runs must degrade to None"
    mean_rows = _sum_mean_rows(rows)
    out = Path("./.sec_mock_runs/p0_summary")
    out.mkdir(parents=True, exist_ok=True)
    _sum_write_report(rows, mean_rows, _sum_memory_rows(runs), out)
    assert (out / "report.md").exists()
    assert "n/a" in (out / "report.md").read_text(encoding="utf-8"), "missing metrics must render as n/a"
    print("p0 summarize compat checks OK")


# --- T0.2 paired statistics --------------------------------------------------


def _mk_stats_result(*, extra_excess: float, fail_last: bool = False) -> dict:
    records = []
    for t in (0, 1):
        episodes = []
        for m in range(3):
            agents = []
            for a in range(2):
                excess = 4.0 + m + a + extra_excess
                steps = 10 + excess
                is_last = m == 2 and a == 1
                success = not (fail_last and is_last)
                agents.append(
                    {
                        "agent_id": a,
                        "route": {
                            "success": success,
                            "steps": steps,
                            "shortest_path_length": 10,
                            "cost_ratio": steps / 10.0,
                            "excess_steps": excess,
                            "looped": False,
                            "stagnation_rate": 0.1,
                            "revisit_max": 2,
                        },
                    }
                )
            episodes.append({"task_id": f"heldout_test_{m}", "agents": agents})
        records.append({"t": t, "episodes": episodes})
    return {"heldout_records": records}


def _paired_stats_checks() -> None:
    import random

    from .maze_stats import hierarchical_paired_diff, paired_diff, per_seed_paired_effects, per_seed_table, route_rows

    rows_a: list[dict] = []
    rows_b: list[dict] = []
    for seed in ("0", "1"):
        rows_a.extend(route_rows(_mk_stats_result(extra_excess=0.0), condition="A", seed=seed))
        rows_b.extend(route_rows(_mk_stats_result(extra_excess=10.0), condition="B", seed=seed))

    stat = paired_diff(rows_b, rows_a, "excess_steps", t=1)
    assert stat["n_pairs"] == 12, stat
    assert abs(stat["mean_diff"] - 10.0) < 1e-9, stat
    assert stat["ci_lo"] > 0.0 and stat["ci_excludes_zero"], "constant +10 effect must exclude zero"

    shuffled = list(rows_b)
    random.Random(1).shuffle(shuffled)
    stat_shuffled = paired_diff(shuffled, rows_a, "excess_steps", t=1)
    assert stat_shuffled == stat, "pairing must be order-invariant"

    b_key = ("1", 1, "heldout_test_2", 1)
    dropped_one = [
        row for row in rows_b
        if (row["seed"], row["t"], row["task_id"], row["agent_id"]) != b_key
    ]
    stat_dropped = paired_diff(dropped_one, rows_a, "excess_steps", t=1)
    assert stat_dropped["n_pairs"] == 11 and stat_dropped["n_dropped"] == 1, stat_dropped

    null_stat = paired_diff(rows_a, rows_a, "excess_steps", t=1)
    assert abs(null_stat["mean_diff"]) < 1e-12
    assert null_stat["ci_lo"] <= 0.0 <= null_stat["ci_hi"] and not null_stat["ci_excludes_zero"]

    # success_excess_steps: failed routes yield None and are dropped from the pairing.
    rows_b_fail = []
    for seed in ("0", "1"):
        rows_b_fail.extend(route_rows(_mk_stats_result(extra_excess=10.0, fail_last=True), condition="B", seed=seed))
    stat_fail = paired_diff(rows_b_fail, rows_a, "success_excess_steps", t=1)
    assert stat_fail["n_pairs"] == 10 and stat_fail["n_dropped"] == 2, stat_fail

    varied_b = []
    for seed in ("0", "1"):
        varied_b.extend(route_rows(_mk_stats_result(extra_excess=10.0 + int(seed) * 3), condition="B", seed=seed))
    first = paired_diff(varied_b, rows_a, "excess_steps", t=1, rng_seed=7)
    second = paired_diff(varied_b, rows_a, "excess_steps", t=1, rng_seed=7)
    assert first == second, "same rng_seed must reproduce identical CIs"

    clustered = hierarchical_paired_diff(varied_b, rows_a, "excess_steps", t=1, n_boot=500, rng_seed=7)
    clustered_repeat = hierarchical_paired_diff(varied_b, rows_a, "excess_steps", t=1, n_boot=500, rng_seed=7)
    assert clustered == clustered_repeat, "clustered bootstrap must be reproducible for a fixed seed"
    assert clustered["n_pairs"] == 12 and clustered["n_seeds"] == 2, clustered
    assert abs(clustered["mean_diff"] - 11.5) < 1e-9 and clustered["ci_lo"] > 0.0, clustered

    seed_effects = per_seed_paired_effects(varied_b, rows_a, ["excess_steps"], t=1)
    assert [(row["seed"], row["mean_diff"]) for row in seed_effects] == [("0", 10.0), ("1", 13.0)]

    seed_table = per_seed_table(rows_a + rows_b)
    assert {(row["condition"], row["seed"]) for row in seed_table} == {("A", "0"), ("A", "1"), ("B", "0"), ("B", "1")}
    assert all(row["n_routes"] == 6 for row in seed_table)
    print("p0 paired stats checks OK")


def _maze_stats_cli_checks() -> None:
    from .maze_stats import DEFAULT_RUNS, main as stats_main

    if not all(Path(path).exists() for path in DEFAULT_RUNS.values()):
        print("p0 maze_stats CLI checks SKIPPED (default runs not present)")
        return
    out = Path("./.sec_mock_runs/p0_stats")
    shutil.rmtree(out, ignore_errors=True)
    stats_main(["--out-dir", str(out), "--baseline", "frozen", "--n-boot", "500"])
    for name in ("paired_stats.csv", "per_seed.csv", "per_seed_paired_effects.csv", "stats_report.md"):
        assert (out / name).exists(), f"missing {name}"
    report = (out / "stats_report.md").read_text(encoding="utf-8")
    assert "shared_reviewer" in report and "Per-Seed Means" in report
    print("p0 maze_stats CLI checks OK")


# --- T0.5 honest naming -------------------------------------------------------


def _naming_config_checks() -> None:
    legacy = _cfg(maze_write_mode="direct")
    assert legacy.maze_write_mode == "scripted", legacy.maze_write_mode
    assert any("deprecated" in note for note in legacy.notes)
    legacy_oracle = _cfg(maze_write_mode="oracle")
    assert legacy_oracle.maze_write_mode == "scripted_gated"
    canonical = _cfg(maze_write_mode="scripted_gated")
    assert canonical.maze_write_mode == "scripted_gated" and not canonical.notes
    raised = False
    try:
        _cfg(maze_write_mode="bogus")
    except ValueError:
        raised = True
    assert raised, "invalid maze_write_mode must still raise"
    print("p0 naming config checks OK")


def _naming_arm_checks() -> None:
    from .maze_alpha import _arms_for_phase

    canonical_modes = {"reviewer", "scripted", "scripted_gated", "self_eval", "none"}
    for phase in ("debug", "smoke", "single", "single_expel_pilot", "mas_nomem", "core"):
        for arm in _arms_for_phase(phase):
            assert "mad" not in str(arm.get("run_id", "")), f"run_id still says mad: {arm}"
            assert arm.get("maze_write_mode") in canonical_modes, arm
    assert _arms_for_phase("mad") == _arms_for_phase("mas_nomem"), "'mad' must alias 'mas_nomem'"
    print("p0 naming arm checks OK")


async def _scripted_e2e_checks() -> None:
    async def _mock(self, messages, *, temp=0.0, model=None, max_tokens=None, tag="", cache_salt=""):
        user = messages[-1]["content"]
        if "Manhattan distance: 0" in user:
            return "At the goal. Action: submit"
        return "Explore. Action: move:right"

    original = LLMClient.chat
    LLMClient.chat = _mock  # type: ignore[assignment]
    try:
        cfg = _cfg(memory_mode="shared", maze_write_mode="scripted", n_solvers=2, max_steps=3)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="train", n=1, seed=8, width=9, height=9, family="benign")[0]
        episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=0, write_mode=cfg.maze_write_mode)
        assert memory.size() > 0, "scripted write mode must still populate the pool"
        assert all(w["write_mode"] == "scripted" for w in audit.writes)
        # legacy name routed through the same canonical branch
        await write_maze_experience(episode, memory, cfg, llm, audit=audit, t=1, write_mode="direct")
        assert all(w["write_mode"] in {"scripted"} for w in audit.writes)
    finally:
        LLMClient.chat = original  # type: ignore[assignment]
    print("p0 scripted e2e checks OK")


def _doc_naming_checks() -> None:
    allowed_markers = ("historical", "historically", "旧称", "deprecated", "labeled")
    for name in ("README.md", "maze_strategy_degradation_blueprint.md"):
        path = Path(name)
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "MAD" in line:
                assert any(marker in line for marker in allowed_markers), (
                    f"{name}:{i} mentions MAD outside a historical-note context: {line!r}"
                )
    print("p0 doc naming checks OK")


def main() -> None:
    _cache_key_checks()
    asyncio.run(_cache_salt_roundtrip_checks())
    asyncio.run(_solver_salt_integration_checks())
    _sanitizer_rule_checks()
    asyncio.run(_distill_reject_checks())
    asyncio.run(_write_experience_reject_checks())
    _entropy_metric_checks()
    _retrieval_share_series_checks()
    _diversity_and_batch_metric_checks()
    _summarize_compat_checks()
    _paired_stats_checks()
    _maze_stats_cli_checks()
    _naming_config_checks()
    _naming_arm_checks()
    asyncio.run(_scripted_e2e_checks())
    _doc_naming_checks()
    print("selftest_p0 OK")


if __name__ == "__main__":
    main()
