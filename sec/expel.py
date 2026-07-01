from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import Config
from .llm import LLMClient
from .metrics import normalize_answer


EXPEL_SYS = (
    "You distill reusable cross-task experience from agent episodes. "
    "Use only the provided episode logs and quality signals; never assume hidden labels. "
    "Extract abstract do/avoid strategy lessons that can transfer to future tasks in the same environment. "
    "Do not copy task-specific answers, identifiers, exact paths, coordinates, URLs, filenames, or fixed action scripts unless the adapter explicitly says they are reusable abstractions. "
    "Return strict JSON only."
)


@dataclass(frozen=True)
class ExpeLAdapter:
    """Domain adapter for the generic ExpeL-style experience extractor."""

    task_family: str
    trajectory_label: str
    forbidden_details: str
    strategy_focus: str
    fallback: dict[str, str]


def parse_expel_insights(text: str) -> list[dict[str, str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    insights: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text_value = str(item.get("text", "")).strip()
        if not text_value:
            continue
        kind = item.get("kind") if item.get("kind") in {"do", "avoid"} else "do"
        insights.append({"kind": str(kind), "text": text_value})
    return insights


def sanitize_expel_insight(insight: dict[str, Any], *, fallback: dict[str, str]) -> dict[str, str]:
    text = str(insight.get("text", "")).strip()
    kind = insight.get("kind") if insight.get("kind") in {"do", "avoid"} else "do"
    if not text:
        return {"kind": fallback.get("kind", "do"), "text": fallback.get("text", "")}
    if looks_over_specific(text):
        return {"kind": fallback.get("kind", "do"), "text": fallback.get("text", "")}
    return {"kind": str(kind), "text": text}


def looks_over_specific(text: str) -> bool:
    low = text.lower()
    if re.search(r"\(\s*-?\d+\s*,\s*-?\d+\s*\)", low):
        return True
    if re.search(r"\bhttps?://|\b[a-z]:\\|/[\w.-]+/[\w.-]+", text):
        return True
    actions = re.findall(r"\b(up|down|left|right|move:up|move:down|move:left|move:right)\b", low)
    if len(actions) >= 4:
        return True
    # A long quoted/final-answer-like literal usually means the extractor memorized a task result.
    if re.search(r"\b(final answer|exact answer|copy the answer)\b", low):
        return True
    if re.search(r"\b(maze|task|episode|case|item|question)\s*id\b", low):
        return True
    return False


async def distill_expel_insights(
    episodes: list[dict[str, Any]],
    adapter: ExpeLAdapter,
    cfg: Config,
    llm: LLMClient,
    *,
    forbidden_check: Callable[[str], bool] | None = None,
) -> list[dict[str, str]]:
    """Generic ExpeL-style contrastive experience extraction.

    ``episodes`` are environment-normalized records with:
      - episode_id
      - agent_id
      - outcome / quality
      - trajectory
    Environment-specific code should only adapt logs into this schema.
    """

    blocks = []
    for idx, ep in enumerate(episodes):
        quality = ep.get("quality", {})
        quality_text = json.dumps(quality, ensure_ascii=False, sort_keys=True)
        blocks.append(
            f"EPISODE {idx}\n"
            f"id={ep.get('episode_id', '')} agent_id={ep.get('agent_id', '')} outcome={ep.get('outcome', '')}\n"
            f"quality={quality_text}\n"
            f"{adapter.trajectory_label}:\n{str(ep.get('trajectory', ''))[:4000]}"
        )

    prompt = (
        f"Task family:\n{adapter.task_family}\n\n"
        f"Strategy focus:\n{adapter.strategy_focus}\n\n"
        f"Forbidden details:\n{adapter.forbidden_details}\n\n"
        "Episodes:\n"
        + "\n\n---\n\n".join(blocks)
        + "\n\nDistill reusable experience for future tasks in this family. "
        "Use success/failure and quality signals to contrast better and worse strategies. "
        "Do not merely restate whether an episode succeeded. "
        "Return strict JSON array only: "
        "[{\"kind\":\"do\"|\"avoid\", \"text\":\"abstract reusable strategy lesson\"}]. "
        "Produce at most 2 do-rules and 2 avoid-rules."
    )
    out = await llm.chat(
        [{"role": "system", "content": EXPEL_SYS}, {"role": "user", "content": prompt}],
        temp=0.2,
        max_tokens=cfg.max_tokens_reviewer,
        tag="expel_reviewer",
    )
    insights: list[dict[str, str]] = []
    for item in parse_expel_insights(out):
        insight = sanitize_expel_insight(item, fallback=adapter.fallback)
        if forbidden_check and forbidden_check(insight["text"]):
            continue
        insights.append(insight)
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for insight in insights:
        key = normalize_answer(insight["text"])
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(insight)
    return unique[:4] if unique else [adapter.fallback]
