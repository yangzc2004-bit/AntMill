from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Literal, Protocol, Sequence

from autogen_core import (
    AgentId,
    MessageContext,
    RoutedAgent,
    SingleThreadedAgentRuntime,
    message_handler,
)


XJQ_WHEELHOUSE_FILES = (
    "attrs-26.1.0-py3-none-any.whl",
    "cachebox-5.2.3-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "cssselect-1.4.0-py3-none-any.whl",
    "deepdiff-9.1.0-py3-none-any.whl",
    "iniconfig-2.3.0-py3-none-any.whl",
    "jsonschema-4.26.0-py3-none-any.whl",
    "jsonschema_specifications-2025.9.1-py3-none-any.whl",
    "lxml-6.1.1-cp312-cp312-manylinux_2_26_x86_64."
    "manylinux_2_28_x86_64.whl",
    "orderly_set-5.5.0-py3-none-any.whl",
    "packaging-26.2-py3-none-any.whl",
    "pluggy-1.6.0-py3-none-any.whl",
    "pygments-2.20.0-py3-none-any.whl",
    "pytest-9.1.1-py3-none-any.whl",
    "pytest_json_ctrf-0.5.2-py3-none-any.whl",
    "pytest_json_report-1.5.0-py3-none-any.whl",
    "pytest_metadata-3.1.1-py3-none-any.whl",
    "pytest_timeout-2.4.0-py3-none-any.whl",
    "referencing-0.37.0-py3-none-any.whl",
    "rpds_py-2026.6.3-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "typing_extensions-4.16.0-py3-none-any.whl",
)

DATAGATE_WHEELHOUSE_FILES = XJQ_WHEELHOUSE_FILES + (
    "anyio-4.14.2-py3-none-any.whl",
    "blinker-1.9.0-py3-none-any.whl",
    "certifi-2026.6.17-py3-none-any.whl",
    "charset_normalizer-3.4.9-cp312-cp312-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
    "click-8.4.2-py3-none-any.whl",
    "colorama-0.4.6-py2.py3-none-any.whl",
    "flask-3.1.3-py3-none-any.whl",
    "h11-0.16.0-py3-none-any.whl",
    "httpcore-1.0.9-py3-none-any.whl",
    "httpx-0.28.1-py3-none-any.whl",
    "idna-3.18-py3-none-any.whl",
    "itsdangerous-2.2.0-py3-none-any.whl",
    "jinja2-3.1.6-py3-none-any.whl",
    "markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
    "werkzeug-3.1.8-py3-none-any.whl",
)

ETL_PIPELINE_WHEELHOUSE_FILES = XJQ_WHEELHOUSE_FILES + (
    "duckdb-1.1.1-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "jsonschema-4.21.1-py3-none-any.whl",
    "pytest-8.3.2-py3-none-any.whl",
    "sqlglot-24.1.3-py3-none-any.whl",
)

FILE_MERGER_WHEELHOUSE_FILES = XJQ_WHEELHOUSE_FILES + (
    "numpy-2.2.6-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "pyarrow-16.1.0-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "pytest-8.1.1-py3-none-any.whl",
    "pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
)

EXECUTION_SERVER_WHEELHOUSE_FILES = DATAGATE_WHEELHOUSE_FILES + (
    "annotated_doc-0.0.4-py3-none-any.whl",
    "annotated_types-0.7.0-py3-none-any.whl",
    "bracex-3.0-py3-none-any.whl",
    "fastapi-0.139.0-py3-none-any.whl",
    "httptools-0.8.0-cp312-cp312-manylinux1_x86_64."
    "manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl",
    "numpy-2.2.6-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "pydantic-2.13.4-py3-none-any.whl",
    "pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "pytest_asyncio-1.3.0-py3-none-any.whl",
    "python_dotenv-1.2.2-py3-none-any.whl",
    "pyyaml-6.0.3-cp312-cp312-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
    "starlette-1.3.1-py3-none-any.whl",
    "typing_inspection-0.4.2-py3-none-any.whl",
    "uvicorn-0.51.0-py3-none-any.whl",
    "uvloop-0.22.1-cp312-cp312-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
    "watchfiles-1.2.0-cp312-cp312-manylinux_2_17_x86_64."
    "manylinux2014_x86_64.whl",
    "wcmatch-11.0-py3-none-any.whl",
    "websockets-16.1-cp312-cp312-manylinux1_x86_64."
    "manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl",
)

