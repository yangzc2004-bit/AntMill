from __future__ import annotations

import math
import random
from typing import Any

from .config import Config
from .metrics import embedding_similarity, similarity


GAMMA_BUDGET_SCHEDULES: dict[str, dict[int, list[int]]] = {
    "gamma_consolidated_active_cummax": {
        0: [0, 6, 7, 8, 8, 8],
        1: [0, 8, 8, 8, 8, 8],
        2: [0, 8, 8, 8, 8, 8],
        3: [0, 6, 6, 7, 8, 9],
        4: [0, 7, 8, 8, 8, 9],
    }
}


class InsightMemory:
    """Insight pools with ExpeL-style top-k retrieval and voting-based fusion.

    Modes:
      none    - no writes, no retrieval (memory-off baseline).
      shared  - one global pool; all agents read and write it (stigmergic channel).
      private - one pool per agent; each agent reads/writes only its own.
      frozen  - accumulate into the shared pool but NEVER inject (retrieval returns []),
                isolating the feedback loop from accumulation per se.

    Retrieval scoring (cfg.retrieval_scoring):
      similarity - legacy lexical top-k against the query.
      ga         - Generative-Agents-style scoring over min-max normalized components:
                   relevance (stable-embedding cosine) + ga_lambda * importance
                   (consensus votes) + ga_recency * recency (last access round).
                   ga_lambda is the positive-feedback strength dial; ga_recency adds
                   the GA usage-feedback channel (retrieval refreshes recency).
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.mode = cfg.memory_mode
        self.shared: list[dict[str, Any]] = []
        self.private: dict[int, list[dict[str, Any]]] = {}
        self.archive: list[dict[str, Any]] = []
        self._budget_keys: set[str] = set()
        self._budget_snapshots: list[dict[str, Any]] = []
        self._last_retrieval_metadata: dict[int, dict[str, Any]] = {}

    def _private_pool(self, agent_id: int) -> list[dict[str, Any]]:
        return self.private.setdefault(agent_id, [])

    def pool_view(self, agent_id: int) -> list[dict[str, Any]]:
        """The pool an agent reads/writes (shared/frozen -> global, private -> own)."""
        if self.mode == "private":
            return self._private_pool(agent_id)
        return self.shared

    def set_pool(self, agent_id: int, pool: list[dict[str, Any]]) -> None:
        if self.mode == "private":
            self.private[agent_id] = pool
        else:
            self.shared = pool

    def retrieve(self, agent_id: int, query: str, *, t: int | None = None) -> list[dict[str, Any]]:
        read_protocol = getattr(self.cfg, "memory_read_protocol", "standard")
        if self.mode in {"none", "frozen"}:
            self._last_retrieval_metadata[agent_id] = self._retrieval_metadata(
                read_protocol=read_protocol,
                active_candidates=[],
                archive_candidates=[],
                selected=[],
                total_limit=0,
                joint_rank=False,
            )
            return []
        pool = self.shared if self.mode == "shared" else self._private_pool(agent_id)
        if not pool and read_protocol == "standard":
            self._last_retrieval_metadata[agent_id] = self._retrieval_metadata(
                read_protocol=read_protocol,
                active_candidates=[],
                archive_candidates=[],
                selected=[],
                total_limit=max(int(self.cfg.retrieval_k), 0),
                joint_rank=False,
            )
            return []
        active_pool = self._budgeted_pool(pool, t=t) if read_protocol == "budgeted_append" else pool
        archive_pool = self.archive if read_protocol in {"archive_rescue", "archive_joint_topk"} else []
        joint_rank = read_protocol == "archive_joint_topk"
        if joint_rank:
            selected = self._rank(list(active_pool) + list(archive_pool), query, k=self.cfg.retrieval_k, t=t)
            total_limit = _effective_limit(int(self.cfg.retrieval_k), list(active_pool) + list(archive_pool))
        else:
            selected = self._rank(active_pool, query, k=self.cfg.retrieval_k, t=t)
            total_limit = _effective_limit(int(self.cfg.retrieval_k), active_pool)
        if read_protocol == "archive_rescue" and archive_pool:
            archive_k = int(getattr(self.cfg, "archive_retrieval_k", 0))
            selected = selected + self._rank(archive_pool, query, k=archive_k, t=t)
            total_limit += _effective_limit(archive_k, archive_pool)
        if t is not None:
            # Usage feedback: retrieval refreshes recency (GA memory-stream semantics).
            for item in selected:
                item["last_access_t"] = t
        self._last_retrieval_metadata[agent_id] = self._retrieval_metadata(
            read_protocol=read_protocol,
            active_candidates=active_pool,
            archive_candidates=archive_pool,
            selected=selected,
            total_limit=total_limit,
            joint_rank=joint_rank,
        )
        return selected

    def _rank(self, pool: list[dict[str, Any]], query: str, *, k: int, t: int | None) -> list[dict[str, Any]]:
        if not pool:
            return []
        scoring = getattr(self.cfg, "retrieval_scoring", "similarity")
        if scoring in {"ga", "ga_mmr"}:
            ranked = self._ga_rank_entries(pool, query, t=t)
            if scoring == "ga_mmr":
                ranked = self._mmr_rerank(ranked, k=k)
        else:
            ranked = [
                (
                    item,
                    float(similarity(query, item.get("text", ""))),
                    float(similarity(query, item.get("text", ""))),
                )
                for item in pool
            ]
            ranked.sort(key=lambda row: (row[1], str(row[0].get("text", ""))), reverse=True)
        selected = ranked if k <= 0 else ranked[:k]
        for rank, (item, score, relevance) in enumerate(selected, start=1):
            item["_retrieval_rank"] = rank
            item["_retrieval_score"] = score
            item["_retrieval_relevance"] = relevance
        return [item for item, _, _ in selected]

    def _mmr_rerank(
        self,
        ranked: list[tuple[dict[str, Any], float, float]],
        *,
        k: int,
    ) -> list[tuple[dict[str, Any], float, float]]:
        """Greedily select high-scoring items that are diverse from prior selections.

        The persisted score remains the underlying GA score. MMR changes only which
        items reach the prompt; it never writes, merges, edits, or down-votes memory.
        """
        limit = len(ranked) if k <= 0 else min(k, len(ranked))
        if limit <= 1:
            return ranked[:limit]
        relevance_weight = float(self.cfg.mmr_relevance_weight)
        remaining = list(ranked)
        selected: list[tuple[dict[str, Any], float, float]] = []
        while remaining and len(selected) < limit:
            candidate_index = 0
            candidate_key: tuple[float, float, float, str] | None = None
            for index, (item, score, relevance) in enumerate(remaining):
                redundancy = max(
                    (
                        embedding_similarity(
                            str(item.get("text", "")),
                            str(previous[0].get("text", "")),
                        )
                        for previous in selected
                    ),
                    default=0.0,
                )
                objective = relevance_weight * score - (1.0 - relevance_weight) * redundancy
                key = (objective, score, relevance, str(item.get("text", "")))
                if candidate_key is None or key > candidate_key:
                    candidate_index = index
                    candidate_key = key
            selected.append(remaining.pop(candidate_index))
        return selected

    def _ga_rank(self, pool: list[dict[str, Any]], query: str, *, t: int | None) -> list[dict[str, Any]]:
        return [item for item, _, _ in self._ga_rank_entries(pool, query, t=t)]

    def _ga_rank_entries(
        self,
        pool: list[dict[str, Any]],
        query: str,
        *,
        t: int | None,
    ) -> list[tuple[dict[str, Any], float, float]]:
        relevance = [embedding_similarity(query, str(item.get("text", ""))) for item in pool]
        importance = [math.log1p(max(int(item.get("votes", 0)), 0)) for item in pool]
        recency = [float(item.get("last_access_t", -1)) for item in pool]
        rel_n = _minmax(relevance)
        imp_n = _minmax(importance)
        rec_n = _minmax(recency)
        lam = float(self.cfg.ga_lambda)
        rho = float(self.cfg.ga_recency)
        scored = [
            (rel_n[i] + lam * imp_n[i] + rho * rec_n[i], relevance[i], str(pool[i].get("text", "")), i)
            for i in range(len(pool))
        ]
        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        return [(pool[i], float(score), float(rel)) for score, rel, _, i in scored]

    def retrieval_metadata(self, agent_id: int) -> dict[str, Any]:
        return dict(self._last_retrieval_metadata.get(agent_id, {}))

    def _retrieval_metadata(
        self,
        *,
        read_protocol: str,
        active_candidates: list[dict[str, Any]],
        archive_candidates: list[dict[str, Any]],
        selected: list[dict[str, Any]],
        total_limit: int,
        joint_rank: bool,
    ) -> dict[str, Any]:
        active_injected = sum(1 for item in selected if not item.get("archived"))
        archive_injected = len(selected) - active_injected
        return {
            "read_protocol": read_protocol,
            "joint_rank": joint_rank,
            "configured_total_limit": total_limit,
            "active_candidate_count": len(active_candidates),
            "archive_candidate_count": len(archive_candidates),
            "injected_count": len(selected),
            "active_injected": active_injected,
            "archive_injected": archive_injected,
            "dose_compliant": len(selected) <= total_limit if total_limit > 0 else len(selected) == 0,
            "ranking": [
                {
                    "id": item.get("id") or _item_key(item),
                    "source": "archive" if item.get("archived") else "active",
                    "archive_source": item.get("archive_source", ""),
                    "rank": int(item.get("_retrieval_rank", rank)),
                    "score": float(item.get("_retrieval_score", 0.0)),
                    "relevance": float(item.get("_retrieval_relevance", 0.0)),
                }
                for rank, item in enumerate(selected, start=1)
            ],
        }

    def _budgeted_pool(self, pool: list[dict[str, Any]], *, t: int | None) -> list[dict[str, Any]]:
        budget = self.budget_for_round(t)
        if budget <= 0:
            return []
        candidates = [item for item in pool if _item_key(item) not in self._budget_keys]
        if len(self._budget_snapshots) < budget and candidates:
            rng = random.Random(f"budgeted_append|seed={self.cfg.seed}|t={t if t is not None else 0}")
            shuffled = list(candidates)
            rng.shuffle(shuffled)
            for item in shuffled:
                if len(self._budget_snapshots) >= budget:
                    break
                key = _item_key(item)
                if key in self._budget_keys:
                    continue
                snap = dict(item)
                snap.setdefault("id", key)
                snap["budgeted_append_snapshot"] = True
                snap["budgeted_append_selected_t"] = t
                self._budget_keys.add(key)
                self._budget_snapshots.append(snap)
        return list(self._budget_snapshots[:budget])

    def budget_for_round(self, t: int | None) -> int:
        schedule_name = self.cfg.budget_schedule_name or "gamma_consolidated_active_cummax"
        schedule_by_seed = GAMMA_BUDGET_SCHEDULES.get(schedule_name, {})
        schedule = schedule_by_seed.get(int(self.cfg.seed), [])
        if not schedule:
            return 0
        idx = max(0, min(int(t or 0), len(schedule) - 1))
        return max(schedule[: idx + 1])

    def add_archive_item(
        self,
        item: dict[str, Any],
        *,
        source: str,
        t: int,
        task_id: str,
        agent_id: int,
        op: str = "",
    ) -> None:
        text = str(item.get("text", "")).strip()
        if not text:
            return
        record = {
            "kind": item.get("kind", "do"),
            "text": text,
            "votes": int(item.get("votes", 0)),
            "id": f"archive:{source}:{_item_key(item)}",
            "archive_source": source,
            "archived": True,
            "retrieval_count": 0,
            "archive_events": [{"t": t, "task_id": task_id, "agent_id": agent_id, "op": op}],
        }
        key = str(record["id"])
        for existing in self.archive:
            if existing.get("id") == key:
                existing.setdefault("archive_events", []).append(record["archive_events"][0])
                return
        self.archive.append(record)

    def apply_insight(self, agent_id: int, insight: dict[str, Any], *, support_count: int) -> None:
        from .fusion import _apply_insight  # local import to avoid a circular import

        if self.mode == "none":
            return
        if self.mode in {"shared", "frozen"}:
            self.shared = _apply_insight(self.shared, insight, cfg=self.cfg, support_count=support_count)
        else:
            self.private[agent_id] = _apply_insight(
                self._private_pool(agent_id), insight, cfg=self.cfg, support_count=support_count
            )

    def all_items(self) -> list[dict[str, Any]]:
        items = list(self.shared)
        for pool in self.private.values():
            items.extend(pool)
        return items

    def size(self) -> int:
        if self.mode == "private":
            return sum(len(pool) for pool in self.private.values())
        return len(self.shared)

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "shared": self.shared,
            "private": {str(k): v for k, v in self.private.items()},
            "archive": self.archive,
            "budgeted_append": {
                "schedule": self.cfg.budget_schedule_name or "gamma_consolidated_active_cummax",
                "budget_current": self.budget_for_round(None),
                "selected_ids": [item.get("id") for item in self._budget_snapshots],
                "selected_items": self._budget_snapshots,
            },
            "size": self.size(),
        }


def _minmax(values: list[float]) -> list[float]:
    lo = min(values)
    hi = max(values)
    if hi - lo <= 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _item_key(item: dict[str, Any]) -> str:
    from .metrics import normalize_answer

    return normalize_answer(f"{item.get('kind', 'do')} {item.get('text', '')}")[:96]


def _effective_limit(k: int, pool: list[dict[str, Any]]) -> int:
    return k if k > 0 else len(pool)
