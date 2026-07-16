from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agentic import parse_action
from .config import Config, condition_name
from .expel import ExpeLAdapter, distill_expel_insights, sanitize_expel_insight
from .expel_ops import apply_memory_ops, find_pool_duplicate, propose_memory_ops
from .llm import LLMClient
from .maze_alpha import MazeMemoryAudit
from .memory import InsightMemory
from .metrics import normalize_answer
from .miniwob_gamma import (
    MINIWOB_ALL_PREREG_TASKS,
    MINIWOB_PRIMARY_TASKS,
    MINIWOB_REPLACEMENT_TASKS,
    MiniWoBEnv,
    action_bid_reference,
    browsergym_version_manifest,
    extract_bids,
    miniwob_state_hash,
    reviewer_episode_summary,
    validate_frozen_browser_runtime,
    validate_miniwob_tasks,
)
from .solver import render_library


MINIWOB_SOLVER_SYS = (
    "You are a browser agent completing a MiniWoB task. Use reusable experience as abstract guidance, "
    "not as a memorized action script. Read the goal, accessibility tree, tool documentation, and recent "
    "history. Output at most two short reasoning sentences and exactly one final line: "
    "Action: <one BrowserGym high-level action>."
)

MINIWOB_EXPEL_ADAPTER = ExpeLAdapter(
    task_family="MiniWoB web interaction tasks",
    trajectory_label="compact browser trajectory summary",
    forbidden_details=(
        "Do not mention task ids, URLs, DOM node ids, coordinates, literal form values, "
        "or fixed action sequences."
    ),
    strategy_focus=(
        "goal grounding, selecting controls from visible labels, form validation, error recovery, "
        "and detecting repeated browser states."
    ),
    fallback={
        "kind": "do",
        "text": "Ground each browser action in the current goal and visible controls, then verify the state change.",
    },
)
_BROWSER_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miniwob-browser")


@dataclass(frozen=True)
class MiniWoBTaskInstance:
    family: str
    split: str
    instance_index: int
    reset_seed: int

    @property
    def task_id(self) -> str:
        return f"{self.family}:{self.split}:seed{self.reset_seed}:instance{self.instance_index}"

    def public(self) -> dict[str, Any]:
        return {
            "task_name": self.family,
            "task_id": self.task_id,
            "split": self.split,
            "instance_index": self.instance_index,
            "seed": self.reset_seed,
        }


@dataclass
class MiniWoBAgentResult:
    agent_id: int
    route: dict[str, Any]
    trace: list[dict[str, Any]]
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    reviewer_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class MiniWoBEpisodeResult:
    task: MiniWoBTaskInstance
    agents: list[MiniWoBAgentResult]

    @property
    def task_id(self) -> str:
        return self.task.task_id

    def public(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task": self.task.public(),
            "agents": [
                {
                    "agent_id": agent.agent_id,
                    "route": agent.route,
                    "trace": agent.trace,
                    "retrieved": [
                        {"id": item.get("id"), "kind": item.get("kind", "do"), "text": item.get("text", "")}
                        for item in agent.retrieved
                    ],
                    "reviewer_summary": agent.reviewer_summary,
                }
                for agent in self.agents
            ],
        }


def _arms_for_phase(phase: str) -> list[dict[str, Any]]:
    base = {
        "n_solvers": 4,
        "maze_write_mode": "reviewer",
        "retrieval_scoring": "ga",
        "ga_lambda": 0.0,
        "retrieval_k": 6,
        "library_cap": 80,
    }
    if phase in {"gamma_p3_smoke", "gamma_p3_formal"}:
        return [
            {
                **base,
                "run_id_suffix": "frozen_reviewer",
                "arm": "frozen",
                "memory_mode": "frozen",
                "memory_write_protocol": "expel_ops",
            },
            {
                **base,
                "run_id_suffix": "shared_append_ga",
                "arm": "append",
                "memory_mode": "shared",
                "memory_write_protocol": "append",
            },
            {
                **base,
                "run_id_suffix": "shared_consolidated_expel",
                "arm": "consolidated",
                "memory_mode": "shared",
                "memory_write_protocol": "expel_ops",
            },
        ]
    raise ValueError(f"unknown MiniWoB phase {phase!r}")


