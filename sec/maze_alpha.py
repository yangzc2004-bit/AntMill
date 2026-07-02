from __future__ import annotations

import argparse
import asyncio
import html
import json
import math
import random
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agentic import parse_action
from .config import Config, condition_name
from .expel import ExpeLAdapter, distill_expel_insights, sanitize_expel_insight
from .expel_ops import apply_memory_ops, propose_memory_ops
from .llm import LLMClient
from .maze_env import DIRS, MazeEnv, MazeTask, _is_open as _maze_is_open, make_maze_tasks
from .memory import InsightMemory
from .metrics import normalize_answer, similarity
from .solver import render_library


MAZE_AGENT_SYS = (
    "You are a maze-navigation agent. Use reusable experience only as strategic guidance, never as a memorized route. "
    "Read the local observation, your recent history, and the available tools. Output 1-2 short reasoning sentences "
    "and exactly one final line: Action: <move:up|move:down|move:left|move:right|inspect|submit>."
)

MAZE_EXPEL_ADAPTER = ExpeLAdapter(
    task_family="local-observation maze navigation",
    trajectory_label="maze trajectory log",
    forbidden_details="Do not mention maze ids, coordinates, exact paths, or fixed action sequences.",
    strategy_focus="loop avoidance, revisits, recovery, systematic exploration, efficient progress, and timely submit after success.",
    fallback={
        "kind": "do",
        "text": "Use local progress, revisits, and open directions to adapt exploration without memorizing exact routes.",
    },
)


@dataclass
class AgentRouteResult:
    agent_id: int
    route: dict[str, Any]
    trace: list[dict[str, Any]]
    retrieved: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.route.get("success"))


@dataclass
class MazeEpisodeResult:
    task_id: str
    task: MazeTask
    agents: list[AgentRouteResult]

    def public(self, *, include_trace: bool = True) -> dict[str, Any]:
        return {
            "task": self.task.public(),
            "task_id": self.task_id,
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "route": a.route,
                    "retrieved": [
                        {"text": item.get("text", ""), "kind": item.get("kind", "do"), "id": item.get("id")}
                        for item in a.retrieved
                    ],
                    "trace": a.trace if include_trace else [],
                }
                for a in self.agents
            ],
        }


class MazeMemoryAudit:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []
        self.retrievals: list[dict[str, Any]] = []
        self.rejections: list[dict[str, Any]] = []

    def record_retrieval(self, *, t: int, task_id: str, agent_id: int, items: list[dict[str, Any]]) -> None:
        for item in items:
            item["retrieval_count"] = int(item.get("retrieval_count", 0)) + 1
            item.setdefault("retrieved_by", []).append({"t": t, "task_id": task_id, "agent_id": agent_id})
        self.retrievals.append(
            {
                "t": t,
                "task_id": task_id,
                "agent_id": agent_id,
                "items": [item.get("id") or _insight_key(item) for item in items],
                "texts": [item.get("text", "") for item in items],
            }
        )

    def record_write(
        self,
        *,
        t: int,
        task_id: str,
        agent_id: int,
        insight: dict[str, Any],
        support_count: int,
        write_mode: str,
        quality: dict[str, Any],
    ) -> None:
        insight.setdefault("id", _insight_key(insight))
        provenance = {
            "t": t,
            "task_id": task_id,
            "agent_id": agent_id,
            "write_mode": write_mode,
            "support_count": support_count,
            "quality": quality,
        }
        insight.setdefault("sources", []).append(provenance)
        insight.setdefault("retrieval_count", 0)
        self.writes.append({"insight": dict(insight), **provenance})

    def record_rejection(self, *, t: int, task_id: str, write_mode: str, text: str, reason: str) -> None:
        self.rejections.append(
            {"t": t, "task_id": task_id, "write_mode": write_mode, "text": text, "reason": reason}
        )

    def retrieval_share_series(self) -> dict[str, dict[str, float]]:
        """Per-item share of retrievals in each round: {item_id: {t: share}}.

        Raw data for rich-get-richer curves: a positive-feedback channel shows up
        as one item's share growing across rounds.
        """
        by_t: dict[int, Counter[str]] = defaultdict(Counter)
        for rec in self.retrievals:
            t = int(rec.get("t", 0))
            for item_id in rec.get("items", []):
                by_t[t][str(item_id)] += 1
        series: dict[str, dict[str, float]] = {}
        for t, counter in sorted(by_t.items()):
            total = sum(counter.values())
            for item_id, count in counter.items():
                series.setdefault(item_id, {})[str(t)] = count / total if total else 0.0
        return series

    def public(self, memory: InsightMemory) -> dict[str, Any]:
        items = memory.all_items()
        attempts = len(self.rejections) + len(self.writes)
        return {
            "writes": self.writes,
            "retrievals": self.retrievals,
            "sanitizer_rejects": self.rejections,
            "sanitizer_reject_rate": len(self.rejections) / attempts if attempts else 0.0,
            "memory_items": items,
            "retrieval_top1_share": retrieval_top1_share(items),
            "retrieval_concentration": retrieval_concentration(items),
            "retrieval_entropy_norm": retrieval_entropy_norm(items),
            "memory_effective_size": memory_effective_size(items),
            "retrieval_share_series": self.retrieval_share_series(),
        }


def _insight_key(insight: dict[str, Any]) -> str:
    return normalize_answer(f"{insight.get('kind', 'do')} {insight.get('text', '')}")[:96]


def _solver_cache_salt(cfg: Config, *, t: int, task_id: str, agent_id: int, step: int) -> str:
    # run_id keeps conditions with identical prompts (e.g. frozen vs no-memory) statistically
    # independent; t/step keep rounds and revisited in-episode states from replaying one sample.
    return f"{cfg.run_id}|seed{cfg.seed}|t{t}|{task_id}|a{agent_id}|s{step}"


def _agent_query(task: MazeTask) -> str:
    """Task-conditioned retrieval query built only from agent-visible start information.

    A constant query makes retrieval a static ranking (every episode retrieves the same
    top-k), so retrieval dynamics cannot exist. Bearing/distance/opening features vary
    per task without exposing hidden structure; raw coordinates are deliberately
    excluded so the query cannot act as a per-maze answer-cache key.
    """
    sx, sy = task.start
    gx, gy = task.goal
    dx, dy = gx - sx, gy - sy
    ew = "east" if dx > 0 else "west" if dx < 0 else "aligned"
    ns = "south" if dy > 0 else "north" if dy < 0 else "aligned"
    open_dirs = sorted(
        name for name, (ddx, ddy) in DIRS.items() if _maze_is_open(task.grid, sx + ddx, sy + ddy)
    )
    manhattan = abs(dx) + abs(dy)
    # Space-separated tokens: normalize_answer strips punctuation without inserting
    # spaces, so key=value forms would collapse into unmatchable single tokens.
    return (
        f"maze goal navigation family {task.family} size {task.width}x{task.height} "
        f"goal bearing {ew} {ns} start manhattan {manhattan} start open {' '.join(open_dirs)}"
    )


def _parse_open_dirs(obs: str) -> list[str]:
    match = re.search(r"Open directions:\s*([^.]+)\.", obs)
    if not match:
        return []
    raw = match.group(1).strip()
    if raw == "none":
        return []
    return [part.strip() for part in raw.split(",") if part.strip() in DIRS]


def _action_direction(action: str) -> str:
    clean = str(action).strip().lower()
    if clean.startswith("action:"):
        clean = clean.split(":", 1)[1].strip()
    if clean.startswith("move:"):
        direction = clean.split(":", 1)[1].strip()
        return direction if direction in DIRS else ""
    return ""


def _direction_between(src: tuple[int, int], dst: tuple[int, int]) -> str:
    dx = dst[0] - src[0]
    dy = dst[1] - src[1]
    for name, delta in DIRS.items():
        if delta == (dx, dy):
            return name
    return ""


def _ordered_dirs_toward_goal(pos: tuple[int, int], goal: tuple[int, int], dirs: set[str]) -> list[str]:
    def score(direction: str) -> tuple[int, int]:
        dx, dy = DIRS[direction]
        nxt = (pos[0] + dx, pos[1] + dy)
        dist = abs(goal[0] - nxt[0]) + abs(goal[1] - nxt[1])
        # Stable tie-breaker keeps runs deterministic while still preferring progress.
        return dist, ["right", "down", "left", "up"].index(direction)

    return sorted(dirs, key=score)


