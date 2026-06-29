from __future__ import annotations

from typing import Any

from .config import Config
from .metrics import similarity


class InsightMemory:
    """Insight pools with ExpeL-style top-k retrieval and voting-based fusion.

    Modes:
      none    - no writes, no retrieval (memory-off baseline).
      shared  - one global pool; all agents read and write it (stigmergic channel).
      private - one pool per agent; each agent reads/writes only its own.
      frozen  - accumulate into the shared pool but NEVER inject (retrieval returns []),
                isolating the feedback loop from accumulation per se.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.mode = cfg.memory_mode
        self.shared: list[dict[str, Any]] = []
        self.private: dict[int, list[dict[str, Any]]] = {}

    def _private_pool(self, agent_id: int) -> list[dict[str, Any]]:
        return self.private.setdefault(agent_id, [])

    def retrieve(self, agent_id: int, query: str) -> list[dict[str, Any]]:
        if self.mode in {"none", "frozen"}:
            return []
        pool = self.shared if self.mode == "shared" else self._private_pool(agent_id)
        if not pool:
            return []
        k = self.cfg.retrieval_k
        if k <= 0:
            return list(pool)  # legacy whole-pool injection
        scored = sorted(pool, key=lambda item: similarity(query, item.get("text", "")), reverse=True)
        return scored[:k]

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