LOCAL_WHEELHOUSE_FILES = {
    "cfgpipe": XJQ_WHEELHOUSE_FILES,
    "datagate": DATAGATE_WHEELHOUSE_FILES,
    "etl_pipeline": ETL_PIPELINE_WHEELHOUSE_FILES,
    "execution_server": EXECUTION_SERVER_WHEELHOUSE_FILES,
    "file_merger": FILE_MERGER_WHEELHOUSE_FILES,
    "l2m": XJQ_WHEELHOUSE_FILES,
    "xjq": XJQ_WHEELHOUSE_FILES,
}


def scbench_local_wheelhouse(
    repo_root: Path,
    problem_name: str,
) -> Path | None:
    wheelhouse = repo_root / "cache_scbench_wheelhouse"
    required_files = LOCAL_WHEELHOUSE_FILES.get(problem_name)
    if (
        required_files is not None
        and all((wheelhouse / name).is_file() for name in required_files)
    ):
        return wheelhouse.resolve()
    return None


AssimilationMode = Literal[
    "no_transfer",
    "source_success",
    "cumulative_success",
    "cumulative_local_acceptance",
    "cumulative_self_report_acceptance",
    "bounded_recent_self_report_acceptance",
    "bounded_diverse_self_report_acceptance",
    "recipient_credit",
    "recursive_synthesis",
    "recursive_self_report_synthesis",
]


@dataclass(frozen=True)
class VerificationResult:
    core_passed: int
    core_total: int
    pytest_exit_code: int
    infrastructure_failure: bool
    test_collection_hash: str = ""
    pytest_collected: int = 0
    all_passed: int = 0
    all_total: int = 0

    @property
    def score(self) -> float:
        if self.infrastructure_failure or self.core_total <= 0:
            return 0.0
        return self.core_passed / self.core_total

    @property
    def all_score(self) -> float:
        if self.infrastructure_failure or self.all_total <= 0:
            return 0.0
        return self.all_passed / self.all_total

    @property
    def core_verified(self) -> bool:
        return (
            not self.infrastructure_failure
            and self.core_total > 0
            and self.core_passed == self.core_total
        )

    @property
    def passed(self) -> bool:
        return (
            self.core_verified
            and self.pytest_exit_code == 0
        )


@dataclass(frozen=True)
class ExperienceArtifact:
    artifact_id: str
    source_worker: str
    source_layer: int
    summary: str
    verification: VerificationResult
    complexity: int = 0


@dataclass(frozen=True)
class WorkerTelemetry:
    duration_sec: float = 0.0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    received_results: int = 0
    received_experience_chars: int = 0
    experience_chars: int = 0
    snapshot_files: int = 0
    snapshot_bytes: int = 0
    local_validation_passed: bool = False
    local_validation_commands: int = 0
    self_reported_success: bool = False


@dataclass(frozen=True)
class WorkerOutput:
    worker_id: str
    layer: int
    workspace: str
    summary: str
    verification: VerificationResult
    artifact: ExperienceArtifact
    telemetry: WorkerTelemetry = WorkerTelemetry()


@dataclass(frozen=True)
class WorkerRequest:
    task_id: str
    task: str
    worker_id: str
    layer: int
    workspace: str
    previous_results: tuple[WorkerOutput, ...]


@dataclass(frozen=True)
class WorkerTask:
    task_id: str
    task: str
    layer: int
    previous_results: tuple[WorkerOutput, ...]


@dataclass(frozen=True)
class WorkerTaskResult:
    output: WorkerOutput


@dataclass(frozen=True)
class UserTask:
    task_id: str
    task: str


@dataclass(frozen=True)
class FinalResult:
    task_id: str
    answer: str
    layers: tuple[tuple[WorkerOutput, ...], ...]


class WorkerBackend(Protocol):
    async def run(self, request: WorkerRequest) -> WorkerOutput:
        ...


class AggregatorBackend(Protocol):
    async def synthesize(
        self, task_id: str, task: str, results: Sequence[WorkerOutput]
    ) -> str:
        ...


class RecursiveSynthesisBackend(Protocol):
    async def synthesize_layer(
        self,
        task_id: str,
        task: str,
        layer: int,
        previous_shared: WorkerOutput | None,
        verified_results: Sequence[WorkerOutput],
    ) -> WorkerOutput:
        ...


class AssimilationPolicy(Protocol):
    mode: AssimilationMode

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        ...

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        ...


@dataclass
class NoTransferPolicy:
    mode: AssimilationMode = "no_transfer"

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer, layer_history
        return ()

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