def _controlled_dfs_action(model_action: str, recommended_action: str) -> str:
    model_clean = str(model_action).strip().lower()
    if recommended_action == "submit":
        return "submit"
    if model_clean == recommended_action:
        return model_action
    # The controller is deliberately conservative: it prevents local loops by enforcing
    # the externally tracked DFS frontier, but it never uses hidden maze cells.
    return recommended_action


def _valid_maze_action(action: str) -> bool:
    raw = str(action).strip().lower()
    if raw.startswith("action:"):
        raw = raw.split(":", 1)[1].strip()
    raw = raw.replace(" ", "").strip("`'\".,;")
    if raw in DIRS:
        return True
    if raw in {"inspect", "submit"}:
        return True
    if raw.startswith("move:"):
        return raw.split(":", 1)[1] in DIRS
    return False


def _state_guided_action(model_action: str, fallback_action: str) -> tuple[str, bool, str]:
    if _valid_maze_action(model_action):
        return model_action, False, ""
    fallback = fallback_action if _valid_maze_action(fallback_action) else "inspect"
    return fallback, True, "parse_failure"


def _uses_search_state(agent_mode: str) -> bool:
    return agent_mode in {"state_guided", "stateful_dfs"}


def _search_instruction(agent_mode: str) -> str:
    if agent_mode == "state_guided":
        return (
            "SEARCH STATE is working memory derived only from your past local observations. "
            "It lists visited/tried/untried directions, a possible backtrack action, and revisit/stagnation warnings. "
            "Use this priority unless the observation says Manhattan distance is 0: "
            "(1) choose a move from frontier_dirs_here when any exists; "
            "(2) otherwise choose a move from untried_dirs_here when any exists, even if that edge goes to a known cell; "
            "(3) if every local open direction has already been tried but global_frontier_action exists, use global_frontier_action; "
            "(4) otherwise use backtrack_candidate to return toward an older fork; "
            "(5) inspect only when the state is ambiguous. "
            "When revisit_warning or stagnation_warning is true, stop optimizing only for Manhattan distance and switch to this DFS-style recovery priority. "
            "Never submit unless the observation says Manhattan distance is 0. "
            "Treat suggested_action as the best local-memory candidate, but the runner will not force it unless your Action line is unparsable. "
            "If your final Action line is unparsable, the runner will fall back to suggested_action and count it as an override. "
        )
    if agent_mode == "stateful_dfs":
        return (
            "SEARCH STATE is a controller frontier. Follow recommended_action unless the observation says the goal is reached. "
        )
    return ""


def _search_public(search: "MazeSearchState | None", env: MazeEnv) -> dict[str, Any]:
    if search is None or env.task is None:
        return {}
    return search.public(env.pos, env.task.goal, env.path)


def _route_stagnation_rate(path: list[Any], goal: tuple[int, int]) -> float:
    cells = [tuple(cell) for cell in path]
    if len(cells) <= 1:
        return 0.0
    seen: set[tuple[int, int]] = {cells[0]}
    best = abs(cells[0][0] - goal[0]) + abs(cells[0][1] - goal[1])
    stalled = 0
    for cell in cells[1:]:
        dist = abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])
        if cell in seen and dist >= best:
            stalled += 1
        if dist < best:
            best = dist
        seen.add(cell)
    return stalled / max(len(cells) - 1, 1)


def _add_route_eval_fields(
    route: dict[str, Any],
    *,
    task: MazeTask,
    max_steps: int,
    agent_mode: str,
    trace: list[dict[str, Any]],
) -> None:
    shortest = max(int(route.get("shortest_path_length") or 1), 1)
    effective_steps = int(route.get("steps") or 0) if route.get("success") else max(max_steps, shortest * 2)
    override_count = sum(1 for row in trace if row.get("state_guided_override"))
    route["effective_steps"] = effective_steps
    route["cost_ratio"] = effective_steps / shortest
    route["excess_steps"] = effective_steps - shortest
    route["agent_mode"] = agent_mode
    route["stagnation_rate"] = _route_stagnation_rate(route.get("path", []), task.goal)
    route["state_guided_override_count"] = override_count
    route["state_guided_override_rate"] = override_count / max(len(trace), 1)


def _run_oracle_maze_agent(task: MazeTask, *, agent_id: int, insights: list[dict[str, Any]]) -> AgentRouteResult:
    env = MazeEnv()
    obs = env.reset(task)
    trace: list[dict[str, Any]] = []
    for step, (cur, nxt) in enumerate(zip(task.shortest_path, task.shortest_path[1:])):
        action = f"move:{_direction_between(cur, nxt)}"
        obs_after, _, info = env.step(action)
        trace.append(
            {
                "step": step,
                "prompt_observation": obs,
                "raw": "oracle_dfs",
                "action": action,
                "controller_action": action,
                "search_state": {"recommended_action": action, "recommendation_reason": "oracle_shortest_path"},
                "normalized_action": info.get("normalized_action"),
                "observation": obs_after,
                "position": list(env.pos),
                "invalid": bool(info.get("invalid")),
            }
        )
        obs = obs_after
    obs_after, _, info = env.step("submit")
    trace.append(
        {
            "step": len(trace),
            "prompt_observation": obs,
            "raw": "oracle_dfs",
            "action": "submit",
            "controller_action": "submit",
            "search_state": {"recommended_action": "submit", "recommendation_reason": "at_goal"},
            "normalized_action": info.get("normalized_action"),
            "observation": obs_after,
            "position": list(env.pos),
            "invalid": bool(info.get("invalid")),
        }
    )
    route = env.route_record()
    _add_route_eval_fields(
        route,
        task=task,
        max_steps=max(task.shortest_path_length * 2, 1),
        agent_mode="oracle_dfs",
        trace=trace,
    )
    return AgentRouteResult(agent_id=agent_id, route=route, trace=trace, retrieved=insights)


OPPOSITE_DIR: dict[str, str] = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}


