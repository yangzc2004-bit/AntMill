from __future__ import annotations

import json
import re
from typing import Any

from .config import Config
from .expel import ExpeLAdapter, render_episode_blocks, sanitize_expel_insight
from .llm import LLMClient
from .metrics import normalize_answer, similarity


MEMORY_OPS_SYS = (
    "You maintain a library of reusable do/avoid strategy insights for an agent family. "
    "You see the current numbered insight pool and a batch of new episode logs with quality signals. "
    "Evolve the pool with operations: ADD a genuinely new transferable lesson; "
    "UPVOTE an existing insight that the new episodes support; "
    "DOWNVOTE an existing insight that the new episodes contradict or that plausibly caused harm; "
    "EDIT an existing insight to refine or generalize its wording. "
    "Use only the provided logs and quality signals; never assume hidden labels. "
    "Do not write task ids, coordinates, exact paths, URLs, or fixed action sequences. "
    "Return strict JSON only."
)

VALID_OPS = {"ADD", "EDIT", "UPVOTE", "DOWNVOTE"}
# ExpeL initializes a newly added insight with importance 2 and removes an insight
# once its count drops to 0; the LLM decides the operations, code only executes.
ADD_INITIAL_VOTES = 2
MAX_OPS_PER_BATCH = 6


def render_ops_pool(pool: list[dict[str, Any]]) -> str:
    if not pool:
        return "(empty)"
    return "\n".join(
        f"[{idx}] kind={item.get('kind', 'do')} votes={int(item.get('votes', 0))} "
        f"text={item.get('text', '')}"
        for idx, item in enumerate(pool)
    )


def parse_memory_ops(text: str, *, max_ops: int = MAX_OPS_PER_BATCH) -> list[dict[str, Any]]:
    """Tolerant parse of the LLM's operation list; invalid entries are dropped."""
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
    ops: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        op = str(item.get("op", "")).strip().upper()
        if op not in VALID_OPS:
            continue
        entry: dict[str, Any] = {"op": op, "target_id": None}
        target = item.get("target_id")
        if target is not None:
            try:
                entry["target_id"] = int(target)
            except (TypeError, ValueError):
                entry["target_id"] = None
        kind = item.get("kind")
        entry["kind"] = kind if kind in {"do", "avoid"} else "do"
        entry["text"] = str(item.get("text", "")).strip()
        ops.append(entry)
    return ops[:max_ops]


async def propose_memory_ops(
    pool: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    adapter: ExpeLAdapter,
    cfg: Config,
    llm: LLMClient,
) -> list[dict[str, Any]]:
    """ExpeL-faithful pool evolution: the reviewer LLM sees the pool and issues ops."""
    prompt = (
        f"Task family:\n{adapter.task_family}\n\n"
        f"Strategy focus:\n{adapter.strategy_focus}\n\n"
        f"Forbidden details:\n{adapter.forbidden_details}\n\n"
        f"EXISTING INSIGHT POOL:\n{render_ops_pool(pool)}\n\n"
        "NEW EPISODES:\n"
        + render_episode_blocks(episodes, adapter)
        + "\n\nEvolve the insight pool for future tasks in this family. "
        "Contrast better and worse episodes using the quality signals. "
        "Prefer UPVOTE/DOWNVOTE/EDIT on existing insights over redundant ADDs. "
        "Return strict JSON array only: "
        '[{"op":"ADD"|"EDIT"|"UPVOTE"|"DOWNVOTE", "target_id": <pool index or null>, '
        '"kind":"do"|"avoid", "text":"abstract reusable strategy lesson"}]. '
        "target_id refers to the pool numbering above; it is required for EDIT/UPVOTE/DOWNVOTE "
        f"and must be null for ADD. Use at most {cfg.max_reviewer_ops} operations."
    )
    out = await llm.chat(
        [{"role": "system", "content": MEMORY_OPS_SYS}, {"role": "user", "content": prompt}],
        temp=0.2,
        max_tokens=cfg.max_tokens_reviewer,
        tag="expel_ops_reviewer",
    )
    return parse_memory_ops(out, max_ops=cfg.max_reviewer_ops)