@dataclass
class SourceSuccessPolicy:
    mode: AssimilationMode = "source_success"

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del layer_history
        if not previous_layer:
            return ()
        return tuple(
            result
            for result in previous_layer
            if result.verification.core_verified
        )

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


@dataclass
class CumulativeSuccessPolicy:
    """Broadcast every Core-verified output produced by any completed layer."""

    mode: AssimilationMode = "cumulative_success"
    seed_results: tuple[WorkerOutput, ...] = ()

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer
        return self.seed_results + tuple(
            result
            for completed_layer in layer_history
            for result in completed_layer
            if result.verification.core_verified
        )

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


@dataclass
class CumulativeLocalAcceptancePolicy:
    """Accumulate outputs accepted by an agent-local completion proxy."""

    mode: AssimilationMode = "cumulative_local_acceptance"
    seed_results: tuple[WorkerOutput, ...] = ()

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer
        accepted = tuple(
            self._as_local_reference(result)
            for completed_layer in layer_history
            for result in completed_layer
            if result.telemetry.local_validation_passed
        )
        return self.seed_results + accepted

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer

    @staticmethod
    def _as_local_reference(result: WorkerOutput) -> WorkerOutput:
        return _as_blinded_proxy_reference(
            result,
            artifact_suffix="local_acceptance",
            test_collection_hash="local-completion-smoke-proxy",
            acceptance_text=(
                "Local agent validation: accepted by completion-and-smoke "
                "proxy; external evaluation withheld."
            ),
        )


@dataclass
class CumulativeSelfReportAcceptancePolicy:
    """Accumulate every output whose agent text claims successful completion."""

    mode: AssimilationMode = "cumulative_self_report_acceptance"
    seed_results: tuple[WorkerOutput, ...] = ()

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer
        accepted = tuple(
            self._as_self_report_reference(result)
            for completed_layer in layer_history
            for result in completed_layer
            if result.telemetry.self_reported_success
        )
        return self.seed_results + accepted

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer

    @staticmethod
    def _as_self_report_reference(result: WorkerOutput) -> WorkerOutput:
        return _as_blinded_proxy_reference(
            result,
            artifact_suffix="self_report_acceptance",
            test_collection_hash="self-report-completion-proxy",
            acceptance_text=(
                "Agent completion report: accepted without an independent "
                "smoke check; external evaluation withheld."
            ),
        )


@dataclass
class BoundedRecentSelfReportAcceptancePolicy:
    """Broadcast only the latest self-reported outputs under a fixed cap."""

    mode: AssimilationMode = "bounded_recent_self_report_acceptance"
    seed_results: tuple[WorkerOutput, ...] = ()
    reference_limit: int = 3

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer
        accepted = [
            CumulativeSelfReportAcceptancePolicy._as_self_report_reference(
                result
            )
            for completed_layer in layer_history
            for result in completed_layer
            if result.telemetry.self_reported_success
        ]
        candidates = [*self.seed_results, *accepted]
        return tuple(candidates[-self.reference_limit :])

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


_IMPLEMENTATION_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".ts",
    ".tsx",
}
_FINGERPRINT_IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "tests",
}


def _workspace_implementation_fingerprint(workspace: str) -> str | None:
    """Hash local implementation files without consulting evaluator output."""
    root = Path(workspace)
    if not root.is_dir():
        return None
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in _IMPLEMENTATION_SUFFIXES
        and not any(
            part.lower() in _FINGERPRINT_IGNORED_PARTS
            for part in path.relative_to(root).parts
        )
        and not path.name.lower().startswith("test_")
        and not path.name.lower().endswith("_test.py")
    )
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            return None
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass
class BoundedDiverseSelfReportAcceptancePolicy:
    """Keep the latest locally distinct self-reported implementations."""

    mode: AssimilationMode = "bounded_diverse_self_report_acceptance"
    seed_results: tuple[WorkerOutput, ...] = ()
    reference_limit: int = 3

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer
        accepted = [
            CumulativeSelfReportAcceptancePolicy._as_self_report_reference(
                result
            )
            for completed_layer in layer_history
            for result in completed_layer
            if result.telemetry.self_reported_success
        ]
        candidates = [*self.seed_results, *accepted]
        selected: list[WorkerOutput] = []
        seen: set[str] = set()
        for candidate in reversed(candidates):
            fingerprint = _workspace_implementation_fingerprint(
                candidate.workspace
            )
            identity = (
                f"implementation:{fingerprint}"
                if fingerprint is not None
                else f"artifact:{candidate.artifact.artifact_id}"
            )
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(candidate)
            if len(selected) == self.reference_limit:
                break
        return tuple(reversed(selected))

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