class MazeSearchState:
    """Externalized DFS memory built only from local observations."""

    def __init__(self) -> None:
        self.open_seen: dict[tuple[int, int], set[str]] = {}
        self.tried: dict[tuple[int, int], set[str]] = defaultdict(set)
        self.parent: dict[tuple[int, int], tuple[int, int] | None] = {}
        self.dead_ends: set[tuple[int, int]] = set()

    def update_observation(self, pos: tuple[int, int], obs: str, path: list[tuple[int, int]]) -> None:
        self.open_seen[pos] = set(_parse_open_dirs(obs))
        self.parent.setdefault(pos, path[-2] if len(path) >= 2 else None)

    def mark_transition(self, before: tuple[int, int], action: str, after: tuple[int, int], invalid: bool) -> None:
        direction = _action_direction(action)
        if not direction:
            return
        self.tried[before].add(direction)
        if invalid or before == after:
            return
        self.parent.setdefault(after, before)
        self.tried[after].add(OPPOSITE_DIR[direction])

    def next_action(self, pos: tuple[int, int], goal: tuple[int, int]) -> tuple[str, str]:
        if pos == goal:
            return "submit", "at_goal"
        open_dirs = self.open_seen.get(pos, set())
        tried = self.tried.get(pos, set())
        frontier = self._frontier_dirs(pos, goal)
        if frontier:
            return f"move:{frontier[0]}", "explore_frontier"
        untried = [d for d in _ordered_dirs_toward_goal(pos, goal, open_dirs) if d not in tried]
        if untried:
            return f"move:{untried[0]}", "explore_untried_edge"
        self.dead_ends.add(pos)
        global_frontier = self._route_to_global_frontier(pos, goal)
        if global_frontier is not None:
            return global_frontier[0], global_frontier[2]
        parent = self.parent.get(pos)
        if parent is not None:
            direction = _direction_between(pos, parent)
            if direction:
                return f"move:{direction}", "backtrack_parent"
        return "inspect", "search_exhausted_no_submit"

    def public(self, pos: tuple[int, int], goal: tuple[int, int], path: list[tuple[int, int]]) -> dict[str, Any]:
        action, reason = self.next_action(pos, goal)
        open_dirs = sorted(self.open_seen.get(pos, set()))
        tried_dirs = sorted(self.tried.get(pos, set()))
        tried_set = set(tried_dirs)
        untried = [d for d in _ordered_dirs_toward_goal(pos, goal, set(open_dirs)) if d not in tried_set]
        frontier_here = self._frontier_dirs(pos, goal)
        parent = self.parent.get(pos)
        visits_here = path.count(pos)
        repeated_tail = len(path) >= 5 and len(set(path[-5:])) <= 2
        best_before = min((abs(cell[0] - goal[0]) + abs(cell[1] - goal[1]) for cell in path[:-1]), default=10**9)
        now_dist = abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])
        stagnant = bool(path[:-1] and now_dist >= best_before and visits_here >= 2)
        frontier_count = 0
        global_frontier = self._route_to_global_frontier(pos, goal)
        for known_pos, known_dirs in self.open_seen.items():
            tried = self.tried.get(known_pos, set())
            frontier_count += sum(
                1
                for direction in known_dirs
                if direction not in tried and self._is_frontier_neighbor(known_pos, direction, goal)
            )
        return {
            "open_dirs": open_dirs,
            "tried_dirs_here": tried_dirs,
            "untried_dirs_here": untried,
            "frontier_dirs_here": frontier_here,
            "known_cell_count": len(self.open_seen),
            "frontier_untried_count": frontier_count,
            "global_frontier_action": global_frontier[0] if global_frontier else None,
            "global_frontier_target": list(global_frontier[1]) if global_frontier else None,
            "global_frontier_reason": global_frontier[2] if global_frontier else None,
            "parent": list(parent) if parent else None,
            "backtrack_candidate": f"move:{_direction_between(pos, parent)}" if parent else None,
            "visits_to_current_cell": visits_here,
            "current_cell_seen_before": visits_here > 1,
            "revisit_warning": visits_here >= 3 or repeated_tail,
            "stagnation_warning": stagnant,
            "dead_end_count": len(self.dead_ends),
            "recommended_action": action,
            "suggested_action": action,
            "recommendation_reason": reason,
            "suggestion_reason": reason,
        }

    def _is_frontier_neighbor(self, pos: tuple[int, int], direction: str, goal: tuple[int, int]) -> bool:
        dx, dy = DIRS[direction]
        nxt = (pos[0] + dx, pos[1] + dy)
        return nxt == goal or nxt not in self.open_seen

    def _frontier_dirs(self, pos: tuple[int, int], goal: tuple[int, int]) -> list[str]:
        open_dirs = self.open_seen.get(pos, set())
        tried = self.tried.get(pos, set())
        return [
            d
            for d in _ordered_dirs_toward_goal(pos, goal, open_dirs)
            if d not in tried and self._is_frontier_neighbor(pos, d, goal)
        ]

    def _route_to_global_frontier(
        self,
        pos: tuple[int, int],
        goal: tuple[int, int],
    ) -> tuple[str, tuple[int, int], str] | None:
        targets = {cell for cell in self.open_seen if self._frontier_dirs(cell, goal)}
        if goal in self.open_seen and goal != pos:
            targets.add(goal)
        targets.discard(pos)
        if not targets:
            return None
        queue: list[tuple[int, int]] = [pos]
        prev: dict[tuple[int, int], tuple[int, int] | None] = {pos: None}
        for cell in queue:
            if cell in targets:
                first = cell
                while prev[first] is not None and prev[first] != pos:
                    first = prev[first]  # type: ignore[assignment]
                direction = _direction_between(pos, first)
                if direction:
                    reason = "route_to_known_goal" if cell == goal else "route_to_global_frontier"
                    return f"move:{direction}", cell, reason
                continue
            for direction in _ordered_dirs_toward_goal(cell, goal, self.open_seen.get(cell, set())):
                dx, dy = DIRS[direction]
                nxt = (cell[0] + dx, cell[1] + dy)
                if nxt in self.open_seen and nxt not in prev:
                    prev[nxt] = cell
                    queue.append(nxt)
        return None


async def run_maze_agent(
    task: MazeTask,
    *,
    agent_id: int,
    insights: list[dict[str, Any]],
    cfg: Config,
    llm: LLMClient,
    peer_summaries: list[str] | None = None,
    t: int = 0,
) -> AgentRouteResult:
    if cfg.maze_agent_mode == "oracle_dfs":
        return _run_oracle_maze_agent(task, agent_id=agent_id, insights=insights)

    env = MazeEnv()
    obs = env.reset(task)
    trace: list[dict[str, Any]] = []
    search = MazeSearchState() if _uses_search_state(cfg.maze_agent_mode) else None
    peer_block = ""
    if peer_summaries:
        peer_block = "PEER LAST-EPISODE SUMMARIES:\n" + "\n".join(peer_summaries[-cfg.n_solvers:]) + "\n\n"

    for step in range(cfg.max_steps):
        search_block = ""
        search_state: dict[str, Any] = {}
        recommended_action = ""
        if search is not None and env.task is not None:
            search.update_observation(env.pos, obs, env.path)
            search_state = _search_public(search, env)
            recommended_action = str(search_state["recommended_action"])
            search_block = (
                "SEARCH STATE:\n"
                + json.dumps(search_state, ensure_ascii=False, sort_keys=True)
                + "\n"
                + _search_instruction(cfg.maze_agent_mode)
                + "\n"
            )
        prompt = (
            f"AGENT ID: {agent_id}\n\n"
            f"TOOLS:\n{env.tools_doc()}\n\n"
            f"REUSABLE EXPERIENCE:\n{render_library(insights)}\n\n"
            f"{peer_block}"
            f"{search_block}"
            f"HISTORY:\n{_trace_summary(trace)}\n\n"
            f"OBSERVATION:\n{obs}\n\n"
            "Choose the next action. Do not output a coordinate-specific memorized route. "
            "Finish with exactly one line: Action: <tool call>."
        )
        out = await llm.chat(
            [{"role": "system", "content": MAZE_AGENT_SYS}, {"role": "user", "content": prompt}],
            temp=cfg.solver_temp,
            max_tokens=cfg.max_tokens_solver,
            tag=f"maze_agent:{agent_id}",
            cache_salt=_solver_cache_salt(cfg, t=t, task_id=task.task_id, agent_id=agent_id, step=step),
        )
        model_action = parse_action(out)
        action = model_action
        override = False
        override_reason = ""
        if search is not None and cfg.maze_agent_mode == "stateful_dfs":
            action = _controlled_dfs_action(model_action, recommended_action)
            override = action != model_action
            override_reason = "stateful_dfs_controller" if override else ""
        elif search is not None and cfg.maze_agent_mode == "state_guided":
            action, override, override_reason = _state_guided_action(model_action, recommended_action)
        before = env.pos
        obs2, done, info = env.step(action)
        if search is not None:
            search.mark_transition(before, str(info.get("normalized_action") or action), env.pos, bool(info.get("invalid")))
        trace.append(
            {
                "step": step,
                "prompt_observation": obs,
                "raw": out,
                "model_action": model_action,
                "action": action,
                "controller_action": action,
                "search_state": search_state,
                "state_guided_override": bool(override and cfg.maze_agent_mode == "state_guided"),
                "state_guided_override_reason": override_reason if cfg.maze_agent_mode == "state_guided" else "",
                "normalized_action": info.get("normalized_action"),
                "observation": obs2,
                "position": list(env.pos),
                "invalid": bool(info.get("invalid")),
            }
        )
        obs = obs2
        if done:
            break
    route = env.route_record()
    _add_route_eval_fields(route, task=task, max_steps=cfg.max_steps, agent_mode=cfg.maze_agent_mode, trace=trace)
    return AgentRouteResult(agent_id=agent_id, route=route, trace=trace, retrieved=insights)