def _task_seed(family: str, experiment_seed: int, *, split: str, index: int) -> int:
    family_index = MINIWOB_ALL_PREREG_TASKS.index(family)
    split_offset = 10_000 if split == "heldout" else 50_000
    return 1_000_000 + family_index * 100_000 + int(experiment_seed) * 1_000 + split_offset + int(index)


def heldout_tasks(family: str, cfg: Config) -> list[MiniWoBTaskInstance]:
    return [
        MiniWoBTaskInstance(
            family=family,
            split="heldout",
            instance_index=index,
            reset_seed=_task_seed(family, cfg.seed, split="heldout", index=index),
        )
        for index in range(cfg.heldout_size)
    ]


def train_tasks(family: str, cfg: Config) -> list[MiniWoBTaskInstance]:
    return [
        MiniWoBTaskInstance(
            family=family,
            split="train",
            instance_index=index,
            reset_seed=_task_seed(family, cfg.seed, split="train", index=index),
        )
        for index in range(cfg.n_train or 0)
    ]


def _history_block(trace: list[dict[str, Any]], *, limit: int = 6) -> str:
    if not trace:
        return "(no actions yet)"
    rows = trace[-limit:]
    return "\n".join(
        f"step {row['step']}: action={row.get('action', '')!r}, "
        f"state={row.get('state_hash_before', '')}, error={row.get('error', '')!r}, "
        f"delta={str(row.get('visible_text_delta', ''))[:180]!r}"
        for row in rows
    )


def _solver_prompt(
    *,
    task: MiniWoBTaskInstance,
    trace: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    agent_id: int,
    tools_doc: str,
    observation_text: str,
) -> str:
    return (
        f"AGENT ID: {agent_id}\n"
        f"TASK FAMILY: {task.family}\n"
        f"TASK INSTANCE: {task.task_id}\n\n"
        f"TOOLS:\n{tools_doc}\n\n"
        f"REUSABLE EXPERIENCE:\n{render_library(insights)}\n\n"
        f"HISTORY:\n{_history_block(trace)}\n\n"
        f"OBSERVATION:\n{observation_text}\n\n"
        "Choose exactly one next browser action. Finish with exactly one line: Action: <tool call>."
    )


def _route_from_trace(
    *,
    success: bool,
    steps: int,
    terminated: bool,
    repeated_action_same_state: bool,
    parse_failure_count: int,
    parse_attempt_count: int,
    llm_error_count: int,
    infrastructure_error_count: int,
    max_steps: int,
    bid_error_count: int = 0,
    executed_action_count: int = 0,
) -> dict[str, Any]:
    nontermination = not terminated and not success
    failure_penalized_steps = steps if success else max_steps
    return {
        "success": bool(success),
        "steps": int(steps),
        "terminated": bool(terminated),
        "nontermination": bool(nontermination),
        "repeated_action_same_state": bool(repeated_action_same_state),
        "loop_stall_burden": bool(repeated_action_same_state or nontermination),
        "failure_penalized_steps": int(failure_penalized_steps),
        "failure_penalized_cost": float(failure_penalized_steps / max(max_steps, 1)),
        "parse_failure_count": int(parse_failure_count),
        "parse_attempt_count": int(parse_attempt_count),
        "parse_failure_rate": float(parse_failure_count / max(parse_attempt_count, 1)),
        "llm_error_count": int(llm_error_count),
        "infrastructure_error_count": int(infrastructure_error_count),
        "bid_error_count": int(bid_error_count),
        "executed_action_count": int(executed_action_count),
        "bid_error_rate": float(bid_error_count / max(executed_action_count, 1)),
    }


