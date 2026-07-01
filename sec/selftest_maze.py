from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .llm import LLMClient
from .maze_alpha import (
    MazeMemoryAudit,
    maze_batch_metrics,
    run_maze_episode,
    run_one_maze_alpha,
    write_replay_html,
    write_route_atlas,
)
from .maze_env import MazeEnv, detect_position_loop, make_maze_tasks, shortest_path
from .memory import InsightMemory


async def _mock_chat(self, messages, *, temp=0.0, model=None, max_tokens=None, tag=""):
    user = messages[-1]["content"]
    if tag in {"maze_reviewer", "expel_reviewer"}:
        return '[{"kind":"do","text":"Prefer open directions that reduce distance while avoiding revisits."}]'
    suggested_match = re.search(r'"suggested_action":\s*"([^"]+)"', user)
    if suggested_match:
        return f"Use the provided local search memory. Action: {suggested_match.group(1)}"
    dist_match = re.search(r"Manhattan distance: (\d+)", user)
    if dist_match and int(dist_match.group(1)) == 0:
        return "At the goal. Action: submit"
    open_match = re.search(r"Open directions: ([^.]+)\\.", user)
    opens = open_match.group(1).split(", ") if open_match else ["right"]
    if "right" in opens:
        return "Move toward open space. Action: move:right"
    if "down" in opens:
        return "Move toward open space. Action: move:down"
    if "left" in opens:
        return "Move toward open space. Action: move:left"
    return "Move toward open space. Action: move:up"


def _cfg(**overrides):
    params = dict(
        api_key_env="SEC_MOCK_KEY",
        model="mock",
        base_url="http://mock.invalid/v1",
        n_solvers=2,
        memory_mode="shared",
        maze_write_mode="direct",
        T=1,
        batch_M=1,
        n_train=1,
        heldout_size=2,
        max_steps=12,
        retrieval_k=2,
        cache_dir="./.sec_mock_cache",
        out_dir="./.sec_mock_runs",
    )
    params.update(overrides)
    return Config(**params)


def _maze_checks() -> None:
    tasks = make_maze_tasks(split="heldout", n=3, seed=0, width=9, height=9, family="trap")
    assert len(tasks) == 3
    for task in tasks:
        path = shortest_path(task.grid, task.start, task.goal)
        assert path and path[0] == task.start and path[-1] == task.goal
    env = MazeEnv()
    obs = env.reset(tasks[0])
    assert "Position:" in obs and "Open directions:" in obs
    obs, done, info = env.step("inspect")
    assert not done and info["normalized_action"] == "inspect"
    assert detect_position_loop([(1, 1), (2, 1), (1, 1), (2, 1), (1, 1), (2, 1)])
    print("maze pure checks OK")


async def _state_guided_checks() -> None:
    original = LLMClient.chat
    LLMClient.chat = _mock_chat  # type: ignore[assignment]
    try:
        cfg = _cfg(n_solvers=1, maze_agent_mode="state_guided", memory_mode="none", maze_write_mode="none", max_steps=40)
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        tasks = make_maze_tasks(split="heldout", n=2, seed=3, width=9, height=9, family="benign")
        episodes = [await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0) for task in tasks]
        routes = [episode.agents[0].route for episode in episodes]
        for episode, route in zip(episodes, routes, strict=True):
            assert "stagnation_rate" in route and "state_guided_override_count" in route
            assert route["state_guided_override_count"] == 0
            assert episode.agents[0].trace and episode.agents[0].trace[0]["search_state"]
        print(
            "maze state_guided checks OK:",
            [{"success": route["success"], "steps": route["steps"]} for route in routes],
        )
    finally:
        LLMClient.chat = original  # type: ignore[assignment]


async def _episode_checks() -> None:
    original = LLMClient.chat
    LLMClient.chat = _mock_chat  # type: ignore[assignment]
    try:
        cfg = _cfg()
        llm = LLMClient(cfg)
        memory = InsightMemory(cfg)
        audit = MazeMemoryAudit()
        task = make_maze_tasks(split="heldout", n=1, seed=1, width=9, height=9, family="benign")[0]
        episode = await run_maze_episode(task, memory, cfg, llm, audit=audit, t=0)
        metrics = maze_batch_metrics([episode])
        assert "success_rate" in metrics and "cost_ratio" in metrics and "route_diversity" in metrics
        assert "stagnation_rate" in metrics and "revisit_max" in metrics
        out = Path("./.sec_mock_runs/maze_selftest")
        write_route_atlas([episode], out / "atlas.png")
        write_replay_html({"heldout_records": [{"t": 0, "episodes": [episode.public()]}]}, out / "replay.html")
        assert (out / "atlas.png").exists() and (out / "replay.html").exists()
        print("maze episode checks OK:", {k: round(v, 3) for k, v in metrics.items()})
    finally:
        LLMClient.chat = original  # type: ignore[assignment]


async def _runner_checks() -> None:
    original = LLMClient.chat
    LLMClient.chat = _mock_chat  # type: ignore[assignment]
    try:
        cfg = _cfg(
            run_id="maze_runner_selftest",
            n_solvers=1,
            T=2,
            batch_M=1,
            n_train=2,
            heldout_size=1,
            max_steps=8,
            out_dir="./.sec_mock_runs/maze_runner",
        )
        train = make_maze_tasks(split="train", n=2, seed=2, width=9, height=9, family="benign")
        heldout = make_maze_tasks(split="heldout", n=1, seed=2, width=9, height=9, family="benign")
        result = await run_one_maze_alpha(cfg, train, heldout)
        out = Path(cfg.out_dir) / "n1_gt_false_seed0_maze_runner_selftest"
        assert result["summary"]["condition"].endswith("maze_runner_selftest")
        assert (out / "result.json").exists()
        assert (out / "memory_audit.json").exists()
        assert (out / "replays" / "index.html").exists()
        assert (out / "curves.png").exists()
        print("maze runner checks OK")
    finally:
        LLMClient.chat = original  # type: ignore[assignment]


def main() -> None:
    _maze_checks()
    asyncio.run(_state_guided_checks())
    asyncio.run(_episode_checks())
    asyncio.run(_runner_checks())
    print("selftest_maze OK")


if __name__ == "__main__":
    main()