async def run_maze_episode(
    task: MazeTask,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    *,
    audit: MazeMemoryAudit,
    t: int,
    peer_summaries: list[str] | None = None,
) -> MazeEpisodeResult:
    retrieved_by_agent = [memory.retrieve(agent_id, _agent_query(task), t=t) for agent_id in range(cfg.n_solvers)]
    for agent_id, items in enumerate(retrieved_by_agent):
        audit.record_retrieval(t=t, task_id=task.task_id, agent_id=agent_id, items=items)
    if cfg.maze_agent_mode == "oracle_dfs":
        return MazeEpisodeResult(
            task_id=task.task_id,
            task=task,
            agents=[
                _run_oracle_maze_agent(task, agent_id=agent_id, insights=retrieved_by_agent[agent_id])
                for agent_id in range(cfg.n_solvers)
            ],
        )
    envs = [MazeEnv() for _ in range(cfg.n_solvers)]
    observations = [env.reset(task) for env in envs]
    traces: list[list[dict[str, Any]]] = [[] for _ in range(cfg.n_solvers)]
    done = [False for _ in range(cfg.n_solvers)]
    searches = [MazeSearchState() for _ in range(cfg.n_solvers)] if _uses_search_state(cfg.maze_agent_mode) else []
    peer_summaries = peer_summaries or []

    async def propose(agent_id: int, peer_actions: list[str], step: int) -> dict[str, Any]:
        env = envs[agent_id]
        search = searches[agent_id] if searches else None
        search_state: dict[str, Any] = {}
        recommended_action = ""
        if search is not None and env.task is not None:
            search.update_observation(env.pos, observations[agent_id], env.path)
            search_state = _search_public(search, env)
            recommended_action = str(search_state.get("recommended_action", ""))
        prompt = _maze_step_prompt(
            env,
            observations[agent_id],
            traces[agent_id],
            retrieved_by_agent[agent_id],
            agent_id,
            peer_actions,
            peer_summaries,
            search_state=search_state,
            agent_mode=cfg.maze_agent_mode,
        )
        out = await llm.chat(
            [{"role": "system", "content": MAZE_AGENT_SYS}, {"role": "user", "content": prompt}],
            temp=cfg.solver_temp,
            max_tokens=cfg.max_tokens_solver,
            tag=f"maze_agent:{agent_id}",
            cache_salt=_solver_cache_salt(cfg, t=t, task_id=task.task_id, agent_id=agent_id, step=step),
        )
        model_action = parse_action(out)
        action = model_action
        override = False
        override_reason = ""
        if search is not None and cfg.maze_agent_mode == "stateful_dfs":
            action = _controlled_dfs_action(model_action, recommended_action)
            override = action != model_action
            override_reason = "stateful_dfs_controller" if override else ""
        elif search is not None and cfg.maze_agent_mode == "state_guided":
            action, override, override_reason = _state_guided_action(model_action, recommended_action)
        return {
            "raw": out,
            "model_action": model_action,
            "action": action,
            "controller_action": action,
            "search_state": search_state,
            "state_guided_override": bool(override and cfg.maze_agent_mode == "state_guided"),
            "state_guided_override_reason": override_reason if cfg.maze_agent_mode == "state_guided" else "",
        }

    for step in range(cfg.max_steps):
        active = [idx for idx, flag in enumerate(done) if not flag]
        if not active:
            break
        proposals = ["" for _ in range(cfg.n_solvers)]
        proposal_meta: list[dict[str, Any]] = [{} for _ in range(cfg.n_solvers)]
        first = await asyncio.gather(*[propose(agent_id, [], step) for agent_id in active])
        for agent_id, item in zip(active, first, strict=True):
            proposals[agent_id] = str(item["action"])
            proposal_meta[agent_id] = item
        for _round in range(2, cfg.debate_rounds + 1):
            revised = await asyncio.gather(*[propose(agent_id, proposals, step) for agent_id in active])
            for agent_id, item in zip(active, revised, strict=True):
                proposals[agent_id] = str(item["action"])
                proposal_meta[agent_id] = item
        for agent_id in active:
            env = envs[agent_id]
            search = searches[agent_id] if searches else None
            meta = proposal_meta[agent_id]
            obs_before = observations[agent_id]
            before = env.pos
            obs_after, terminal, info = env.step(proposals[agent_id])
            if search is not None:
                search.mark_transition(before, str(info.get("normalized_action") or proposals[agent_id]), env.pos, bool(info.get("invalid")))
            traces[agent_id].append(
                {
                    "step": step,
                    "prompt_observation": obs_before,
                    "raw": meta.get("raw", ""),
                    "model_action": meta.get("model_action", proposals[agent_id]),
                    "action": proposals[agent_id],
                    "controller_action": proposals[agent_id],
                    "search_state": meta.get("search_state", {}),
                    "state_guided_override": bool(meta.get("state_guided_override")),
                    "state_guided_override_reason": meta.get("state_guided_override_reason", ""),
                    "normalized_action": info.get("normalized_action"),
                    "observation": obs_after,
                    "position": list(env.pos),
                    "invalid": bool(info.get("invalid")),
                    "peer_actions": [
                        {"agent_id": pid, "action": act}
                        for pid, act in enumerate(proposals)
                        if pid != agent_id and act
                    ],
                }
            )
            observations[agent_id] = obs_after
            done[agent_id] = terminal

    agents: list[AgentRouteResult] = []
    for agent_id, env in enumerate(envs):
        route = env.route_record()
        _add_route_eval_fields(route, task=task, max_steps=cfg.max_steps, agent_mode=cfg.maze_agent_mode, trace=traces[agent_id])
        agents.append(
            AgentRouteResult(
                agent_id=agent_id,
                route=route,
                trace=traces[agent_id],
                retrieved=retrieved_by_agent[agent_id],
            )
        )
    return MazeEpisodeResult(task_id=task.task_id, task=task, agents=agents)


def _maze_step_prompt(
    env: MazeEnv,
    obs: str,
    trace: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    agent_id: int,
    peer_actions: list[str],
    peer_summaries: list[str],
    *,
    search_state: dict[str, Any] | None = None,
    agent_mode: str = "prompt_only",
) -> str:
    peer_block = ""
    if peer_actions:
        peer_lines = [f"- Agent {pid}: {act}" for pid, act in enumerate(peer_actions) if pid != agent_id and act]
        peer_block = "PEER PROPOSED ACTIONS THIS STEP:\n" + ("\n".join(peer_lines) if peer_lines else "(none)") + "\n\n"
    summary_block = ""
    if peer_summaries:
        summary_block = "PEER LAST-EPISODE SUMMARIES:\n" + "\n".join(peer_summaries[-4:]) + "\n\n"
    search_block = ""
    if search_state:
        search_block = (
            "SEARCH STATE:\n"
            + json.dumps(search_state, ensure_ascii=False, sort_keys=True)
            + "\n"
            + _search_instruction(agent_mode)
            + "\n"
        )
    return (
        f"AGENT ID: {agent_id}\n\n"
        f"TOOLS:\n{env.tools_doc()}\n\n"
        f"REUSABLE EXPERIENCE:\n{render_library(insights)}\n\n"
        f"{summary_block}"
        f"{search_block}"
        f"HISTORY:\n{_trace_summary(trace)}\n\n"
        f"OBSERVATION:\n{obs}\n\n"
        f"{peer_block}"
        "Choose the next action for your own maze copy. Do not output a coordinate-specific memorized route. "
        "Use systematic exploration: prefer unvisited open directions; if all open directions were recently visited, "
        "backtrack toward the most recent cell with an untried open direction; do not alternate between the same two cells more than once. "
        "If the observation says Manhattan distance is 0, your next action must be submit. "
        "Finish with exactly one line: Action: <tool call>."
    )


def maze_batch_metrics(episodes: list[MazeEpisodeResult], *, baseline_cost_ratio: float | None = None) -> dict[str, float]:
    routes = [agent.route for ep in episodes for agent in ep.agents]
    if not routes:
        return {
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "cost_ratio": 0.0,
            "excess_steps": 0.0,
            "success_excess_steps": 0.0,
            "n_success": 0.0,
            "invalid_move_rate": 0.0,
            "loop_rate": 0.0,
            "stagnation_rate": 0.0,
            "revisit_max": 0.0,
            "state_guided_override_count": 0.0,
            "state_guided_override_rate": 0.0,
            "route_diversity": 0.0,
            "route_diversity_efficient": 0.0,
            "route_diversity_efficient_n": 0.0,
            "mas_antmill_rate": 0.0,
            "efficiency_collapse_signal": 0.0,
        }
    mean = lambda xs: float(sum(xs) / len(xs)) if xs else 0.0
    per_episode_overlap = [_episode_route_diversity(ep) for ep in episodes]
    loop_by_ep = []
    for ep in episodes:
        loops = sum(1 for a in ep.agents if a.route.get("looped"))
        same_route = _episode_route_diversity(ep) <= 0.5
        loop_by_ep.append(1.0 if loops >= max(1, math.ceil(len(ep.agents) / 2)) and same_route else 0.0)
    success = mean([1.0 if r.get("success") else 0.0 for r in routes])
    cost = mean([float(r.get("cost_ratio") or 0.0) for r in routes])
    loop = mean([1.0 if r.get("looped") else 0.0 for r in routes])
    diversity = mean(per_episode_overlap)
    success_routes = [r for r in routes if r.get("success")]
    efficient_divs = [d for d in (_episode_route_diversity_efficient(ep) for ep in episodes) if d is not None]
    baseline = baseline_cost_ratio if baseline_cost_ratio is not None else cost
    collapse_signal = 1.0 if cost > baseline * 1.15 and loop >= 0.25 and diversity <= 0.5 else 0.0
    return {
        "success_rate": success,
        "failure_rate": 1.0 - success,
        "cost_ratio": cost,
        "excess_steps": mean([float(r.get("excess_steps") or 0.0) for r in routes]),
        # Success-conditional efficiency: failures carry a capped-step penalty in
        # cost_ratio/excess_steps, which entangles "slower" with "failed".
        "success_excess_steps": mean([float(r.get("excess_steps") or 0.0) for r in success_routes]),
        "n_success": float(len(success_routes)),
        "invalid_move_rate": mean([float(r.get("invalid_move_rate") or 0.0) for r in routes]),
        "loop_rate": loop,
        "stagnation_rate": mean([float(r.get("stagnation_rate") or 0.0) for r in routes]),
        "revisit_max": mean([float(r.get("revisit_max") or 0.0) for r in routes]),
        "state_guided_override_count": mean([float(r.get("state_guided_override_count") or 0.0) for r in routes]),
        "state_guided_override_rate": mean([float(r.get("state_guided_override_rate") or 0.0) for r in routes]),
        "route_diversity": diversity,
        "route_diversity_efficient": mean(efficient_divs),
        "route_diversity_efficient_n": float(len(efficient_divs)),
        "mas_antmill_rate": mean(loop_by_ep),
        "efficiency_collapse_signal": collapse_signal,
    }