def _as_blinded_proxy_reference(
    result: WorkerOutput,
    *,
    artifact_suffix: str,
    test_collection_hash: str,
    acceptance_text: str,
) -> WorkerOutput:
    """Hide external evaluation while preserving the agent's experience text."""
    sanitized_lines = []
    for line in result.artifact.summary.splitlines():
        if line.startswith("Local verifier Core:"):
            sanitized_lines.append(acceptance_text)
        else:
            sanitized_lines.append(line)
    summary = "\n".join(sanitized_lines)
    proxy_verification = VerificationResult(
        core_passed=max(result.verification.core_total, 1),
        core_total=max(result.verification.core_total, 1),
        pytest_exit_code=0,
        infrastructure_failure=False,
        test_collection_hash=test_collection_hash,
        pytest_collected=result.telemetry.local_validation_commands,
        all_passed=1,
        all_total=1,
    )
    artifact = ExperienceArtifact(
        artifact_id=f"{result.artifact.artifact_id}:{artifact_suffix}",
        source_worker=result.artifact.source_worker,
        source_layer=result.artifact.source_layer,
        summary=summary,
        verification=proxy_verification,
        complexity=result.artifact.complexity,
    )
    return WorkerOutput(
        worker_id=result.worker_id,
        layer=result.layer,
        workspace=result.workspace,
        summary=summary,
        verification=proxy_verification,
        artifact=artifact,
        telemetry=result.telemetry,
    )


@dataclass
class RecipientCreditPolicy:
    """MoA-compatible bundle credit based on next-layer recipient outcomes.

    Standard MoA broadcasts the same prior-layer context to every worker. To
    preserve that topology, credit is assigned to the broadcast bundle rather
    than routing different artifacts to individual workers.
    """

    mode: AssimilationMode = "recipient_credit"
    min_uplift: float = 0.0
    _bundle_credit: dict[tuple[str, ...], float] = field(default_factory=dict)
    _last_uplift: float | None = None

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        if not previous_layer:
            return ()
        candidates = SourceSuccessPolicy().select(previous_layer, layer_history)
        if self._last_uplift is None or self._last_uplift > self.min_uplift:
            return candidates
        return ()

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        if not references or not previous_layer or not next_layer:
            return
        previous_by_worker = {item.worker_id: item for item in previous_layer}
        paired_uplifts = [
            item.verification.score - previous_by_worker[item.worker_id].verification.score
            for item in next_layer
            if item.worker_id in previous_by_worker
        ]
        if not paired_uplifts:
            return
        self._last_uplift = sum(paired_uplifts) / len(paired_uplifts)
        self._bundle_credit[self._key(references)] = self._last_uplift

    @staticmethod
    def _key(results: Sequence[WorkerOutput]) -> tuple[str, ...]:
        return tuple(sorted(item.artifact.artifact_id for item in results))


@dataclass
class RecursiveSynthesisPolicy:
    """Marker policy for recursive MoA manager synthesis."""

    mode: AssimilationMode = "recursive_synthesis"

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer, layer_history
        raise RuntimeError(
            "recursive_synthesis references must be produced by the MoA manager"
        )

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


@dataclass
class RecursiveSelfReportSynthesisPolicy:
    """Marker policy for recursive manager synthesis from blinded self reports."""

    mode: AssimilationMode = "recursive_self_report_synthesis"

    def select(
        self,
        previous_layer: Sequence[WorkerOutput],
        layer_history: Sequence[Sequence[WorkerOutput]],
    ) -> tuple[WorkerOutput, ...]:
        del previous_layer, layer_history
        raise RuntimeError(
            "recursive_self_report_synthesis references must be produced "
            "by the MoA manager"
        )

    def observe(
        self,
        references: Sequence[WorkerOutput],
        previous_layer: Sequence[WorkerOutput],
        next_layer: Sequence[WorkerOutput],
    ) -> None:
        del references, previous_layer, next_layer


