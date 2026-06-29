from __future__ import annotations

import asyncio
from typing import Any

from .config import Config
from .llm import LLMClient
from .memory import InsightMemory
from .solver import render_library


DEBATE_SYS = (
    "You are one of several independent reasoning agents solving a multi-hop QA question. "
    "Use the SHARED EXPERIENCE if helpful. If CONTEXT is provided, ground your answer in it "
    "rather than relying on memory. When PEER ANSWERS are shown, critically reconsider them: "
    "revise your answer if a peer is better justified, but do NOT conform without a reason. "
    "Output 1-3 concise reasoning sentences, then exactly one line: Final answer: <short answer>."
)


def _context_block(context: str, cfg: Config) -> str:
    if cfg.use_context and context:
        return f"CONTEXT:\n{context[: cfg.max_context_chars]}\n\n"
    return ""


def _round1_user(agent_id: int, insights: list[dict], context: str, question: str, cfg: Config) -> str:
    return (
        f"SOLVER AGENT ID: {agent_id}\n"
        "Use an independent reasoning style from other agents while following the same output format.\n\n"
        f"SHARED EXPERIENCE:\n{render_library(insights)}\n\n"
        f"{_context_block(context, cfg)}"
        f"QUESTION:\n{question}\n\n"
        "Remember: finish with exactly one line starting with 'Final answer:'."
    )


def _peer_block(peer_texts: list[str], self_id: int) -> str:
    lines = []
    for pid, text in enumerate(peer_texts):
        if pid == self_id:
            continue
        lines.append(f"- Agent {pid}: {text.strip()[:600]}")
    return "\n".join(lines) if lines else "(none)"


def _round_n_user(
    agent_id: int, insights: list[dict], context: str, question: str, peer_texts: list[str], cfg: Config
) -> str:
    return (
        f"SOLVER AGENT ID: {agent_id}\n\n"
        f"SHARED EXPERIENCE:\n{render_library(insights)}\n\n"
        f"{_context_block(context, cfg)}"
        f"QUESTION:\n{question}\n\n"
        f"PEER ANSWERS (previous round):\n{_peer_block(peer_texts, agent_id)}\n\n"
        "Reconsider in light of the peers and give your updated answer. "
        "Finish with exactly one line starting with 'Final answer:'."
    )


async def debate_answer(
    question: str,
    context: str,
    memory: InsightMemory,
    cfg: Config,
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """Run an R-round multi-agent debate; return per-agent {final, rounds}."""
    n = cfg.n_solvers
    insights = [memory.retrieve(agent_id, question) for agent_id in range(n)]

    async def call(agent_id: int, user: str) -> str:
        return await llm.chat(
            [{"role": "system", "content": DEBATE_SYS}, {"role": "user", "content": user}],
            temp=cfg.solver_temp,
            max_tokens=cfg.max_tokens_solver,
            tag=f"debate:{agent_id}",
        )

    texts = await asyncio.gather(
        *[call(a, _round1_user(a, insights[a], context, question, cfg)) for a in range(n)]
    )
    rounds: list[list[str]] = [list(texts)]
    for _ in range(2, cfg.debate_rounds + 1):
        prev = list(texts)
        texts = await asyncio.gather(
            *[call(a, _round_n_user(a, insights[a], context, question, prev, cfg)) for a in range(n)]
        )
        rounds.append(list(texts))

    return [
        {"final": rounds[-1][a], "rounds": [rounds[r][a] for r in range(len(rounds))]}
        for a in range(n)
    ]
