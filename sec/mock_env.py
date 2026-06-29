from __future__ import annotations

from typing import Any


class MockToolEnv:
    """Tiny deterministic tool environment for offline tests.

    Task: enable a target feature flag, then submit. Tools: read | set:<flag> | submit.
    `behavior="loop"` tasks are unsolvable-by-design so a naive agent repeats an action forever,
    exercising the silent death-loop / non-termination detection without raising any error.
    """

    def __init__(self) -> None:
        self.task_id = ""
        self._target = ""
        self._behavior = "solve"
        self._flags: set[str] = set()
        self._submitted = False

    def reset(self, task: dict[str, Any]) -> str:
        self.task_id = str(task.get("task_id", ""))
        self._target = str(task["target"])
        self._behavior = str(task.get("behavior", "solve"))
        self._flags = set()
        self._submitted = False
        return self._obs()

    def _obs(self) -> str:
        return (
            f"Goal: enable feature {self._target}. MODE:{self._behavior}. "
            f"State flags: [{', '.join(sorted(self._flags))}]"
        )

    def step(self, action: str) -> tuple[str, bool, dict[str, Any]]:
        a = action.strip()
        low = a.lower()
        if low.startswith("set:"):
            self._flags.add(a.split(":", 1)[1].strip())
        elif low.startswith("submit"):
            self._submitted = True
            return self._obs(), True, {"submitted": True}
        elif low.startswith("read"):
            pass
        else:
            # tool error is returned as an observation, never raised
            return f"Unknown action {action!r}. {self._obs()}", False, {"error": True}
        return self._obs(), False, {}

    def tools_doc(self) -> str:
        return "read | set:<flag> | submit"

    def is_success(self) -> bool:
        return self._submitted and self._target in self._flags


def make_tasks(n_solve: int, n_loop: int) -> list[dict[str, Any]]:
    tasks = [{"task_id": f"solve_{i}", "target": f"F{i}", "behavior": "solve"} for i in range(n_solve)]
    tasks += [{"task_id": f"loop_{i}", "target": f"G{i}", "behavior": "loop"} for i in range(n_loop)]
    return tasks
