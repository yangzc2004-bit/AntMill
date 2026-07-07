from __future__ import annotations

import math
from typing import Any

from .config import Config
from .metrics import embedding_similarity, similarity


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
        if self.mode in {"none", "frozen"}:
            return []
        pool = self.shared if self.mode == "shared" else self._private_pool(agent_id)
        if not pool:
            return []
        k = self.cfg.retrieval_k
        if k <= 0:
            selected = list(pool)  # legacy whole-pool injection
        elif getattr(self.cfg, "retrieval_scoring", "similarity") == "ga":
            selected = self._ga_rank(pool, query, t=t)[:k]
        else:
            selected = sorted(pool, key=lambda item: similarity(query, item.get("text", "")), reverse=True)[:k]
        if t is not None:
            # Usage feedback: retrieval refreshes recency (GA memory-stream semantics).
            for item in selected:
                item["last_access_t"] = t
        return selected

    def _ga_rank(self, pool: list[dict[str, Any]], query: str, *, t: int | None) -> list[dict[str, Any]]:
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
        return [pool[i] for _, _, _, i in scored]

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
            "size": self.size(),
        }


def _minmax(values: list[float]) -> list[float]:
    lo = min(values)
    hi = max(values)
    if hi - lo <= 1e-12:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
