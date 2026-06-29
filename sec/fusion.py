from __future__ import annotations

import json
import re
from typing import Any

from .config import Config
from .llm import LLMClient
from .metrics import (
    cluster_by_normalized_answer,
    exact_match,
    majority_cluster,
    normalize_answer,
    parse_final_answer,
    similarity,
)


REVIEWER_SYS = (
    "You distill reusable INSIGHTS by CONTRASTING multiple agents' trajectories on the SAME question. "
    "Use the provided success labels only; never assume an external answer key. "
    "Write abstract QA tactics that can transfer to future questions. "
    "Do NOT copy or mention this item's concrete final answers, entity names, titles, years, locations, or proper nouns. "
    "Do NOT write rules like 'Prefer ... before answering <answer>'. "
    "Turn item-specific observations into general strategies, such as verifying both candidates in comparison questions. "
    "Return strict JSON only."
)

SELF_EVAL_SYS = (
    "You are a self-reflection judge for your own QA trajectory. You do not know the answer key. "
    "Judge whether the trajectory is likely correct from internal consistency and question coverage only."
)


def _json_array_from_text(text: str) -> list[dict[str, Any]]:
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
    result = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            kind = item.get("kind")
            if kind not in {"do", "avoid"}:
                kind = "do"
            result.append({"text": item["text"].strip(), "kind": kind})
    return [item for item in result if item["text"]]