def make_assimilation_policy(
    mode: AssimilationMode,
    seed_results: Sequence[WorkerOutput] = (),
) -> AssimilationPolicy:
    if mode == "no_transfer":
        return NoTransferPolicy()
    if mode == "source_success":
        return SourceSuccessPolicy()
    if mode == "cumulative_success":
        return CumulativeSuccessPolicy(seed_results=tuple(seed_results))
    if mode == "cumulative_local_acceptance":
        return CumulativeLocalAcceptancePolicy(
            seed_results=tuple(seed_results)
        )
    if mode == "cumulative_self_report_acceptance":
        return CumulativeSelfReportAcceptancePolicy(
            seed_results=tuple(seed_results)
        )
    if mode == "bounded_recent_self_report_acceptance":
        return BoundedRecentSelfReportAcceptancePolicy(
            seed_results=tuple(seed_results)
        )
    if mode == "bounded_diverse_self_report_acceptance":
        return BoundedDiverseSelfReportAcceptancePolicy(
            seed_results=tuple(seed_results)
        )
    if mode == "recipient_credit":
        return RecipientCreditPolicy()
    if mode == "recursive_synthesis":
        return RecursiveSynthesisPolicy()
    if mode == "recursive_self_report_synthesis":
        return RecursiveSelfReportSynthesisPolicy()
    raise ValueError(f"Unknown assimilation mode: {mode}")


class MoAWorkerAgent(RoutedAgent):
    def __init__(
        self,
        worker_id: str,
        workspace: Path,
        backend: WorkerBackend,
    ) -> None:
        super().__init__(description=f"MoA worker {worker_id}")
        self._worker_id = worker_id
        self._workspace = workspace
        self._backend = backend

    @message_handler
    async def handle_task(
        self, message: WorkerTask, ctx: MessageContext
    ) -> WorkerTaskResult:
        del ctx
        request = WorkerRequest(
            task_id=message.task_id,
            task=message.task,
            worker_id=self._worker_id,
            layer=message.layer,
            workspace=str(self._workspace),
            previous_results=message.previous_results,
        )
        return WorkerTaskResult(output=await self._backend.run(request))


class MoAOrchestratorAgent(RoutedAgent):
    def __init__(
        self,
        worker_ids: Sequence[AgentId],
        num_layers: int,
        policy: AssimilationPolicy,
        aggregator: AggregatorBackend,
        recursive_synthesizer: RecursiveSynthesisBackend | None = None,
        initial_shared_experience: WorkerOutput | None = None,
        initial_references: Sequence[WorkerOutput] = (),
    ) -> None:
        super().__init__(description="Standard layered Mixture-of-Agents orchestrator")
        if num_layers < 1:
            raise ValueError("num_layers must be at least 1")
        if not worker_ids:
            raise ValueError("At least one worker is required")
        self._worker_ids = tuple(worker_ids)
        self._num_layers = num_layers
        self._policy = policy
        self._aggregator = aggregator
        self._recursive_synthesizer = recursive_synthesizer
        self._initial_shared_experience = initial_shared_experience
        self._initial_references = tuple(initial_references)
        recursive_modes = (
            "recursive_synthesis",
            "recursive_self_report_synthesis",
        )
        if (
            self._policy.mode in recursive_modes
            and self._recursive_synthesizer is None
        ):
            raise ValueError(
                f"{self._policy.mode} requires a recursive synthesizer"
            )
        if (
            initial_shared_experience is not None
            and self._policy.mode not in recursive_modes
        ):
            raise ValueError(
                "initial_shared_experience is only valid for recursive modes"
            )
        if (
            self._initial_references
            and self._policy.mode
            not in (
                "cumulative_success",
                "cumulative_local_acceptance",
                "cumulative_self_report_acceptance",
                "bounded_recent_self_report_acceptance",
                "bounded_diverse_self_report_acceptance",
            )
        ):
            raise ValueError(
                "initial_references require a cumulative assimilation mode"
            )

    @message_handler
    async def handle_task(self, message: UserTask, ctx: MessageContext) -> FinalResult:
        del ctx
        history: list[tuple[WorkerOutput, ...]] = []
        shared_experience = self._initial_shared_experience
        references: tuple[WorkerOutput, ...]
        if shared_experience is not None:
            references = (shared_experience,)
        else:
            references = self._initial_references

        for layer in range(1, self._num_layers + 1):
            previous_layer = history[-1] if history else ()
            worker_results = await asyncio.gather(
                *[
                    self.send_message(
                        WorkerTask(
                            task_id=message.task_id,
                            task=message.task,
                            layer=layer,
                            previous_results=references,
                        ),
                        recipient=worker_id,
                    )
                    for worker_id in self._worker_ids
                ]
            )
            layer_outputs = tuple(result.output for result in worker_results)
            history.append(layer_outputs)
            self._policy.observe(references, previous_layer, layer_outputs)
            if (
                self._policy.mode
                in (
                    "recursive_synthesis",
                    "recursive_self_report_synthesis",
                )
                and layer < self._num_layers
            ):
                if self._policy.mode == "recursive_synthesis":
                    synthesis_sources = tuple(
                        output
                        for output in layer_outputs
                        if output.verification.core_verified
                    )
                else:
                    synthesis_sources = tuple(
                        CumulativeSelfReportAcceptancePolicy
                        ._as_self_report_reference(output)
                        for output in layer_outputs
                        if output.telemetry.self_reported_success
                    )
                if synthesis_sources:
                    assert self._recursive_synthesizer is not None
                    shared_experience = (
                        await self._recursive_synthesizer.synthesize_layer(
                            task_id=message.task_id,
                            task=message.task,
                            layer=layer,
                            previous_shared=shared_experience,
                            verified_results=synthesis_sources,
                        )
                    )
                references = (
                    (shared_experience,) if shared_experience is not None else ()
                )
            elif self._policy.mode not in (
                "recursive_synthesis",
                "recursive_self_report_synthesis",
            ):
                references = self._policy.select(layer_outputs, history)

        answer = await self._aggregator.synthesize(
            message.task_id, message.task, history[-1]
        )
        return FinalResult(
            task_id=message.task_id,
            answer=answer,
            layers=tuple(history),
        )


