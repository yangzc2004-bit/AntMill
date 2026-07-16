"""Stretch adapter skeleton for tau2-bench.

Gamma P4 is explicitly non-blocking. This module exists only to reserve a
clear namespace distinct from the older tau-bench skeleton in sec/tau_env.py.
Wire it once P1-P3 are complete and the tau2-bench package/API has been pinned.
"""
from __future__ import annotations

from typing import Any


TAU2_BENCH_REPO = "https://github.com/sierra-research/tau2-bench"
TAU2_PREREG_SUBSET = "retail"


class Tau2BenchEnv:
    task_id: str = ""

    def __init__(self, env_name: str = TAU2_PREREG_SUBSET, user_model: str | None = None) -> None:
        try:
            import tau2  # type: ignore  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "tau2-bench is not installed or its import name has changed. "
                f"Pin and install it from {TAU2_BENCH_REPO} before running Gamma P4."
            ) from exc
        raise NotImplementedError("Tau2BenchEnv is a P4 stretch skeleton; P1-P3 do not depend on it.")

    def reset(self, task: dict[str, Any]) -> str:
        raise NotImplementedError

    def step(self, action: str) -> tuple[str, bool, dict[str, Any]]:
        raise NotImplementedError

    def tools_doc(self) -> str:
        raise NotImplementedError

    def is_success(self) -> bool:
        raise NotImplementedError


def load_tau2_tasks(env_name: str, n_train: int, n_heldout: int, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raise NotImplementedError(
        "Load tau2-bench tasks into disjoint train/heldout splits after the package API is pinned."
    )
