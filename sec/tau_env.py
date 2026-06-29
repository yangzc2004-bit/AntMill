"""Adapter skeleton for tau-bench (sierra-research/tau-bench).

Not runnable in an offline environment: tau-bench is not on PyPI. On a machine with internet and
API keys, install it with:

    pip install git+https://github.com/sierra-research/tau-bench

tau-bench also runs an LLM "user simulator", so set the relevant provider API-key env vars.

To wire it up, implement the Environment protocol from `sec.agentic` by wrapping a tau-bench env:
  - reset(task):   start a tau-bench task; return the initial user message / observation text.
  - step(action):  pass the agent's tool call / message into tau-bench; return (obs, done, info).
                   Tool/runtime errors should be returned as observation text, never raised.
  - tools_doc():   render the task's tool schema as text for the agent prompt.
  - is_success():  tau-bench reward / DB-state check == 1.

`load_tau_tasks` should return (train_pool, heldout) lists of task dicts, mirroring
`sec.data.load_benchmark`. Keep them disjoint.

This file intentionally raises clear errors until wired up, so the rest of the package imports
cleanly offline and the mock-tested agentic core (sec/agentic.py) is unaffected.
"""
from __future__ import annotations

from typing import Any


class TauBenchEnv:
    task_id: str = ""

    def __init__(self, env_name: str = "retail", user_model: str | None = None) -> None:
        try:
            import tau_bench  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "tau-bench is not installed. On a machine with internet run:\n"
                "  pip install git+https://github.com/sierra-research/tau-bench\n"
                "then implement TauBenchEnv against it (see this module's docstring)."
            ) from exc
        raise NotImplementedError("TauBenchEnv is a skeleton; wire it to tau_bench here.")

    def reset(self, task: dict[str, Any]) -> str:
        raise NotImplementedError

    def step(self, action: str) -> tuple[str, bool, dict[str, Any]]:
        raise NotImplementedError

    def tools_doc(self) -> str:
        raise NotImplementedError

    def is_success(self) -> bool:
        raise NotImplementedError


def load_tau_tasks(env_name: str, n_train: int, n_heldout: int, seed: int):
    raise NotImplementedError(
        "Load tau-bench tasks and split into disjoint (train_pool, heldout); see module docstring."
    )
