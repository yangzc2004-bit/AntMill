from __future__ import annotations

from .config import Config
from .llm import LLMClient


SOLVER_SYS = (
    "You are a problem-solving agent for multi-hop QA. Use the SHARED EXPERIENCE if helpful. "
    "If CONTEXT is provided, ground your answer in it rather than relying on memory. "
    "Output 1-3 concise reasoning sentences, then exactly one line: Final answer: <short answer>."
)


def render_library(library: list[dict]) -> str:
    if not library:
        return "(empty)"
    do_rules = [item["text"] for item in library if item.get("kind") == "do"]
    avoid_rules = [item["text"] for item in library if item.get("kind") == "avoid"]
    lines: list[str] = []
    if do_rules:
        lines.append("DO:")
        lines.extend(f"- {rule}" for rule in do_rules)
    if avoid_rules:
        lines.append("AVOID:")
        lines.extend(f"- {rule}" for rule in avoid_rules)
    return "\n".join(lines) if lines else "(empty)"


async def solver_answer(
    question: str,
    context: str,
    library: list[dict],
    temp: float,
    *,
    cfg: Config,
    llm: LLMClient,
    solver_id: int,
) -> str:
    context_block = ""
    if cfg.use_context and context:
        clipped = context[: cfg.max_context_chars]
        context_block = f"CONTEXT:\n{clipped}\n\n"
    user = (
        f"SOLVER AGENT ID: {solver_id}\n"
        "Use an independent reasoning style from other agents while following the same output format.\n\n"
        f"SHARED EXPERIENCE:\n{render_library(library)}\n\n"
        f"{context_block}"
        f"QUESTION:\n{question}\n\n"
        "Remember: finish with exactly one line starting with 'Final answer:'."
    )
    return await llm.chat(
        [{"role": "system", "content": SOLVER_SYS}, {"role": "user", "content": user}],
        temp=temp,
        max_tokens=cfg.max_tokens_solver,
        tag=f"solver:{solver_id}",
    )