def _episode_route_diversity(ep: MazeEpisodeResult) -> float:
    paths = [tuple(tuple(cell) for cell in a.route.get("path", [])) for a in ep.agents]
    if len(paths) <= 1:
        return 0.0
    sims = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            set_i = set(paths[i])
            set_j = set(paths[j])
            sims.append(len(set_i & set_j) / max(len(set_i | set_j), 1))
    return 1.0 - float(sum(sims) / len(sims))


def _episode_route_diversity_efficient(ep: MazeEpisodeResult, *, max_cost: float = 2.5) -> float | None:
    """Route diversity among efficient successful routes only.

    Plain visited-cell diversity is confounded with efficiency: inefficient
    wandering inflates it. Conditioning on success and cost <= max_cost isolates
    genuine homogenization. None when fewer than 2 routes qualify.
    """
    cells = [
        set(tuple(cell) for cell in a.route.get("path", []))
        for a in ep.agents
        if a.route.get("success") and float(a.route.get("cost_ratio") or 0.0) <= max_cost
    ]
    if len(cells) < 2:
        return None
    sims = []
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            sims.append(len(cells[i] & cells[j]) / max(len(cells[i] | cells[j]), 1))
    return 1.0 - float(sum(sims) / len(sims))


def _retrieval_counts(items: list[dict[str, Any]]) -> list[int]:
    return [int(item.get("retrieval_count", 0)) for item in items if int(item.get("retrieval_count", 0)) > 0]


def retrieval_top1_share(items: list[dict[str, Any]]) -> float:
    """Share of retrievals going to the single most-retrieved item.

    Deprecated as a mechanism variable: max/total is a deterministic function of
    pool size (a 1-item pool scores 1.0 by construction). Kept for continuity
    with earlier runs; use retrieval_entropy_norm for mechanism claims.
    """
    counts = _retrieval_counts(items)
    total = sum(counts)
    if total <= 0:
        return 0.0
    return max(counts) / total


def retrieval_concentration(items: list[dict[str, Any]]) -> float:
    """Deprecated alias of retrieval_top1_share."""
    return retrieval_top1_share(items)


def retrieval_entropy_norm(items: list[dict[str, Any]]) -> float:
    """Normalized Shannon entropy of the retrieval-count distribution, in [0, 1].

    0 = all retrievals concentrate on one item; 1 = uniform spread across the
    retrieved items. Unlike max/total, this is comparable across pool sizes.
    """
    counts = _retrieval_counts(items)
    total = sum(counts)
    if total <= 0 or len(counts) <= 1:
        return 0.0
    probs = [count / total for count in counts]
    entropy = -sum(p * math.log(p) for p in probs)
    return entropy / math.log(len(counts))


def memory_effective_size(items: list[dict[str, Any]]) -> float:
    """exp(entropy) of the retrieval distribution: effective number of used memories."""
    counts = _retrieval_counts(items)
    total = sum(counts)
    if total <= 0:
        return 0.0
    probs = [count / total for count in counts]
    return math.exp(-sum(p * math.log(p) for p in probs))