@dataclass(frozen=True)
class MoARunConfig:
    run_root: Path
    worker_count: int = 3
    num_layers: int = 2
    assimilation_mode: AssimilationMode = "source_success"


async def run_moa(
    task: str,
    worker_backend_factory: Callable[[str, Path], WorkerBackend],
    aggregator: AggregatorBackend,
    config: MoARunConfig,
    task_id: str | None = None,
    recursive_synthesizer: RecursiveSynthesisBackend | None = None,
    initial_shared_experience: WorkerOutput | None = None,
    initial_references: Sequence[WorkerOutput] = (),
) -> FinalResult:
    task_id = task_id or uuid.uuid4().hex
    run_dir = config.run_root / task_id
    run_dir.mkdir(parents=True, exist_ok=False)
    runtime = SingleThreadedAgentRuntime()
    worker_agent_ids: list[AgentId] = []

    for index in range(config.worker_count):
        worker_name = f"worker_{index + 1}"
        workspace = run_dir / "workers" / worker_name
        workspace.mkdir(parents=True)
        backend = worker_backend_factory(worker_name, workspace)
        await MoAWorkerAgent.register(
            runtime,
            worker_name,
            lambda worker_name=worker_name, workspace=workspace, backend=backend: (
                MoAWorkerAgent(worker_name, workspace, backend)
            ),
        )
        worker_agent_ids.append(AgentId(worker_name, "default"))

    policy = make_assimilation_policy(
        config.assimilation_mode,
        seed_results=initial_references,
    )
    await MoAOrchestratorAgent.register(
        runtime,
        "orchestrator",
        lambda: MoAOrchestratorAgent(
            worker_ids=worker_agent_ids,
            num_layers=config.num_layers,
            policy=policy,
            aggregator=aggregator,
            recursive_synthesizer=recursive_synthesizer,
            initial_shared_experience=initial_shared_experience,
            initial_references=initial_references,
        ),
    )

    runtime.start()
    try:
        result = await runtime.send_message(
            UserTask(task_id=task_id, task=task),
            recipient=AgentId("orchestrator", "default"),
        )
        await runtime.stop_when_idle()
    finally:
        await runtime.close()

    manifest = {
        "task_id": result.task_id,
        "task": task,
        "worker_count": config.worker_count,
        "num_layers": config.num_layers,
        "assimilation_mode": config.assimilation_mode,
        "initial_shared_experience": (
            asdict(initial_shared_experience)
            if initial_shared_experience is not None
            else None
        ),
        "initial_references": [
            asdict(reference) for reference in initial_references
        ],
        "answer": result.answer,
        "layers": [
            [asdict(output) for output in layer]
            for layer in result.layers
        ],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return result


class ScbenchSnapshotEvaluator:
    def __init__(
        self,
        repo_root: Path,
        problem_name: str,
        checkpoint: int,
        problem_catalog: Path,
        image: str | None = None,
    ) -> None:
        self._repo_root = repo_root.resolve()
        self._problem_name = problem_name
        self._checkpoint = checkpoint
        self._problem_catalog = problem_catalog.resolve()
        self._image = image or self._load_image()

    async def evaluate(
        self, snapshot: Path, output_dir: Path
    ) -> VerificationResult:
        return await asyncio.to_thread(self.evaluate_sync, snapshot, output_dir)

    def evaluate_sync(
        self, snapshot: Path, output_dir: Path
    ) -> VerificationResult:
        snapshot = snapshot.resolve()
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        environment_path = output_dir / "antmill_eval_environment.yaml"
        requirements_path = (
            self._problem_catalog
            / self._problem_name
            / "requirements.txt"
        ).resolve()
        if not requirements_path.is_file():
            raise RuntimeError(
                f"Missing frozen problem requirements: {requirements_path}"
            )
        cli_bootstrap = (
            self._repo_root
            / "benchmarks"
            / "scbench"
            / "scbench_miniswe_cli.py"
        ).resolve()
        wheelhouse = self._local_wheelhouse()
        environment_path.write_text(
            self._environment_config_text(
                use_local_wheelhouse=wheelhouse is not None
            ),
            encoding="utf-8",
        )
        command = [
            "docker",
            "run",
            "--rm",
            "--env",
            "SCBENCH_PROBLEMS_PATH=/problems",
            *(
                [
                    "--env",
                    "UV_OFFLINE=1",
                    "--env",
                    "UV_FIND_LINKS=/antmill/wheelhouse",
                ]
                if wheelhouse is not None
                else []
            ),
            "--volume",
            f"{self._problem_catalog}:/problems:ro",
            "--volume",
            f"{snapshot}:/snapshot:ro",
            "--volume",
            f"{output_dir}:/outputs",
            "--volume",
            f"{cli_bootstrap}:/antmill/scbench_miniswe_cli.py:ro",
            "--volume",
            f"{environment_path}:/antmill/local_eval.yaml:ro",
            "--volume",
            f"{requirements_path}:/antmill/requirements.txt:ro",
            *(
                [
                    "--volume",
                    f"{wheelhouse}:/antmill/wheelhouse:ro",
                ]
                if wheelhouse is not None
                else []
            ),
            self._image,
            "python",
            "/antmill/scbench_miniswe_cli.py",
            "eval-snapshot",
            "/snapshot",
            "--save-dir",
            "/outputs",
            "--problem-name",
            self._problem_name,
            "--checkpoint",
            str(self._checkpoint),
            "--env-config",
            "/antmill/local_eval.yaml",
            "--json",
        ]
        completed = subprocess.run(
            command,
            cwd=self._repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        evaluation_path = output_dir / "evaluation.json"
        if completed.returncode != 0 or not evaluation_path.exists():
            raise RuntimeError(
                "SCBench evaluation failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        pass_counts = dict(evaluation["pass_counts"])
        total_counts = dict(evaluation["total_counts"])
        return VerificationResult(
            core_passed=int(pass_counts["Core"]),
            core_total=int(total_counts["Core"]),
            pytest_exit_code=int(evaluation["pytest_exit_code"]),
            infrastructure_failure=bool(evaluation["infrastructure_failure"]),
            test_collection_hash=str(
                evaluation.get("test_collection_hash", "")
            ),
            pytest_collected=int(evaluation.get("pytest_collected", 0)),
            all_passed=sum(int(value) for value in pass_counts.values()),
            all_total=sum(int(value) for value in total_counts.values()),
        )

    @staticmethod
    def _environment_config_text(
        *,
        use_local_wheelhouse: bool = False,
    ) -> str:
        package_source = (
            " --no-index --find-links /antmill/wheelhouse"
            if use_local_wheelhouse
            else ""
        )
        return (
            "type: local\n"
            "name: python-reproducible-evaluation\n"
            "environment:\n"
            "  include_os_env: true\n"
            "setup:\n"
            "  commands:\n"
            "    - cp /antmill/requirements.txt requirements.txt\n"
            f"    - uv pip install{package_source} --python "
            "/opt/scbench/.venv/bin/python -r requirements.txt\n"
            "  eval_commands:\n"
            '    - sh -lc "test -f pyproject.toml || '
            'uv init --name scbench-submission"\n'
            f"    - uv add{package_source} -r requirements.txt\n"
            "commands:\n"
            '  entry_file: "{entry_file}.py"\n'
            '  command: "uv run"\n'
            '  agent_command: "python"\n'
        )

    def _local_wheelhouse(self) -> Path | None:
        return scbench_local_wheelhouse(
            self._repo_root,
            self._problem_name,
        )

    def _load_image(self) -> str:
        versions_path = self._repo_root / "benchmarks" / "scbench" / "versions.json"
        versions = json.loads(versions_path.read_text(encoding="utf-8"))
        return str(versions["image"])


class FixtureWorkerBackend:
    """Infrastructure-only backend for exercising MoA plus SCBench evaluation."""

    def __init__(
        self,
        worker_id: str,
        workspace: Path,
        fixture_submission: Path,
        evaluator: ScbenchSnapshotEvaluator,
        delay_seconds: float = 0.0,
    ) -> None:
        self._worker_id = worker_id
        self._workspace = workspace
        self._fixture_submission = fixture_submission
        self._evaluator = evaluator
        self._delay_seconds = delay_seconds

    async def run(self, request: WorkerRequest) -> WorkerOutput:
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        snapshot = self._workspace / f"layer_{request.layer}" / "snapshot"
        if snapshot.exists():
            shutil.rmtree(snapshot)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self._fixture_submission, snapshot)
        evaluation_dir = snapshot.parent / "evaluation"
        verification = await self._evaluator.evaluate(snapshot, evaluation_dir)
        summary = (
            f"{request.worker_id} layer {request.layer}: "
            f"Core {verification.core_passed}/{verification.core_total}; "
            f"received {len(request.previous_results)} prior-layer results."
        )
        artifact = ExperienceArtifact(
            artifact_id=f"{request.task_id}:{request.worker_id}:{request.layer}",
            source_worker=request.worker_id,
            source_layer=request.layer,
            summary=summary,
            verification=verification,
            complexity=len(request.previous_results),
        )
        return WorkerOutput(
            worker_id=request.worker_id,
            layer=request.layer,
            workspace=str(snapshot),
            summary=summary,
            verification=verification,
            artifact=artifact,
        )


class BestVerifiedAggregator:
    async def synthesize(
        self, task_id: str, task: str, results: Sequence[WorkerOutput]
    ) -> str:
        del task_id, task
        best = max(
            results,
            key=lambda result: (
                result.verification.score,
                -result.artifact.complexity,
                result.worker_id,
            ),
        )
        return best.workspace


class RecordingBackend:
    """Deterministic protocol-test backend; it does not stand in for experiments."""

    def __init__(
        self,
        worker_id: str,
        workspace: Path,
        events: list[dict[str, object]],
        delay: float = 0.01,
    ) -> None:
        self._worker_id = worker_id
        self._workspace = workspace
        self._events = events
        self._delay = delay

    async def run(self, request: WorkerRequest) -> WorkerOutput:
        started = time.perf_counter()
        self._events.append(
            {
                "event": "start",
                "worker": request.worker_id,
                "layer": request.layer,
                "time": started,
                "previous": tuple(item.artifact.artifact_id for item in request.previous_results),
            }
        )
        await asyncio.sleep(self._delay)
        core_passed = min(request.layer, 2)
        verification = VerificationResult(
            core_passed=core_passed,
            core_total=2,
            pytest_exit_code=0 if core_passed == 2 else 1,
            infrastructure_failure=False,
        )
        artifact = ExperienceArtifact(
            artifact_id=f"{request.task_id}:{request.worker_id}:{request.layer}",
            source_worker=request.worker_id,
            source_layer=request.layer,
            summary=f"{request.worker_id} layer {request.layer}",
            verification=verification,
            complexity=len(request.previous_results),
        )
        output = WorkerOutput(
            worker_id=request.worker_id,
            layer=request.layer,
            workspace=str(self._workspace),
            summary=artifact.summary,
            verification=verification,
            artifact=artifact,
            telemetry=WorkerTelemetry(
                local_validation_passed=True,
                local_validation_commands=3,
                self_reported_success=True,
            ),
        )
        self._events.append(
            {
                "event": "end",
                "worker": request.worker_id,
                "layer": request.layer,
                "time": time.perf_counter(),
            }
        )
        return output


class SummaryAggregator:
    def __init__(self) -> None:
        self.received: tuple[WorkerOutput, ...] = ()

    async def synthesize(
        self, task_id: str, task: str, results: Sequence[WorkerOutput]
    ) -> str:
        del task_id, task
        self.received = tuple(results)
        return "\n".join(result.summary for result in results)


def temporary_run_root(prefix: str = "antmill-moa-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