def _json_object_from_text(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _fallback_reviewer_insight() -> dict[str, str]:
    return {
        "kind": "do",
        "text": "Ground the final answer in explicit evidence from the provided context before responding.",
    }


def _specific_terms(question: str, clusters: list[dict[str, Any]]) -> set[str]:
    stop = {
        "a",
        "an",
        "and",
        "answer",
        "are",
        "did",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "of",
        "or",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whose",
        "why",
        "with",
        "yes",
        "no",
    }
    terms: set[str] = set()

    for cluster in clusters:
        answer = str(cluster.get("answer", ""))
        norm_answer = normalize_answer(answer)
        if len(norm_answer) >= 4 and norm_answer not in stop:
            terms.add(norm_answer)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'_:-]*|\d{3,}", answer):
            norm_token = normalize_answer(token)
            if len(norm_token) >= 4 and norm_token not in stop:
                terms.add(norm_token)

    capitalized_spans = re.findall(
        r"\b[A-Z][A-Za-z0-9'_:-]*(?:\s+(?:[A-Z][A-Za-z0-9'_:-]*|of|the|and|in|for|de|la|le|van|von))*",
        question,
    )
    for span in capitalized_spans:
        norm_span = normalize_answer(span)
        if len(norm_span) >= 4 and norm_span not in stop:
            terms.add(norm_span)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'_:-]*|\d{3,}", span):
            norm_token = normalize_answer(token)
            if len(norm_token) >= 4 and norm_token not in stop:
                terms.add(norm_token)

    return terms


def _is_item_specific_insight(text: str, question: str, clusters: list[dict[str, Any]]) -> bool:
    norm_text = normalize_answer(text)
    if not norm_text:
        return True
    if re.search(r"\bfinal answer\s*:", text, flags=re.IGNORECASE):
        return True
    for term in _specific_terms(question, clusters):
        if len(term.split()) >= 2 and term in norm_text:
            return True
        if len(term.split()) == 1 and re.search(rf"\b{re.escape(term)}\b", norm_text):
            return True
    return False


def _filter_reusable_insights(
    insights: list[dict[str, Any]],
    question: str,
    clusters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reusable: list[dict[str, Any]] = []
    seen: set[str] = set()
    for insight in insights:
        text = str(insight.get("text", "")).strip()
        if _is_item_specific_insight(text, question, clusters):
            continue
        key = normalize_answer(text)
        if key in seen:
            continue
        seen.add(key)
        reusable.append({"kind": insight.get("kind", "do"), "text": text})
    return reusable


async def self_reflect_success(question: str, trajectory: str, *, cfg: Config, llm: LLMClient) -> bool:
    prompt = (
        f"Question:\n{question}\n\nTrajectory:\n{trajectory}\n\n"
        "Return strict JSON only: {\"success\": true|false, \"confidence\": 0.0-1.0, \"reason\": \"short\"}."
    )
    out = await llm.chat(
        [{"role": "system", "content": SELF_EVAL_SYS}, {"role": "user", "content": prompt}],
        temp=0.0,
        max_tokens=cfg.max_tokens_self_eval,
        tag="self_eval",
    )
    data = _json_object_from_text(out)
    if "success" in data:
        return bool(data["success"])
    return "true" in out.lower() and "false" not in out.lower()


async def contrast_distill(
    question: str,
    clusters: list[dict[str, Any]],
    cluster_success: dict[str, bool],
    *,
    cfg: Config,
    llm: LLMClient,
) -> list[dict[str, Any]]:
    cluster_blocks = []
    for idx, cluster in enumerate(clusters):
        success = cluster_success.get(cluster["norm"], False)
        trajectories = "\n---\n".join(cluster["trajectories"][:2])
        cluster_blocks.append(
            f"CLUSTER {idx} success={str(success).lower()} size={len(cluster['indices'])}\n"
            f"Answer: {cluster['answer']}\nTrajectories:\n{trajectories}"
        )
    prompt = (
        f"Question:\n{question}\n\n"
        "Clusters with success labels:\n"
        + "\n\n".join(cluster_blocks)
        + "\n\nDistill only reusable strategy-level rules. Do not include this question's answer text, "
        "named entities, titles, years, places, or other proper nouns in the insight text. "
        "Bad: {\"kind\":\"do\", \"text\":\"Prefer evidence-linked reasoning before answering Gettysburg Address.\"}\n"
        "Good: {\"kind\":\"do\", \"text\":\"For chronology questions, extract and compare the relevant dates for all candidates before answering.\"}\n"
        "Return strict JSON array only, with this schema: "
        "[{\"kind\":\"do\"|\"avoid\", \"text\":\"abstract rule without item-specific nouns\"}]. "
        "Produce at most 2 do-rules and 2 avoid-rules."
    )
    out = await llm.chat(
        [{"role": "system", "content": REVIEWER_SYS}, {"role": "user", "content": prompt}],
        temp=0.2,
        max_tokens=cfg.max_tokens_reviewer,
        tag="reviewer",
    )
    insights = _filter_reusable_insights(_json_array_from_text(out), question, clusters)
    if insights:
        return insights[:4]
    return [_fallback_reviewer_insight()]


def _find_match(insight: dict[str, Any], library: list[dict[str, Any]], threshold: float) -> tuple[int | None, bool]:
    best_idx: int | None = None
    best_score = 0.0
    for idx, item in enumerate(library):
        score = similarity(insight["text"], item.get("text", ""))
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx is None or best_score < threshold:
        return None, False
    same_kind = library[best_idx].get("kind") == insight.get("kind")
    return best_idx, same_kind


def _apply_insight(
    library: list[dict[str, Any]],
    insight: dict[str, Any],
    *,
    cfg: Config,
    support_count: int,
) -> list[dict[str, Any]]:
    idx, same_kind = _find_match(insight, library, cfg.similarity_threshold)
    upvote = support_count >= cfg.mu * max(cfg.n_solvers, 1)
    if idx is None:
        library.append(
            {
                "text": insight["text"],
                "kind": insight.get("kind", "do"),
                "votes": 1 if upvote else 0,
                "evidence": insight.get("evidence", ""),
            }
        )
    elif same_kind:
        if upvote:
            library[idx]["votes"] = int(library[idx].get("votes", 0)) + 1
        elif len(insight["text"]) > len(str(library[idx].get("text", ""))):
            library[idx]["text"] = insight["text"]
    else:
        library[idx]["votes"] = int(library[idx].get("votes", 0)) - 1
    library = [item for item in library if int(item.get("votes", 0)) >= 0]
    library.sort(key=lambda item: (int(item.get("votes", 0)), normalize_answer(item.get("text", ""))), reverse=True)
    return library[: cfg.library_cap]


async def reviewer_synthesize(
    batch_results: list[dict[str, Any]],
    library: list[dict[str, Any]],
    cfg: Config,
    *,
    llm: LLMClient,
    gold: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    updated = [dict(item) for item in library]
    for item in batch_results:
        question = item["question"]
        answers = item["answers"]
        clusters = cluster_by_normalized_answer(answers)
        majority = majority_cluster(answers)
        endorsement = len(majority["indices"]) / max(len(answers), 1)

        cluster_success: dict[str, bool] = {}
        if cfg.use_ground_truth:
            if gold is None or question not in gold:
                raise ValueError("gold labels are required when use_ground_truth=True")
            for cluster in clusters:
                cluster_success[cluster["norm"]] = exact_match(cluster["answer"], gold[question])
        elif cfg.n_solvers >= 2:
            for cluster in clusters:
                cluster_success[cluster["norm"]] = (len(cluster["indices"]) / cfg.n_solvers) >= cfg.mu
        else:
            success = await self_reflect_success(question, answers[0], cfg=cfg, llm=llm)
            cluster_success[clusters[0]["norm"]] = success
            endorsement = 1.0 if success else 0.0

        insights = await contrast_distill(question, clusters, cluster_success, cfg=cfg, llm=llm)
        support_count = int(round(endorsement * max(cfg.n_solvers, 1)))
        for insight in insights:
            updated = _apply_insight(updated, insight, cfg=cfg, support_count=support_count)
    return updated


async def reviewer_synthesize_v2(
    batch_results: list[dict[str, Any]],
    memory: "Any",
    cfg: Config,
    *,
    llm: LLMClient,
    gold: dict[str, str] | None,
    use_gold: bool,
) -> None:
    """Fuse insights from a debate batch into the memory object in place.

    Shared/frozen pools use cross-agent contrast distillation; private pools distill from each
    agent's own trajectory via self-reflection. ``use_gold`` (drawn per batch from anchor_rho)
    selects gold-labeled vs consensus-labeled success.
    """
    for item in batch_results:
        question = item["question"]
        answers = item["answers"]
        clusters = cluster_by_normalized_answer(answers)
        majority = majority_cluster(answers)
        endorsement = len(majority["indices"]) / max(len(answers), 1)

        if memory.mode == "private":
            for agent_id, answer in enumerate(answers):
                final = parse_final_answer(answer)
                norm = normalize_answer(final)
                if use_gold:
                    if gold is None or question not in gold:
                        raise ValueError("gold labels are required when the batch is gold-anchored")
                    success = exact_match(final, gold[question])
                else:
                    success = await self_reflect_success(question, answer, cfg=cfg, llm=llm)
                single = [{"norm": norm, "answer": final, "indices": [0], "trajectories": [answer]}]
                insights = await contrast_distill(question, single, {norm: success}, cfg=cfg, llm=llm)
                support_count = cfg.n_solvers if success else 0
                for insight in insights:
                    memory.apply_insight(agent_id, insight, support_count=support_count)
            continue

        cluster_success: dict[str, bool] = {}
        if use_gold:
            if gold is None or question not in gold:
                raise ValueError("gold labels are required when the batch is gold-anchored")
            for cluster in clusters:
                cluster_success[cluster["norm"]] = exact_match(cluster["answer"], gold[question])
        else:
            for cluster in clusters:
                cluster_success[cluster["norm"]] = (len(cluster["indices"]) / max(cfg.n_solvers, 1)) >= cfg.mu

        insights = await contrast_distill(question, clusters, cluster_success, cfg=cfg, llm=llm)
        support_count = int(round(endorsement * max(cfg.n_solvers, 1)))
        for insight in insights:
            memory.apply_insight(0, insight, support_count=support_count)
