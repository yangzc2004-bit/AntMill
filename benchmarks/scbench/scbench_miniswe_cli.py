"""Load the pinned upstream MiniSWE implementation, then enter SCBench's CLI.

The pinned SCBench commit contains both ``agents/miniswe.py`` and an
``agents/miniswe/`` parser package. Python resolves the package first, so the
implementation's registration side effect is otherwise skipped.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import sys
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


def message_content_for_miniswe(message: object) -> str:
    content = getattr(message, "content", None)
    if content:
        return str(content)

    for tool_call in getattr(message, "tool_calls", None) or ():
        function = getattr(tool_call, "function", None)
        if function is None or str(getattr(function, "name", "")).lower() != "bash":
            continue
        arguments = getattr(function, "arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"command": arguments}
        if not isinstance(arguments, dict):
            continue
        command = str(arguments.get("command", "")).strip()
        if command:
            return (
                "THOUGHT: Execute the requested shell action.\n\n"
                f"```bash\n{command}\n```"
            )
    return ""


def register_upstream_miniswe() -> None:
    import slop_code.agent_runner as agent_runner
    from slop_code.agent_runner import trajectory
    from slop_code.agent_runner.models import AgentRunSpec

    class LocalAgentRunSpec(AgentRunSpec):
        image: str | None = None

    class StepRole(str, Enum):
        SYSTEM = "system"
        USER = "user"
        ASSISTANT = "assistant"
        ENVIRONMENT = "environment"

    class LegacyTrajectoryStep(BaseModel):
        role: StepRole
        content: str
        wall_clock_time: float = 0.0
        cost: float = 0.0
        tokens: object | None = None
        meta: dict[str, object] = Field(default_factory=dict)

    trajectory.StepRole = StepRole
    trajectory.TrajectoryStep = LegacyTrajectoryStep
    agent_runner.AgentRunSpec = LocalAgentRunSpec

    source = Path(
        "/opt/scbench/src/slop_code/agent_runner/agents/miniswe.py"
    )
    spec = importlib.util.spec_from_file_location(
        "slop_code.agent_runner.agents._miniswe_impl", source
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load upstream MiniSWE implementation: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    from minisweagent.models import litellm_model
    from minisweagent.models.utils.cache_control import set_cache_control

    def query_without_catalog_pricing(self, messages, **kwargs):
        if self.config.set_cache_control:
            messages = set_cache_control(
                messages, mode=self.config.set_cache_control
            )
        response = self._query(messages, **kwargs)
        self.n_calls += 1
        message = response.choices[0].message
        reasoning = getattr(message, "reasoning_content", None)
        extra = response.model_dump()
        usage = extra.get("usage")
        if isinstance(usage, dict):
            for details_key in (
                "prompt_tokens_details",
                "completion_tokens_details",
            ):
                if usage.get(details_key) is None:
                    usage[details_key] = {}
        return {
            "content": message_content_for_miniswe(message),
            "reasoning": reasoning,
            "extra": extra,
        }

    litellm_model.LitellmModel.query = query_without_catalog_pricing


def terminate_lingering_descendants() -> None:
    """Stop agent-started processes before correctness-test collection."""
    root_pid = os.getpid()
    parent_by_pid: dict[int, int] = {}
    for status_path in Path("/proc").glob("[0-9]*/status"):
        try:
            pid = int(status_path.parent.name)
            parent = next(
                line
                for line in status_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if line.startswith("PPid:")
            )
            parent_by_pid[pid] = int(parent.split()[1])
        except (OSError, StopIteration, ValueError):
            continue

    descendants: set[int] = set()
    frontier = {root_pid}
    while frontier:
        children = {
            pid
            for pid, parent in parent_by_pid.items()
            if parent in frontier and pid not in descendants
        }
        descendants.update(children)
        frontier = children

    for sig, delay in ((signal.SIGTERM, 0.25), (signal.SIGKILL, 0.0)):
        for pid in sorted(descendants, reverse=True):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
        if delay:
            time.sleep(delay)


def disable_non_scoring_quality_analysis() -> None:
    """Keep correctness evaluation while skipping optional static analysis."""
    from slop_code.agent_runner import runner
    from slop_code.entrypoints.commands import eval_checkpoint
    from slop_code.entrypoints.evaluation.driver import (
        CheckpointEvaluationResult,
    )
    from slop_code.evaluation import collection
    from slop_code.evaluation.collection import compute_tc_hash
    from slop_code.evaluation.pytest_runner import PytestRunner
    from slop_code.evaluation.pytest_runner import run_checkpoint_pytest
    from slop_code.metrics.models import LineCountMetrics
    from slop_code.metrics.models import SnapshotQualityReport

    def run_checkpoint_from_execution_report(
        *,
        submission_path,
        problem,
        checkpoint,
        env_spec,
        pytest_args=None,
    ):
        """Use pytest's execution report as the canonical test inventory.

        Upstream performs four additional marker-specific collection passes
        before the real test run. Environment setup can fail on only one of
        those passes and silently relabel its tests as Core. The real
        pytest-json-report already contains each test's marker keywords, so it
        is both faster and more stable to derive the inventory from that
        single execution.
        """
        pytest_runner = PytestRunner(
            problem=problem,
            checkpoint=checkpoint,
            environment=env_spec,
            submission_path=submission_path,
        )
        results = pytest_runner.run(pytest_args=pytest_args)

        grouped_test_ids: dict[str, list[str]] = {}
        for test in results.tests:
            group_type = getattr(test.group_type, "value", test.group_type)
            key = f"{test.checkpoint}-{group_type}"
            grouped_test_ids.setdefault(key, []).append(test.id)

        results.test_collection_hash = compute_tc_hash(grouped_test_ids)
        if results.pytest_collected != len(results.tests):
            results.infrastructure_failure = True
        return results

    collection.run_checkpoint_with_collection = (
        run_checkpoint_from_execution_report
    )

    def empty_quality_report() -> SnapshotQualityReport:
        return SnapshotQualityReport(
            files=0,
            overall_lines=LineCountMetrics(
                total_lines=0,
                loc=0,
                comments=0,
                multi_comment=0,
                single_comment=0,
            ),
            lint_errors=0,
            lint_fixable=0,
            cc_counts={},
            mi={},
        )

    def evaluate_without_quality(
        checkpoint,
        save_dir,
        snapshot_dir,
        problem,
        environment,
    ):
        terminate_lingering_descendants()
        report = runner.evaluate_checkpoint(
            submission_path=snapshot_dir,
            problem=problem,
            checkpoint=checkpoint,
            env_spec=environment,
        )
        report.save(save_dir)
        return report, empty_quality_report()

    def evaluate_checkpoint_without_quality(
        snapshot,
        save_dir,
        checkpoint,
        problem,
        environment,
        **_kwargs,
    ):
        terminate_lingering_descendants()
        report = run_checkpoint_pytest(
            submission_path=snapshot,
            problem=problem,
            checkpoint=checkpoint,
            env_spec=environment,
        )
        report.save(save_dir)
        return CheckpointEvaluationResult(
            problem_name=problem.name,
            checkpoint_name=checkpoint.name,
            report=report,
            quality=empty_quality_report(),
            rubric_grades=None,
        )

    runner.evaluate_agent_snapshot = evaluate_without_quality
    eval_checkpoint.evaluate_checkpoint = evaluate_checkpoint_without_quality


register_upstream_miniswe()
disable_non_scoring_quality_analysis()

from slop_code.entrypoints.cli import app  # noqa: E402


if __name__ == "__main__":
    app()
