from __future__ import annotations

import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .config import Config
from .llm import LLMClient
from .memory import InsightMemory
from .metrics import answer_entropy, normalize_answer
from .solver import render_library


# ---------------------------------------------------------------------------
# Environment protocol — any benchmark (tau-bench, SWE-bench, terminal-bench)
# is plugged in by implementing this. Actions and observations are text.
# ---------------------------------------------------------------------------

@runtime_checkable
class Environment(Protocol):
    task_id: str

    def reset(self, task: dict[str, Any]) -> str:
        """Start a task; return the initial observation text."""

    def step(self, action: str) -> tuple[str, bool, dict[str, Any]]:
        """Execute one action; return (observation, done, info).

        Tool/runtime errors must be returned as observation text, NOT raised — the whole point
        is that the agent can fail silently (loop) without the harness crashing.
        """

    def tools_doc(self) -> str:
        """Human-readable description of the available tools/actions."""

    def is_success(self) -> bool:
        """Whether the task is solved in the current state."""


@dataclass
class EpisodeResult:
    task_id: str
    success: bool
    steps: int
    terminated: bool           # env reached a terminal (done) state within max_steps
    looped: bool               # a normalized action repeated within the loop window (silent loop)
    consensus: float           # mean per-step majority fraction across agents
    diversity: float           # mean per-step action entropy across agents
    trajectory: list[dict[str, Any]] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "steps": self.steps,
            "terminated": self.terminated,
            "looped": self.looped,
            "consensus": self.consensus,
            "diversity": self.diversity,
        }


AGENT_SYS = (
    "You are one of several agents collaborating to complete a multi-step task by calling tools. "
    "Use the SHARED EXPERIENCE if helpful. Read the TOOLS, the current OBSERVATION, and the HISTORY, "
    "then output 1-2 short reasoning sentences and exactly one line: Action: <one tool call>. "
    "When PEER ACTIONS are shown, reconsider them but do not conform without a reason."
)


def parse_action(text: str) -> str:
    match = re.search(r"action\s*:\s*(.+)", str(text), flags=re.IGNORECASE)
    if match:
        return match.group(1).splitlines()[0].strip()
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return lines[-1] if lines else ""


def aggregate_action(proposals: list[str]) -> tuple[str, float]:
    """Majority vote over normalized actions; returns (chosen action, majority fraction)."""
    if not proposals:
        return "", 0.0
    norms = [normalize_answer(p) for p in proposals]
    top_norm, count = Counter(norms).most_common(1)[0]
    representative = next(p for p in proposals if normalize_answer(p) == top_norm)
    return representative, count / len(proposals)


def _history_block(history: list[dict[str, Any]], limit: int = 6) -> str:
    if not history:
        return "(no actions yet)"
    recent = history[-limit:]
    return "\n".join(f"step {h['step']}: action={h['action']!r} -> obs={h['obs'][:200]!r}" for h in recent)


def _peer_block(peer_actions: list[str], self_id: int) -> str:
    lines = [f"- Agent {pid}: {act.strip()[:200]}" for pid, act in enumerate(peer_actions) if pid != self_id]
    return "\n".join(lines) if lines else "(none)"


def _user_prompt(env, obs, history, insights, agent_id, peer_actions, cfg) -> str:
    peer = ""
    if peer_actions:
        peer = f"PEER ACTIONS (this step):\n{_peer_block(peer_actions, agent_id)}\n\n"
    return (
        f"AGENT ID: {agent_id}\n\n"
        f"TOOLS:\n{env.tools_doc()}\n\n"
        f"SHARED EXPERIENCE:\n{render_library(insights)}\n\n"
        f"HISTORY:\n{_history_block(history)}\n\n"
        f"OBSERVATION:\n{obs}\n\n"
        f"{peer}"
        "Decide the single best next action. Finish with exactly one line: 'Action: <tool call>'."
    )


async def _debate_step(env, obs, history, insights_per_agent, cfg: Config, llm: LLMClient) -> list[str]:
    """One step's multi-agent debate; returns each agent's final-round proposed action."""
    n = cfg.n_solvers

    async def call(agent_id: int, peer_actions: list[str]) -> str:
        user = _user_prompt(env, obs, history, insights_per_agent[agent_id], agent_id, peer_actions, cfg)
        out = await llm.chat(
            [{"role": "system", "content": AGENT_SYS}, {"role": "user", "content": user}],
            temp=cfg.solver_temp,
            max_tokens=cfg.max_tokens_solver,
            tag=f"agent:{agent_id}",
        )
        return parse_action(out)

    actions = await asyncio.gather(*[call(a, []) for a in range(n)])
    for _ in range(2, cfg.debate_rounds + 1):
        prev = list(actions)
        actions = await asyncio.gather(*[call(a, prev) for a in range(n)])
    return list(actions)


async def run_episode(task: dict[str, Any], env: Environment, memory: InsightMemory, cfg: Config, llm: LLMClient) -> EpisodeResult:
    obs = env.reset(task)
    query = str(task.get("query") or task.get("instruction") or task.get("task_id") or task)
    history: list[dict[str, Any]] = []
    recent_actions: list[str] = []
    consensus_series: list[float] = []
    diversity_series: list[float] = []
    looped = False
    done = False
    step = 0

    insights_per_agent = [memory.retrieve(a, query) for a in range(cfg.n_solvers)]

    while step < cfg.max_steps:
        proposals = await _debate_step(env, obs, history, insights_per_agent, cfg, llm)
        action, majority = aggregate_action(proposals)
        consensus_series.append(majority)
        diversity_series.append(answer_entropy(proposals))

        norm_action = normalize_answer(action)
        if norm_action and norm_action in recent_actions[-cfg.loop_window:]:
            looped = True  # silent death-loop: repeating an action without progress
        recent_actions.append(norm_action)

        obs, done, info = env.step(action)
        history.append({"step": step, "action": action, "obs": obs, "consensus": majority})
        step += 1
        if done:
            break

    mean = lambda xs: float(sum(xs) / len(xs)) if xs else 0.0
    return EpisodeResult(
        task_id=getattr(env, "task_id", query),
        success=bool(env.is_success()),
        steps=step,
        terminated=done,
        looped=looped,
        consensus=mean(consensus_series),
        diversity=mean(diversity_series),
        trajectory=history,
    )


def episode_batch_metrics(results: list[EpisodeResult]) -> dict[str, float]:
    """Per-round metrics over a batch of episodes, including the silent-failure indicators."""
    n = len(results)
    if n == 0:
        return {"A_t": 0.0, "C_t": 0.0, "G_t": 0.0, "D_t": 0.0, "nonterm_rate": 0.0, "loop_rate": 0.0}
    mean = lambda f: float(sum(f(r) for r in results) / n)
    a_t = mean(lambda r: 1.0 if r.success else 0.0)
    c_t = mean(lambda r: r.consensus)
    return {
        "A_t": a_t,
        "C_t": c_t,
        "G_t": c_t - a_t,
        "D_t": mean(lambda r: r.diversity),
        "nonterm_rate": mean(lambda r: 0.0 if r.terminated else 1.0),  # never reached done
        "loop_rate": mean(lambda r: 1.0 if r.looped else 0.0),         # silent action repetition
    }