async def _browser_call(func, *args):
    """Run BrowserGym's synchronous Playwright API on its sole owning thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_BROWSER_EXECUTOR, lambda: func(*args))


def _env_snapshot(env: MiniWoBEnv) -> dict[str, Any]:
    return {
        "goal": env.goal(),
        "tools_doc": env.tools_doc(),
        "observation_text": env.observation_text(),
        "obs": env.last_obs,
        "state_hash": miniwob_state_hash(env.last_obs),
    }


async def run_miniwob_agent(
    task: MiniWoBTaskInstance,
    *,
    agent_id: int,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    audit: MazeMemoryAudit,
    t: int,
) -> MiniWoBAgentResult:
    env = MiniWoBEnv(task_name=task.family, seed=task.reset_seed)
    trace: list[dict[str, Any]] = []
    retrieved: list[dict[str, Any]] = []
    parse_failure_count = 0
    parse_attempt_count = 0
    llm_error_count = 0
    infrastructure_error_count = 0
    bid_error_count = 0
    executed_action_count = 0
    repeated_action_same_state = False
    seen_action_states: set[tuple[str, str]] = set()
    terminated = False
    success = False
    initial_obs: Any = {}
    final_obs: Any = {}
    goal = ""
    tools_doc = ""
    observation_text = ""
    current_hash = ""
    try:
        await _browser_call(env.reset, {"task_name": task.family, "seed": task.reset_seed})
        initial = await _browser_call(_env_snapshot, env)
        initial_obs = initial["obs"]
        final_obs = initial_obs
        goal = str(initial["goal"])
        tools_doc = str(initial["tools_doc"])
        observation_text = str(initial["observation_text"])
        current_hash = str(initial["state_hash"])
        query = f"{task.family}\n{goal}"
        retrieved = memory.retrieve(agent_id, query, t=t)
        audit.record_retrieval(
            t=t,
            task_id=task.task_id,
            agent_id=agent_id,
            items=retrieved,
            metadata=memory.retrieval_metadata(agent_id),
        )
        for step in range(cfg.max_steps):
            parse_attempt_count += 1
            try:
                completion = await llm.chat(
                    [
                        {"role": "system", "content": MINIWOB_SOLVER_SYS},
                        {
                            "role": "user",
                            "content": _solver_prompt(
                                task=task,
                                trace=trace,
                                insights=retrieved,
                                agent_id=agent_id,
                                tools_doc=tools_doc,
                                observation_text=observation_text,
                            ),
                        },
                    ],
                    temp=cfg.solver_temp,
                    max_tokens=cfg.max_tokens_solver,
                    tag=f"miniwob_solver:{agent_id}",
                    cache_salt=f"{cfg.run_id}|{task.task_id}|t={t}|agent={agent_id}|step={step}",
                )
            except RuntimeError as exc:
                llm_error_count += 1
                trace.append(
                    {
                        "step": step,
                        "action": "",
                        "normalized_action": "",
                        "state_hash_before": current_hash,
                        "state_hash": current_hash,
                        "visible_text_delta": "",
                        "error": f"llm_error:{str(exc)[:180]}",
                        "parse_failure": False,
                    }
                )
                break
            action = parse_action(completion)
            if not action:
                parse_failure_count += 1
                trace.append(
                    {
                        "step": step,
                        "action": "",
                        "normalized_action": "",
                        "state_hash_before": current_hash,
                        "state_hash": current_hash,
                        "visible_text_delta": "",
                        "error": "parse_failure",
                        "parse_failure": True,
                    }
                )
                break
            state_before = current_hash
            normalized_action = normalize_answer(action)
            action_state = (state_before, normalized_action)
            if action_state in seen_action_states:
                repeated_action_same_state = True
            seen_action_states.add(action_state)
            _action_name, referenced_bid = action_bid_reference(action)
            bid_invalid_pre = referenced_bid is not None and referenced_bid not in extract_bids(observation_text)
            executed_action_count += 1
            try:
                _obs_text, done, info = await _browser_call(env.step, action)
            except Exception as exc:  # noqa: BLE001
                infrastructure_error_count += 1
                trace.append(
                    {
                        "step": step,
                        "action": action,
                        "normalized_action": normalized_action,
                        "state_hash_before": state_before,
                        "state_hash": state_before,
                        "visible_text_delta": "",
                        "error": f"browser_exception:{str(exc)[:180]}",
                        "parse_failure": False,
                    }
                )
                break
            snapshot = await _browser_call(_env_snapshot, env)
            final_obs = snapshot["obs"]
            observation_text = str(snapshot["observation_text"])
            current_hash = str(info.get("state_hash") or snapshot["state_hash"])
            error = str(info.get("last_action_error", ""))
            bid_error = bid_invalid_pre or "could not find element with bid" in error.lower()
            if bid_error:
                bid_error_count += 1
            trace.append(
                {
                    "step": step,
                    "action": action,
                    "normalized_action": normalized_action,
                    "state_hash_before": state_before,
                    "state_hash": current_hash,
                    "visible_text_delta": str(info.get("visible_text_delta", "")),
                    "error": error,
                    "bid_error": bid_error,
                    "parse_failure": False,
                }
            )
            if done:
                terminated = True
                break
        success = bool(await _browser_call(env.is_success))
        route = _route_from_trace(
            success=success,
            steps=len(trace),
            terminated=terminated,
            repeated_action_same_state=repeated_action_same_state,
            parse_failure_count=parse_failure_count,
            parse_attempt_count=parse_attempt_count,
            llm_error_count=llm_error_count,
            infrastructure_error_count=infrastructure_error_count,
            max_steps=cfg.max_steps,
            bid_error_count=bid_error_count,
            executed_action_count=executed_action_count,
        )
        summary = reviewer_episode_summary(
            goal=goal,
            success=success,
            steps=len(trace),
            trajectory=trace,
            final_obs=final_obs,
        )
        route["initial_state_hash"] = miniwob_state_hash(initial_obs)
        return MiniWoBAgentResult(
            agent_id=agent_id,
            route=route,
            trace=trace,
            retrieved=[dict(item) for item in retrieved],
            reviewer_summary=summary,
        )
    except Exception as exc:  # noqa: BLE001
        infrastructure_error_count += 1
        route = _route_from_trace(
            success=False,
            steps=len(trace),
            terminated=False,
            repeated_action_same_state=repeated_action_same_state,
            parse_failure_count=parse_failure_count,
            parse_attempt_count=parse_attempt_count,
            llm_error_count=llm_error_count,
            infrastructure_error_count=infrastructure_error_count,
            max_steps=cfg.max_steps,
            bid_error_count=bid_error_count,
            executed_action_count=executed_action_count,
        )
        route["initial_state_hash"] = miniwob_state_hash(initial_obs)
        summary = reviewer_episode_summary(
            goal=goal,
            success=False,
            steps=len(trace),
            trajectory=trace,
            final_obs=final_obs,
        )
        audit.record_llm_error(t=t, task_id=task.task_id, tag="miniwob_setup", message=str(exc))
        return MiniWoBAgentResult(
            agent_id=agent_id,
            route=route,
            trace=trace,
            retrieved=[dict(item) for item in retrieved],
            reviewer_summary=summary,
        )
    finally:
        await _browser_call(env.close)


async def run_miniwob_episode(
    task: MiniWoBTaskInstance,
    *,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    audit: MazeMemoryAudit,
    t: int,
) -> MiniWoBEpisodeResult:
    agents = await asyncio.gather(
        *[
            run_miniwob_agent(task, agent_id=agent_id, memory=memory, cfg=cfg, llm=llm, audit=audit, t=t)
            for agent_id in range(cfg.n_solvers)
        ]
    )
    return MiniWoBEpisodeResult(task=task, agents=list(agents))


async def _run_task_batch(
    tasks: list[MiniWoBTaskInstance],
    *,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    audit: MazeMemoryAudit,
    t: int,
    episode_concurrency: int,
) -> list[MiniWoBEpisodeResult]:
    sem = asyncio.Semaphore(max(1, episode_concurrency))

    async def run(task: MiniWoBTaskInstance) -> MiniWoBEpisodeResult:
        async with sem:
            return await run_miniwob_episode(task, memory=memory, cfg=cfg, llm=llm, audit=audit, t=t)

    return list(await asyncio.gather(*[run(task) for task in tasks]))


def _episode_quality(episode: MiniWoBEpisodeResult, agent_id: int) -> dict[str, Any]:
    agent = next((item for item in episode.agents if item.agent_id == agent_id), episode.agents[0])
    route = agent.route
    return {
        "success": route.get("success"),
        "steps": route.get("steps"),
        "failure_penalized_steps": route.get("failure_penalized_steps"),
        "repeated_action_same_state": route.get("repeated_action_same_state"),
        "nontermination": route.get("nontermination"),
        "loop_stall_burden": route.get("loop_stall_burden"),
    }


def _reviewer_episodes(episode: MiniWoBEpisodeResult) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for agent in episode.agents:
        records.append(
            {
                "episode_id": episode.task_id,
                "agent_id": agent.agent_id,
                "outcome": "success" if agent.route.get("success") else "failure",
                "quality": _episode_quality(episode, agent.agent_id),
                "trajectory": json.dumps(agent.reviewer_summary, ensure_ascii=False, sort_keys=True),
            }
        )
    return records


def _record_rejects(
    audit: MazeMemoryAudit,
    rejects: list[dict[str, str]],
    *,
    episode: MiniWoBEpisodeResult,
    t: int,
    write_mode: str,
) -> None:
    for item in rejects:
        audit.record_rejection(
            t=t,
            task_id=episode.task_id,
            write_mode=write_mode,
            text=item.get("text", ""),
            reason=item.get("reason", "over_specific"),
        )


async def _write_append(
    episode: MiniWoBEpisodeResult,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    *,
    audit: MazeMemoryAudit,
    t: int,
) -> None:
    for agent in episode.agents:
        mini_episode = MiniWoBEpisodeResult(task=episode.task, agents=[agent])
        rejects: list[dict[str, str]] = []
        try:
            insights = await distill_expel_insights(
                _reviewer_episodes(mini_episode),
                MINIWOB_EXPEL_ADAPTER,
                cfg,
                llm,
                reject_log=rejects,
            )
        except RuntimeError as exc:
            audit.record_llm_error(t=t, task_id=episode.task_id, tag="miniwob_append_reviewer", message=str(exc))
            continue
        _record_rejects(audit, rejects, episode=episode, t=t, write_mode="reviewer_append")
        pool = memory.pool_view(agent.agent_id)
        quality = _episode_quality(episode, agent.agent_id)
        for raw in insights[:2]:
            insight = sanitize_expel_insight(raw)
            if not insight:
                audit.record_rejection(
                    t=t,
                    task_id=episode.task_id,
                    write_mode="reviewer_append",
                    text=str(raw.get("text", "")),
                    reason="over_specific",
                )
                continue
            duplicate = find_pool_duplicate(pool, insight, cfg)
            if duplicate is not None:
                pool[duplicate]["votes"] = int(pool[duplicate].get("votes", 0)) + 1
                item = pool[duplicate]
                write_mode = "reviewer_append:agree"
            else:
                item = {"kind": insight["kind"], "text": insight["text"], "votes": 1, "last_access_t": t}
                pool.append(item)
                write_mode = "reviewer_append:append"
            audit.record_write(
                t=t,
                task_id=episode.task_id,
                agent_id=agent.agent_id,
                insight=item,
                support_count=int(item.get("votes", 0)),
                write_mode=write_mode,
                quality=quality,
            )
        if len(pool) > cfg.library_cap:
            pool.sort(key=lambda item: (int(item.get("votes", 0)), normalize_answer(str(item.get("text", "")))), reverse=True)
            del pool[cfg.library_cap:]
        memory.set_pool(agent.agent_id, pool)


async def _write_consolidated(
    episode: MiniWoBEpisodeResult,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    *,
    audit: MazeMemoryAudit,
    t: int,
) -> None:
    pool = memory.pool_view(0)
    try:
        ops = await propose_memory_ops(pool, _reviewer_episodes(episode), MINIWOB_EXPEL_ADAPTER, cfg, llm)
    except RuntimeError as exc:
        audit.record_llm_error(t=t, task_id=episode.task_id, tag="miniwob_expel_ops_reviewer", message=str(exc))
        return
    rejects: list[dict[str, str]] = []
    new_pool, applied = apply_memory_ops(pool, ops, cfg=cfg, reject_log=rejects)
    memory.set_pool(0, new_pool)
    _record_rejects(audit, rejects, episode=episode, t=t, write_mode="reviewer_ops")
    quality = _episode_quality(episode, 0)
    for op in applied:
        item = op["item"]
        if op["op"] in {"ADD", "EDIT"}:
            item["last_access_t"] = t
        audit.record_write(
            t=t,
            task_id=episode.task_id,
            agent_id=0,
            insight=item,
            support_count=int(item.get("votes", 0)),
            write_mode=f"reviewer_ops:{op['op']}",
            quality=quality,
        )


async def write_miniwob_experience(
    episode: MiniWoBEpisodeResult,
    *,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    audit: MazeMemoryAudit,
    t: int,
) -> None:
    if memory.mode == "none":
        return
    if cfg.memory_write_protocol == "append":
        await _write_append(episode, memory, cfg, llm, audit=audit, t=t)
        return
    if cfg.memory_write_protocol == "expel_ops":
        await _write_consolidated(episode, memory, cfg, llm, audit=audit, t=t)
        return
    raise ValueError(f"unsupported MiniWoB memory protocol {cfg.memory_write_protocol!r}")


def _batch_metrics(episodes: list[MiniWoBEpisodeResult]) -> dict[str, float]:
    routes = [agent.route for episode in episodes for agent in episode.agents]
    if not routes:
        return {
            "success_rate": 0.0,
            "steps": 0.0,
            "failure_penalized_steps": 0.0,
            "failure_penalized_cost": 0.0,
            "repeated_action_same_state_rate": 0.0,
            "nontermination_rate": 0.0,
            "loop_stall_burden_rate": 0.0,
            "parse_failure_rate": 0.0,
            "infrastructure_error_route_rate": 0.0,
            "bid_error_rate": 0.0,
        }
    mean = lambda key: float(sum(float(route.get(key) or 0.0) for route in routes) / len(routes))
    total_bid_errors = sum(int(route.get("bid_error_count") or 0) for route in routes)
    total_executed = sum(int(route.get("executed_action_count") or 0) for route in routes)
    return {
        "success_rate": mean("success"),
        "steps": mean("steps"),
        "failure_penalized_steps": mean("failure_penalized_steps"),
        "failure_penalized_cost": mean("failure_penalized_cost"),
        "repeated_action_same_state_rate": mean("repeated_action_same_state"),
        "nontermination_rate": mean("nontermination"),
        "loop_stall_burden_rate": mean("loop_stall_burden"),
        "parse_failure_rate": mean("parse_failure_rate"),
        "infrastructure_error_route_rate": float(
            sum(1 for route in routes if int(route.get("infrastructure_error_count") or 0) > 0) / len(routes)
        ),
        "bid_error_rate": float(total_bid_errors / max(total_executed, 1)),
    }


def _sample_train_batch(
    tasks: list[MiniWoBTaskInstance],
    *,
    batch_size: int,
    t: int,
    rng: random.Random,
) -> list[MiniWoBTaskInstance]:
    if not tasks or batch_size <= 0:
        return []
    start = (t * batch_size) % len(tasks)
    batch = list(tasks[start:start + batch_size])
    if len(batch) < batch_size:
        batch.extend(tasks[: batch_size - len(batch)])
    rng.shuffle(batch)
    return batch


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def _hash_replay(
    episode: MiniWoBEpisodeResult,
    *,
    max_actions: int = 2,
) -> dict[str, Any]:
    agent = episode.agents[0]
    env = MiniWoBEnv(task_name=episode.task.family, seed=episode.task.reset_seed)
    expected = [str(agent.route.get("initial_state_hash", ""))]
    expected.extend(str(row.get("state_hash", "")) for row in agent.trace[:max_actions] if row.get("action"))
    observed: list[str] = []
    error = ""
    try:
        await _browser_call(env.reset, {"task_name": episode.task.family, "seed": episode.task.reset_seed})
        snapshot = await _browser_call(_env_snapshot, env)
        observed.append(str(snapshot["state_hash"]))
        for row in agent.trace[:max_actions]:
            action = str(row.get("action", ""))
            if not action:
                continue
            _obs_text, _done, info = await _browser_call(env.step, action)
            observed.append(str(info.get("state_hash") or ""))
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:240]
    finally:
        await _browser_call(env.close)
    n = min(len(expected), len(observed))
    matches = sum(1 for index in range(n) if expected[index] and expected[index] == observed[index])
    return {
        "task_id": episode.task_id,
        "expected_hashes": expected,
        "observed_hashes": observed,
        "n_compared": n,
        "n_matches": matches,
        "agreement": float(matches / n) if n else 0.0,
        "error": error,
    }


async def run_one_miniwob_gamma(
    cfg: Config,
    *,
    family: str,
    phase: str,
    episode_concurrency: int,
) -> dict[str, Any]:
    llm = LLMClient(cfg)
    memory = InsightMemory(cfg)
    audit = MazeMemoryAudit()
    rng = random.Random(cfg.seed)
    out_dir = cfg.output_path() / condition_name(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_manifest = browsergym_version_manifest()
    manifest = {
        "condition": condition_name(cfg),
        "run_id": cfg.run_id,
        "phase": phase,
        "arm": cfg.notes[0] if cfg.notes else "",
        "task_family": family,
        "seed": cfg.seed,
        "created_unix": time.time(),
        "config": cfg.to_public_dict(),
        "miniwob": {
            **runtime_manifest,
            "miniwob_url": os.environ.get("MINIWOB_URL", ""),
            "task_validation": validate_miniwob_tasks(
                [family],
                runtime_manifest=runtime_manifest,
            ),
            "independent_envs_per_task": cfg.n_solvers,
        },
        "preregistration": (
            "prereg_phase_gamma_p3_execution.md + prereg_phase_gamma_p3_execution_amendment_01.md "
            "+ prereg_phase_gamma_p3_execution_amendment_02.md "
            "+ prereg_phase_gamma_p3_execution_amendment_03.md "
            "+ prereg_phase_gamma_p3_execution_amendment_04.md"
        ),
    }
    _write_json(out_dir / "manifest.json", manifest)
    deviation_log = out_dir / "prereg_deviation_log.md"
    if not deviation_log.exists():
        deviation_log.write_text("# Preregistration Deviations\n\nNo deviations recorded at run start.\n", encoding="utf-8")

    heldout = heldout_tasks(family, cfg)
    train = train_tasks(family, cfg)
    log: list[dict[str, Any]] = []
    heldout_records: list[dict[str, Any]] = []
    hash_replays: list[dict[str, Any]] = []
    started = time.time()
    for t in range(cfg.T):
        heldout_eps = await _run_task_batch(
            heldout,
            memory=memory,
            cfg=cfg,
            llm=llm,
            audit=audit,
            t=t,
            episode_concurrency=episode_concurrency,
        )
        metrics = _batch_metrics(heldout_eps)
        audit.record_pool_state(t=t, memory=memory)
        row = {
            "t": t,
            **metrics,
            "memory_size": memory.size(),
            "tokens_total_so_far": llm.stats.total_tokens,
            "network_calls_so_far": llm.stats.network_calls,
            "cache_hits_so_far": llm.stats.cache_hits,
        }
        log.append(row)
        heldout_records.append({"t": t, "episodes": [episode.public() for episode in heldout_eps]})
        if phase == "gamma_p3_smoke":
            hash_replays.extend(await asyncio.gather(*[_hash_replay(episode) for episode in heldout_eps]))
        print(
            f"[{condition_name(cfg)}] t={t:02d} family={family} success={row['success_rate']:.3f} "
            f"cost={row['failure_penalized_cost']:.3f} stall={row['loop_stall_burden_rate']:.3f} "
            f"biderr={row['bid_error_rate']:.3f} mem={memory.size()} tokens={llm.stats.total_tokens}",
            flush=True,
        )
        should_train = cfg.batch_M > 0 and not (cfg.skip_final_train and t == cfg.T - 1)
        if should_train:
            batch = _sample_train_batch(train, batch_size=cfg.batch_M, t=t, rng=rng)
            train_eps = await _run_task_batch(
                batch,
                memory=memory,
                cfg=cfg,
                llm=llm,
                audit=audit,
                t=t,
                episode_concurrency=episode_concurrency,
            )
            for episode in train_eps:
                await write_miniwob_experience(
                    episode,
                    memory=memory,
                    cfg=cfg,
                    llm=llm,
                    audit=audit,
                    t=t,
                )
        partial = {
            "config": cfg.to_public_dict(),
            "task_family": family,
            "log": log,
            "memory": memory.snapshot(),
            "audit": audit.public(memory),
        }
        _write_json(out_dir / "partial.json", partial)

    summary = {
        "condition": condition_name(cfg),
        "task_family": family,
        "arm": cfg.notes[0] if cfg.notes else "",
        "success_final": log[-1]["success_rate"] if log else 0.0,
        "failure_penalized_cost_final": log[-1]["failure_penalized_cost"] if log else 0.0,
        "loop_stall_burden_final": log[-1]["loop_stall_burden_rate"] if log else 0.0,
        "parse_failure_rate_final": log[-1]["parse_failure_rate"] if log else 0.0,
        "infrastructure_error_route_rate_final": log[-1]["infrastructure_error_route_rate"] if log else 0.0,
        "llm": llm.stats.public_summary(),
        "elapsed_sec": time.time() - started,
    }
    result = {
        "config": cfg.to_public_dict(),
        "task_family": family,
        "phase": phase,
        "log": log,
        "summary": summary,
        "memory": memory.snapshot(),
        "memory_audit": audit.public(memory),
        "heldout_records": heldout_records,
        "hash_replays": hash_replays,
    }
    _write_json(out_dir / "result.json", result)
    _write_json(out_dir / "memory_audit.json", audit.public(memory))
    return result


def build_configs(args: argparse.Namespace) -> list[tuple[Config, str]]:
    tasks = [item.strip() for item in args.tasks.split(",") if item.strip()]
    invalid = [item for item in tasks if item not in MINIWOB_ALL_PREREG_TASKS]
    if invalid:
        raise ValueError(f"unknown MiniWoB task(s): {invalid}")
    seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    configs: list[tuple[Config, str]] = []
    for family in tasks:
        for seed in seeds:
            for arm in _arms_for_phase(args.phase):
                run_id = f"gamma_p3_{family.replace('-', '_')}_{arm['run_id_suffix']}"
                params = {
                    "model": args.model,
                    "base_url": args.base_url,
                    "api_key_env": args.api_key_env,
                    "dataset": "miniwob",
                    "out_dir": args.out_dir,
                    "cache_dir": args.cache_dir,
                    "cache_policy": args.cache_policy,
                    "seed": seed,
                    "T": args.T,
                    "heldout_size": args.heldout_size,
                    "batch_M": args.train_batch,
                    "n_train": args.train_size,
                    "max_steps": args.max_steps,
                    "concurrency": args.concurrency,
                    "solver_temp": args.solver_temp,
                    "max_tokens_solver": args.max_tokens_solver,
                    "max_tokens_reviewer": args.max_tokens_reviewer,
                    "skip_final_train": args.skip_final_train,
                    "run_id": run_id,
                    "notes": [str(arm["arm"])],
                }
                params.update({key: value for key, value in arm.items() if key not in {"run_id_suffix", "arm"}})
                configs.append((Config(**params), family))
    return configs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Gamma P3 MiniWoB++ task-generalization experiments.")
    parser.add_argument("--phase", choices=["gamma_p3_smoke", "gamma_p3_formal"], required=True)
    parser.add_argument("--tasks", default=",".join(MINIWOB_PRIMARY_TASKS))
    parser.add_argument("--model", default="DeepSeek-V3")
    parser.add_argument("--base-url", default="https://api.modelarts-maas.com/v2")
    parser.add_argument("--api-key-env", default="MODELARTS_MAAS_KEY")
    parser.add_argument("--out-dir", default="./runs_miniwob_gamma_p3")
    parser.add_argument("--cache-dir", default="./cache_miniwob_gamma_p3")
    parser.add_argument("--cache-policy", choices=["read_write", "off"], default="read_write")
    parser.add_argument("--seeds", default="0")
    parser.add_argument("--T", type=int, default=4)
    parser.add_argument("--heldout-size", type=int, default=12)
    parser.add_argument("--train-size", type=int, default=16)
    parser.add_argument("--train-batch", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--concurrency", type=int, default=8, help="MaaS concurrency shared by the four solvers.")
    parser.add_argument("--episode-concurrency", type=int, default=2, help="Concurrent task instances; each owns four browsers.")
    parser.add_argument("--solver-temp", type=float, default=0.7)
    parser.add_argument("--max-tokens-solver", type=int, default=256)
    parser.add_argument("--max-tokens-reviewer", type=int, default=512)
    parser.add_argument("--skip-final-train", action="store_true")
    return parser


async def _run_all(args: argparse.Namespace) -> None:
    runtime_validation = validate_frozen_browser_runtime()
    if not runtime_validation.get("ok"):
        raise RuntimeError(
            "Frozen MiniWoB browser runtime validation failed before launch. "
            f"Details: {runtime_validation}"
        )
    validation = validate_miniwob_tasks(
        runtime_manifest=runtime_validation["actual"],
    )
    if not validation.get("ok"):
        raise RuntimeError(
            "MiniWoB task registration failed. Install browsergym-miniwob, initialize its browser runtime, "
            f"and configure MINIWOB_URL. Details: {validation}"
        )
    for cfg, family in build_configs(args):
        await run_one_miniwob_gamma(
            cfg,
            family=family,
            phase=args.phase,
            episode_concurrency=args.episode_concurrency,
        )
    final_runtime_validation = validate_frozen_browser_runtime()
    if not final_runtime_validation.get("ok"):
        raise RuntimeError(
            "Frozen MiniWoB browser runtime changed during execution. "
            f"Details: {final_runtime_validation}"
        )


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    asyncio.run(_run_all(args))


if __name__ == "__main__":
    main()