async def write_maze_experience(
    episode: MazeEpisodeResult,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    *,
    audit: MazeMemoryAudit,
    t: int,
    write_mode: str,
) -> None:
    if memory.mode == "none" or write_mode == "none":
        return
    write_mode = _canonical_write_mode(write_mode)
    # "scripted" / "scripted_gated" inject fixed researcher-written templates. They are
    # upper-bound injection controls for what one globally shared strategy text can do;
    # they are NOT learned experience and must not be read as an experience-writing arm.
    if write_mode == "scripted":
        for agent in episode.agents:
            insight = _scripted_insight(agent.route)
            support = cfg.n_solvers if agent.success else max(0, cfg.n_solvers // 2)
            _apply_maze_insight(memory, audit, insight, episode, agent.agent_id, cfg, t, write_mode, support)
        return

    if write_mode in {"scripted_gated", "self_eval"}:
        for agent in episode.agents:
            if write_mode == "scripted_gated" and not agent.success:
                insight = _route_avoid_insight(agent.route)
                support = 0
            elif write_mode == "self_eval" and not _self_eval_route(agent.route):
                insight = _route_avoid_insight(agent.route)
                support = 0
            else:
                insight = _scripted_insight(agent.route)
                support = cfg.n_solvers
            _apply_maze_insight(memory, audit, insight, episode, agent.agent_id, cfg, t, write_mode, support)
        return

    if write_mode == "reviewer" and cfg.memory_write_protocol == "expel_ops":
        # ExpeL-faithful pool evolution: the reviewer LLM sees the numbered pool and
        # issues ADD/EDIT/UPVOTE/DOWNVOTE; code executes (sanitizer as the only veto).
        if memory.mode == "private":
            for agent in episode.agents:
                agent_episode = MazeEpisodeResult(task_id=episode.task_id, task=episode.task, agents=[agent])
                await _write_experience_ops(agent_episode, memory, cfg, llm, audit=audit, t=t, agent_id=agent.agent_id)
        else:
            await _write_experience_ops(episode, memory, cfg, llm, audit=audit, t=t, agent_id=0)
        return

    if memory.mode == "private":
        for agent in episode.agents:
            agent_episode = MazeEpisodeResult(task_id=episode.task_id, task=episode.task, agents=[agent])
            rejects: list[dict[str, str]] = []
            insights = await distill_expel_insights(
                _maze_expel_episodes(agent_episode), MAZE_EXPEL_ADAPTER, cfg, llm, reject_log=rejects
            )
            _record_rejects(audit, rejects, episode=episode, t=t, write_mode=write_mode)
            agent_support = cfg.n_solvers if agent.success else 0
            for insight in insights[:4]:
                _apply_maze_insight(memory, audit, insight, episode, agent.agent_id, cfg, t, write_mode, agent_support)
        return

    rejects = []
    insights = await distill_expel_insights(
        _maze_expel_episodes(episode), MAZE_EXPEL_ADAPTER, cfg, llm, reject_log=rejects
    )
    _record_rejects(audit, rejects, episode=episode, t=t, write_mode=write_mode)
    support = sum(1 for agent in episode.agents if agent.success)
    for insight in insights[:4]:
        _apply_maze_insight(memory, audit, insight, episode, 0, cfg, t, write_mode, support)


async def _write_experience_ops(
    episode: MazeEpisodeResult,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    *,
    audit: MazeMemoryAudit,
    t: int,
    agent_id: int,
) -> None:
    pool = memory.pool_view(agent_id)
    ops = await propose_memory_ops(pool, _maze_expel_episodes(episode), MAZE_EXPEL_ADAPTER, cfg, llm)
    rejects: list[dict[str, str]] = []
    new_pool, applied = apply_memory_ops(pool, ops, cfg=cfg, reject_log=rejects)
    memory.set_pool(agent_id, new_pool)
    for item in rejects:
        audit.record_rejection(
            t=t,
            task_id=episode.task_id,
            write_mode=f"reviewer_ops:{item.get('op', '?')}",
            text=item.get("text", ""),
            reason=item.get("reason", "over_specific"),
        )
    quality = _episode_quality(episode, agent_id)
    for op in applied:
        item = op["item"]
        if op["op"] in {"ADD", "EDIT"}:
            item["last_access_t"] = t
        audit.record_write(
            t=t,
            task_id=episode.task_id,
            agent_id=agent_id,
            insight=item,
            support_count=int(item.get("votes", 0)),
            write_mode=f"reviewer_ops:{op['op']}",
            quality=quality,
        )


def _record_rejects(
    audit: MazeMemoryAudit,
    rejects: list[dict[str, str]],
    *,
    episode: MazeEpisodeResult,
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


def _apply_maze_insight(
    memory: InsightMemory,
    audit: MazeMemoryAudit,
    insight: dict[str, Any],
    episode: MazeEpisodeResult,
    agent_id: int,
    cfg: Config,
    t: int,
    write_mode: str,
    support_count: int,
) -> None:
    quality = _episode_quality(episode, agent_id)
    original_text = str(insight.get("text", ""))
    insight = _sanitize_insight(insight)
    if not insight.get("text"):
        audit.record_rejection(
            t=t, task_id=episode.task_id, write_mode=write_mode, text=original_text, reason="over_specific"
        )
        return
    audit.record_write(
        t=t,
        task_id=episode.task_id,
        agent_id=agent_id,
        insight=insight,
        support_count=support_count,
        write_mode=write_mode,
        quality=quality,
    )
    insight.setdefault("last_access_t", t)
    memory.apply_insight(agent_id, insight, support_count=support_count)


def _episode_quality(episode: MazeEpisodeResult, agent_id: int) -> dict[str, Any]:
    agent = next((a for a in episode.agents if a.agent_id == agent_id), episode.agents[0])
    route = agent.route
    return {
        "success": route.get("success"),
        "steps": route.get("steps"),
        "cost_ratio": route.get("cost_ratio"),
        "invalid_moves": route.get("invalid_moves"),
        "revisit_max": route.get("revisit_max"),
        "stagnation_rate": route.get("stagnation_rate"),
        "looped": route.get("looped"),
    }


def _canonical_write_mode(write_mode: str) -> str:
    return {"direct": "scripted", "oracle": "scripted_gated"}.get(write_mode, write_mode)


def _scripted_insight(route: dict[str, Any]) -> dict[str, str]:
    """Fixed researcher-written template (scripted-injection control), not learned experience."""
    if route.get("success") and not route.get("looped") and float(route.get("invalid_move_rate") or 0.0) <= 0.25:
        return {
            "kind": "do",
            "text": "Prefer actions that keep reducing distance while avoiding revisits; submit immediately once the goal is reached.",
        }
    if route.get("looped"):
        return {
            "kind": "avoid",
            "text": "Avoid repeating a correction pattern after returning to the same cell; switch to an unvisited open direction instead.",
        }
    return {
        "kind": "do",
        "text": "When progress stalls, inspect the local exits and choose an open direction that has not appeared in the recent path.",
    }


def _route_avoid_insight(route: dict[str, Any]) -> dict[str, str]:
    if route.get("looped"):
        return {
            "kind": "avoid",
            "text": "Avoid alternating between the same small set of cells; treat repeated visits as a signal to change exploration policy.",
        }
    return {
        "kind": "avoid",
        "text": "Avoid continuing a long route with no successful submit; reassess open directions and recent revisits before moving again.",
    }


def _self_eval_route(route: dict[str, Any]) -> bool:
    return (
        bool(route.get("success"))
        and not bool(route.get("looped"))
        and float(route.get("invalid_move_rate") or 0.0) <= 0.35
        and int(route.get("revisit_max") or 0) < 8
    )


def _maze_expel_episodes(episode: MazeEpisodeResult) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for agent in episode.agents:
        route = agent.route
        recent = agent.trace[-8:]
        trajectory = "\n".join(
            f"step {row['step']}: action={row['normalized_action']} invalid={row['invalid']} pos={row['position']}"
            for row in recent
        )
        records.append(
            {
                "episode_id": episode.task_id,
                "agent_id": agent.agent_id,
                "outcome": "success" if route.get("success") else "failure",
                "quality": {
                    "success": route.get("success"),
                    "steps": route.get("steps"),
                    "invalid_moves": route.get("invalid_moves"),
                    "revisit_max": route.get("revisit_max"),
                    "stagnation_rate": route.get("stagnation_rate"),
                    "looped": route.get("looped"),
                },
                "trajectory": trajectory,
            }
        )
    return records


def _sanitize_insight(item: dict[str, Any]) -> dict[str, str]:
    """Clean one insight; {} means rejected (dropped, never replaced with canned text)."""
    return sanitize_expel_insight(item)


def _trace_summary(trace: list[dict[str, Any]]) -> str:
    if not trace:
        return "(no actions yet)"
    return "\n".join(
        f"step {row['step']}: action={row['normalized_action']} invalid={row['invalid']} pos={row['position']}"
        for row in trace[-8:]
    )


async def run_one_maze_alpha(cfg: Config, train_tasks: list[MazeTask], heldout_tasks: list[MazeTask]) -> dict[str, Any]:
    llm = LLMClient(cfg)
    memory = InsightMemory(cfg)
    audit = MazeMemoryAudit()
    rng = random.Random(cfg.seed)
    out_dir = cfg.output_path() / condition_name(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "replays").mkdir(parents=True, exist_ok=True)
    (out_dir / "route_atlas").mkdir(parents=True, exist_ok=True)
    log: list[dict[str, Any]] = []
    heldout_records: list[dict[str, Any]] = []
    started = time.time()
    baseline_cost: float | None = None

    for t in range(cfg.T):
        heldout = await _run_task_batch(heldout_tasks[: cfg.heldout_size], memory, cfg, llm, audit=audit, t=t)
        metrics = maze_batch_metrics(heldout, baseline_cost_ratio=baseline_cost)
        if t == 0:
            baseline_cost = metrics["cost_ratio"]
        pool_items = memory.all_items()
        metrics["memory_size"] = memory.size()
        metrics["retrieval_concentration"] = retrieval_concentration(pool_items)
        metrics["retrieval_top1_share"] = retrieval_top1_share(pool_items)
        metrics["retrieval_entropy_norm"] = retrieval_entropy_norm(pool_items)
        metrics["memory_effective_size"] = memory_effective_size(pool_items)
        metrics["sanitizer_reject_count"] = len(audit.rejections)
        row = {
            "t": t,
            **metrics,
            "tokens_total_so_far": llm.stats.total_tokens,
            "cache_hits_so_far": llm.stats.cache_hits,
            "network_calls_so_far": llm.stats.network_calls,
        }
        log.append(row)
        heldout_records.append({"t": t, "episodes": [ep.public(include_trace=True) for ep in heldout]})
        write_route_atlas(heldout[: min(len(heldout), 12)], out_dir / "route_atlas" / f"t_{t:02d}.png")
        print(
            f"[{condition_name(cfg)}] t={t:02d} success={row['success_rate']:.3f} "
            f"cost={row['cost_ratio']:.3f} loop={row['loop_rate']:.3f} div={row['route_diversity']:.3f} "
            f"mem={memory.size()} tokens={llm.stats.total_tokens}",
            flush=True,
        )

        should_train = cfg.batch_M and cfg.memory_mode != "none" and not (cfg.skip_final_train and t == cfg.T - 1)
        if should_train:
            batch = _sample_train_batch(train_tasks, cfg.batch_M, t, rng)
            train_eps = await _run_task_batch(batch, memory, cfg, llm, audit=audit, t=t)
            for ep in train_eps:
                await write_maze_experience(
                    ep,
                    memory,
                    cfg,
                    llm,
                    audit=audit,
                    t=t,
                    write_mode=cfg.maze_write_mode,
                )

        partial = {"config": cfg.to_public_dict(), "log": log, "memory": memory.snapshot(), "audit": audit.public(memory)}
        _write_json(out_dir / "partial.json", partial)

    summary = {
        "condition": condition_name(cfg),
        "memory_mode": cfg.memory_mode,
        "maze_agent_mode": cfg.maze_agent_mode,
        "maze_write_mode": cfg.maze_write_mode,
        "n_solvers": cfg.n_solvers,
        "success_final": log[-1]["success_rate"] if log else 0.0,
        "cost_final": log[-1]["cost_ratio"] if log else 0.0,
        "cost_peak": max((row["cost_ratio"] for row in log), default=0.0),
        "loop_final": log[-1]["loop_rate"] if log else 0.0,
        "route_diversity_final": log[-1]["route_diversity"] if log else 0.0,
        "efficiency_collapse_rounds": sum(int(row["efficiency_collapse_signal"]) for row in log),
        "retrieval_concentration_final": log[-1]["retrieval_concentration"] if log else 0.0,
        "llm": llm.stats.public_summary(),
        "elapsed_sec": time.time() - started,
    }
    result = {
        "config": cfg.to_public_dict(),
        "log": log,
        "summary": summary,
        "memory": memory.snapshot(),
        "memory_audit": audit.public(memory),
        "heldout_records": heldout_records,
    }
    _write_json(out_dir / "result.json", result)
    _write_json(out_dir / "memory_audit.json", audit.public(memory))
    write_replay_html(result, out_dir / "replays" / "index.html")
    plot_maze_curves(result, out_dir / "curves.png")
    return result


async def _run_task_batch(
    tasks: list[MazeTask],
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
    *,
    audit: MazeMemoryAudit,
    t: int,
) -> list[MazeEpisodeResult]:
    sem = asyncio.Semaphore(cfg.concurrency)

    async def run(task: MazeTask) -> MazeEpisodeResult:
        async with sem:
            return await run_maze_episode(task, memory, cfg, llm, audit=audit, t=t)

    return list(await asyncio.gather(*[run(task) for task in tasks]))


def _sample_train_batch(tasks: list[MazeTask], batch_size: int, t: int, rng: random.Random) -> list[MazeTask]:
    if batch_size >= len(tasks):
        return list(tasks)
    start = (t * batch_size) % len(tasks)
    batch = tasks[start:start + batch_size]
    if len(batch) < batch_size:
        batch += tasks[: batch_size - len(batch)]
    # Keep deterministic coverage but shuffle order to avoid prompt-cache artifacts.
    batch = list(batch)
    rng.shuffle(batch)
    return batch


def build_maze_alpha_configs(args: argparse.Namespace) -> list[Config]:
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    arms = _arms_for_phase(args.phase)
    run_id_filter = {item.strip() for item in getattr(args, "run_id_filter", "").split(",") if item.strip()}
    if run_id_filter:
        arms = [arm for arm in arms if str(arm.get("run_id", "")) in run_id_filter]
        if not arms:
            raise ValueError(f"run_id_filter matched no arms: {sorted(run_id_filter)}")
    configs: list[Config] = []
    for seed in seeds:
        for arm in arms:
            params = {
                "model": args.model or Config.model,
                "base_url": args.base_url or Config.base_url,
                "api_key_env": args.api_key_env or Config.api_key_env,
                "out_dir": args.out_dir,
                "cache_dir": args.cache_dir,
                "seed": seed,
                "dataset": "tau_bench",
                "T": args.T,
                "batch_M": args.train_batch,
                "n_train": max(args.train_size, args.train_batch * args.T),
                "heldout_size": args.heldout_size,
                "concurrency": args.concurrency,
                "rate_limit_per_min": args.rpm,
                "max_steps": args.max_steps,
                "debate_rounds": args.debate_rounds,
                "retrieval_k": args.retrieval_k,
                "library_cap": args.library_cap,
                "solver_temp": args.solver_temp,
                "max_tokens_solver": args.max_tokens_solver,
                "max_tokens_reviewer": args.max_tokens_reviewer,
                "skip_final_train": args.skip_final_train,
                "maze_width": args.maze_width,
                "maze_height": args.maze_height,
                "maze_family": args.maze_family,
                "maze_agent_mode": args.maze_agent_mode,
                "maze_min_shortest": args.maze_min_shortest,
                "maze_max_shortest": args.maze_max_shortest,
                "memory_write_protocol": getattr(args, "write_protocol", "distill"),
                "retrieval_scoring": getattr(args, "retrieval_scoring", "similarity"),
                "ga_lambda": getattr(args, "ga_lambda", 1.0),
                "ga_recency": getattr(args, "ga_recency", 0.0),
            }
            params.update(arm)
            configs.append(Config(**params))
    return configs


def _arms_for_phase(phase: str) -> list[dict[str, Any]]:
    if phase == "debug":
        return [
            {"run_id": "maze_debug_single_nomem", "n_solvers": 1, "memory_mode": "none", "maze_write_mode": "none"},
        ]
    if phase == "single":
        return [
            {"run_id": "maze_single_nomem", "n_solvers": 1, "memory_mode": "none", "maze_write_mode": "none"},
            {"run_id": "maze_single_reviewer", "n_solvers": 1, "memory_mode": "shared", "maze_write_mode": "reviewer"},
            {"run_id": "maze_single_scripted_gated", "n_solvers": 1, "memory_mode": "shared", "maze_write_mode": "scripted_gated"},
            {"run_id": "maze_single_self_eval", "n_solvers": 1, "memory_mode": "shared", "maze_write_mode": "self_eval"},
            {
                "run_id": "maze_single_frozen_reviewer",
                "n_solvers": 1,
                "memory_mode": "frozen",
                "maze_write_mode": "reviewer",
            },
            {
                "run_id": "maze_single_frozen_scripted_gated",
                "n_solvers": 1,
                "memory_mode": "frozen",
                "maze_write_mode": "scripted_gated",
            },
        ]
    if phase == "single_expel_pilot":
        return [
            {"run_id": "single_nomem_state_guided", "n_solvers": 1, "memory_mode": "none", "maze_write_mode": "none"},
            {"run_id": "single_expel_reviewer", "n_solvers": 1, "memory_mode": "shared", "maze_write_mode": "reviewer"},
        ]
    if phase in {"mas_nomem", "mad"}:  # "mad" is a deprecated alias; no debate happens at debate_rounds=1
        return [
            {"run_id": "maze_single_nomem", "n_solvers": 1, "memory_mode": "none", "maze_write_mode": "none"},
            {"run_id": "maze_mas_nomem", "n_solvers": 4, "memory_mode": "none", "maze_write_mode": "none"},
        ]
    if phase == "core":
        return [
            {"run_id": "maze_mas_private_reviewer", "n_solvers": 4, "memory_mode": "private", "maze_write_mode": "reviewer"},
            {"run_id": "maze_mas_shared_reviewer", "n_solvers": 4, "memory_mode": "shared", "maze_write_mode": "reviewer"},
            {"run_id": "maze_mas_shared_scripted_gated", "n_solvers": 4, "memory_mode": "shared", "maze_write_mode": "scripted_gated"},
            {"run_id": "maze_mas_frozen_reviewer", "n_solvers": 4, "memory_mode": "frozen", "maze_write_mode": "reviewer"},
            {"run_id": "maze_mas_shared_scripted", "n_solvers": 4, "memory_mode": "shared", "maze_write_mode": "scripted"},
        ]
    if phase == "smoke":
        return [
            {"run_id": "maze_smoke_single_nomem", "n_solvers": 1, "memory_mode": "none", "maze_write_mode": "none"},
            {"run_id": "maze_smoke_shared_scripted", "n_solvers": 3, "memory_mode": "shared", "maze_write_mode": "scripted"},
        ]
    raise ValueError(f"unknown maze phase {phase!r}")


def write_replay_html(result: dict[str, Any], path: Path) -> Path:
    data = json.dumps(result.get("heldout_records", []), ensure_ascii=False)
    content = f"""<!doctype html>
<meta charset="utf-8">
<title>Maze Alpha Replay</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 20px; }}
.grid {{ display: grid; gap: 2px; margin: 12px 0; width: max-content; }}
.cell {{ width: 24px; height: 24px; border: 1px solid #ddd; text-align: center; line-height: 24px; font-size: 12px; }}
.wall {{ background: #222; border-color: #222; }}
.start {{ background: #7dd3fc; }}
.goal {{ background: #86efac; }}
.path0 {{ background: #fca5a5; }}
.path1 {{ background: #fdba74; }}
.path2 {{ background: #c4b5fd; }}
.path3 {{ background: #f9a8d4; }}
button, select {{ margin-right: 8px; }}
pre {{ max-width: 960px; white-space: pre-wrap; background: #f6f6f6; padding: 10px; }}
</style>
<h1>Maze Alpha Replay</h1>
<div>
<label>round <select id="round"></select></label>
<label>episode <select id="episode"></select></label>
<button id="prev">Prev</button><button id="next">Next</button>
<span id="step"></span>
</div>
<div id="grid"></div>
<pre id="details"></pre>
<script>
const records = {data};
let roundIdx = 0, episodeIdx = 0, step = 0;
const roundSel = document.getElementById('round');
const epSel = document.getElementById('episode');
const gridEl = document.getElementById('grid');
const details = document.getElementById('details');
for (let i = 0; i < records.length; i++) {{
  const o = document.createElement('option'); o.value = i; o.textContent = records[i].t; roundSel.appendChild(o);
}}
function fillEpisodes() {{
  epSel.innerHTML = '';
  const eps = records[roundIdx]?.episodes || [];
  for (let i = 0; i < eps.length; i++) {{
    const o = document.createElement('option'); o.value = i; o.textContent = eps[i].task_id; epSel.appendChild(o);
  }}
  episodeIdx = 0; step = 0;
}}
function draw() {{
  const ep = records[roundIdx]?.episodes?.[episodeIdx];
  if (!ep) return;
  const task = ep.task;
  gridEl.className = 'grid';
  gridEl.style.gridTemplateColumns = `repeat(${{task.width}}, 24px)`;
  gridEl.innerHTML = '';
  const marks = new Map();
  ep.agents.forEach((agent, ai) => {{
    const path = agent.route.path || [];
    for (let i = 0; i < Math.min(path.length, step + 1); i++) marks.set(path[i].join(','), ai);
  }});
  for (let y = 0; y < task.height; y++) {{
    for (let x = 0; x < task.width; x++) {{
      const d = document.createElement('div');
      d.className = 'cell';
      if (task.grid[y][x] === '#') d.classList.add('wall');
      const key = `${{x}},${{y}}`;
      if (x === task.start[0] && y === task.start[1]) {{ d.classList.add('start'); d.textContent = 'S'; }}
      if (x === task.goal[0] && y === task.goal[1]) {{ d.classList.add('goal'); d.textContent = 'G'; }}
      if (marks.has(key)) {{ d.classList.add('path' + (marks.get(key) % 4)); d.textContent = String(marks.get(key)); }}
      gridEl.appendChild(d);
    }}
  }}
  document.getElementById('step').textContent = `step ${{step}}`;
  details.textContent = JSON.stringify(ep.agents.map(a => ({{agent_id:a.agent_id, route:a.route, retrieved:a.retrieved}})), null, 2);
}}
roundSel.onchange = () => {{ roundIdx = Number(roundSel.value); fillEpisodes(); draw(); }};
epSel.onchange = () => {{ episodeIdx = Number(epSel.value); step = 0; draw(); }};
document.getElementById('prev').onclick = () => {{ step = Math.max(0, step - 1); draw(); }};
document.getElementById('next').onclick = () => {{ step += 1; draw(); }};
fillEpisodes(); draw();
</script>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_route_atlas(episodes: list[MazeEpisodeResult], path: Path) -> Path:
    import matplotlib.pyplot as plt

    cols = min(4, max(1, len(episodes)))
    rows = math.ceil(len(episodes) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.0, rows * 3.0), squeeze=False)
    colors = ["#ef4444", "#f97316", "#8b5cf6", "#ec4899", "#14b8a6"]
    for ax in axes.flat:
        ax.axis("off")
    for ax, ep in zip(axes.flat, episodes):
        task = ep.task
        for y, row in enumerate(task.grid):
            for x, cell in enumerate(row):
                if cell == "#":
                    ax.add_patch(plt.Rectangle((x, task.height - y - 1), 1, 1, color="#222222"))
        ax.scatter([task.start[0] + 0.5], [task.height - task.start[1] - 0.5], c="#0ea5e9", marker="s")
        ax.scatter([task.goal[0] + 0.5], [task.height - task.goal[1] - 0.5], c="#22c55e", marker="*")
        for agent in ep.agents:
            path_cells = agent.route.get("path", [])
            if len(path_cells) < 2:
                continue
            xs = [cell[0] + 0.5 for cell in path_cells]
            ys = [task.height - cell[1] - 0.5 for cell in path_cells]
            ax.plot(xs, ys, color=colors[agent.agent_id % len(colors)], linewidth=1.4, alpha=0.8)
        ax.set_title(ep.task_id, fontsize=8)
        ax.set_xlim(0, task.width)
        ax.set_ylim(0, task.height)
        ax.set_aspect("equal")
        ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_maze_curves(result: dict[str, Any], path: Path) -> Path:
    import matplotlib.pyplot as plt

    log = result.get("log", [])
    t = [row["t"] for row in log]
    fig, axes = plt.subplots(2, 3, figsize=(12, 6), squeeze=False)
    series = [
        ("success_rate", axes[0][0]),
        ("cost_ratio", axes[0][1]),
        ("loop_rate", axes[0][2]),
        ("route_diversity", axes[1][0]),
        ("stagnation_rate", axes[1][1]),
        ("revisit_max", axes[1][2]),
    ]
    for key, ax in series:
        ax.plot(t, [row.get(key, 0.0) for row in log], marker="o")
        ax.set_title(key)
        ax.grid(True, alpha=0.25)
    fig.suptitle(result.get("summary", {}).get("condition", "maze alpha"))
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_maze_report(results: list[dict[str, Any]], out_dir: Path) -> Path:
    lines = [
        "# Maze Alpha Report",
        "",
        "This exploratory report focuses on strategy efficiency, route convergence, and silent loops.",
        "",
        "| condition | success final | cost final | loop final | diversity final | retrieval concentration | tokens |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        s = result["summary"]
        llm = s["llm"]
        lines.append(
            f"| {s['condition']} | {s['success_final']:.3f} | {s['cost_final']:.3f} | "
            f"{s['loop_final']:.3f} | {s['route_diversity_final']:.3f} | "
            f"{s['retrieval_concentration_final']:.3f} | {llm.get('trace_total_tokens', llm['total_tokens'])} |"
        )
    lines.extend(["", "## Artifacts", ""])
    for result in results:
        cond = result["summary"]["condition"]
        lines.append(f"- `{cond}`: `result.json`, `curves.png`, `memory_audit.json`, `replays/index.html`")
    path = out_dir / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cli(args: argparse.Namespace) -> list[dict[str, Any]]:
    configs = build_maze_alpha_configs(args)
    max_train = max(int(c.n_train or 0) for c in configs)
    max_heldout = max(c.heldout_size for c in configs)
    results: list[dict[str, Any]] = []
    for cfg in configs:
        train = _make_filtered_maze_tasks(
            split="train",
            n=max_train,
            seed=cfg.seed,
            width=cfg.maze_width,
            height=cfg.maze_height,
            family=cfg.maze_family,
            min_shortest=cfg.maze_min_shortest,
            max_shortest=cfg.maze_max_shortest,
        )
        heldout = _make_filtered_maze_tasks(
            split="heldout",
            n=max_heldout,
            seed=cfg.seed,
            width=cfg.maze_width,
            height=cfg.maze_height,
            family=cfg.maze_family,
            min_shortest=cfg.maze_min_shortest,
            max_shortest=cfg.maze_max_shortest,
        )
        print(f"Running {condition_name(cfg)} with train={len(train)} heldout={len(heldout)}", flush=True)
        results.append(asyncio.run(run_one_maze_alpha(cfg, train, heldout)))
    out_dir = Path(args.out_dir)
    _write_json(out_dir / f"summary_{args.phase}.json", [r["summary"] for r in results])
    write_maze_report(results, out_dir)
    return results


def _make_filtered_maze_tasks(
    *,
    split: str,
    n: int,
    seed: int,
    width: int,
    height: int,
    family: str,
    min_shortest: int = 0,
    max_shortest: int = 0,
) -> list[MazeTask]:
    if min_shortest <= 0 and max_shortest <= 0:
        return make_maze_tasks(split=split, n=n, seed=seed, width=width, height=height, family=family)
    tasks: list[MazeTask] = []
    batch = max(n, 50)
    attempt_seed = seed
    attempts = 0
    while len(tasks) < n and attempts < 200:
        candidates = make_maze_tasks(split=split, n=batch, seed=attempt_seed, width=width, height=height, family=family)
        for task in candidates:
            shortest = task.shortest_path_length
            if shortest < min_shortest:
                continue
            if max_shortest and shortest > max_shortest:
                continue
            tasks.append(task)
            if len(tasks) >= n:
                break
        attempt_seed += 1
        attempts += 1
    if len(tasks) < n:
        raise RuntimeError(
            f"could not generate {n} {split} mazes for {width}x{height} {family} "
            f"with shortest in [{min_shortest}, {max_shortest or 'inf'}]; got {len(tasks)}"
        )
    return tasks