def apply_memory_ops(
    pool: list[dict[str, Any]],
    ops: list[dict[str, Any]],
    *,
    cfg: Config,
    reject_log: list[dict[str, str]] | None = None,
    archive_log: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Execute LLM-issued operations. Code executes, never decides; the sanitizer is
    the only veto (rejects are dropped and logged, never rewritten).

    Item dicts are mutated in place so live references (retrieval counts, audit
    provenance) stay attached; only the list container is rebuilt for removal/cap.
    Returns (new_pool, applied_ops); applied entries carry an "item" reference.
    """
    applied: list[dict[str, Any]] = []
    for op in ops:
        name = str(op.get("op", ""))
        text = str(op.get("text", "")).strip()
        kind = op.get("kind", "do")
        target = op.get("target_id")
        if name in {"EDIT", "UPVOTE", "DOWNVOTE"}:
            if target is None or not 0 <= int(target) < len(pool):
                _log_reject(reject_log, name, text, "invalid_target")
                continue
            item = pool[int(target)]
        if name == "ADD":
            clean = sanitize_expel_insight({"kind": kind, "text": text})
            if not clean:
                _log_reject(reject_log, name, text, "over_specific")
                continue
            dup = find_pool_duplicate(pool, clean, cfg)
            if dup is not None:
                # A re-added existing lesson is agreement, not a new entry.
                _log_archive(
                    archive_log,
                    "similarity_merge",
                    {"kind": clean["kind"], "text": clean["text"], "votes": ADD_INITIAL_VOTES},
                    op="ADD",
                    merged_into=pool[dup],
                )
                pool[dup]["votes"] = int(pool[dup].get("votes", 0)) + 1
                applied.append({"op": "UPVOTE", "item": pool[dup], "converted_from": "ADD"})
                continue
            record: dict[str, Any] = {"kind": clean["kind"], "text": clean["text"], "votes": ADD_INITIAL_VOTES}
            pool.append(record)
            applied.append({"op": "ADD", "item": record})
        elif name == "UPVOTE":
            item["votes"] = int(item.get("votes", 0)) + 1
            applied.append({"op": "UPVOTE", "item": item})
        elif name == "DOWNVOTE":
            _log_archive(archive_log, "downvote", dict(item), op="DOWNVOTE")
            item["votes"] = int(item.get("votes", 0)) - 1
            applied.append({"op": "DOWNVOTE", "item": item})
        elif name == "EDIT":
            _log_archive(archive_log, "edit_before", dict(item), op="EDIT")
            clean = sanitize_expel_insight({"kind": kind if kind in {"do", "avoid"} else item.get("kind", "do"), "text": text})
            if not clean:
                _log_reject(reject_log, name, text, "over_specific")
                continue
            item["text"] = clean["text"]
            item["kind"] = clean["kind"]
            applied.append({"op": "EDIT", "item": item})
    survivors = [item for item in pool if int(item.get("votes", 0)) > 0]
    survivors.sort(key=lambda item: (int(item.get("votes", 0)), normalize_answer(str(item.get("text", "")))), reverse=True)
    return survivors[: cfg.library_cap], applied


def find_pool_duplicate(pool: list[dict[str, Any]], insight: dict[str, str], cfg: Config) -> int | None:
    best_idx: int | None = None
    best_score = 0.0
    for idx, item in enumerate(pool):
        if item.get("kind") != insight.get("kind"):
            continue
        score = similarity(insight["text"], str(item.get("text", "")))
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx is not None and best_score >= cfg.similarity_threshold:
        return best_idx
    return None


def _log_reject(reject_log: list[dict[str, str]] | None, op: str, text: str, reason: str) -> None:
    if reject_log is not None:
        reject_log.append({"op": op, "text": text, "reason": reason})


def _log_archive(
    archive_log: list[dict[str, Any]] | None,
    source: str,
    item: dict[str, Any],
    *,
    op: str,
    merged_into: dict[str, Any] | None = None,
) -> None:
    if archive_log is not None:
        archive_log.append(
            {
                "source": source,
                "item": dict(item),
                "op": op,
                "merged_into": dict(merged_into) if merged_into is not None else None,
            }
        )
