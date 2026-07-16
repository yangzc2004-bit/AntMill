from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from sec.scbench_moa import (
    BoundedDiverseSelfReportAcceptancePolicy,
    ExperienceArtifact,
    MoARunConfig,
    RecordingBackend,
    SummaryAggregator,
    VerificationResult,
    WorkerOutput,
    WorkerTelemetry,
    run_moa,
)


class RecordingRecursiveSynthesizer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def synthesize_layer(
        self,
        task_id: str,
        task: str,
        layer: int,
        previous_shared: WorkerOutput | None,
        verified_results: tuple[WorkerOutput, ...],
    ) -> WorkerOutput:
        del task
        self.calls.append(
            {
                "layer": layer,
                "previous": (
                    previous_shared.artifact.artifact_id
                    if previous_shared is not None
                    else None
                ),
                "sources": tuple(
                    item.artifact.artifact_id for item in verified_results
                ),
            }
        )
        verification = VerificationResult(
            core_passed=1,
            core_total=1,
            pytest_exit_code=0,
            infrastructure_failure=False,
        )
        artifact = ExperienceArtifact(
            artifact_id=f"{task_id}:manager:{layer}",
            source_worker="manager",
            source_layer=layer,
            summary=f"shared layer {layer}",
            verification=verification,
        )
        return WorkerOutput(
            worker_id="manager",
            layer=layer,
            workspace="manager",
            summary=artifact.summary,
            verification=verification,
            artifact=artifact,
        )


def run_protocol_test(mode: str) -> None:
    events: list[dict[str, object]] = []
    aggregator = SummaryAggregator()
    recursive_synthesizer = (
        RecordingRecursiveSynthesizer()
        if mode
        in (
            "recursive_synthesis",
            "recursive_self_report_synthesis",
        )
        else None
    )
    with tempfile.TemporaryDirectory(prefix=f"antmill-moa-{mode}-") as root:
        result = asyncio.run(
            run_moa(
                task="Solve the same coding task independently.",
                worker_backend_factory=lambda worker_id, workspace: RecordingBackend(
                    worker_id, workspace, events
                ),
                aggregator=aggregator,
                config=MoARunConfig(
                    run_root=Path(root),
                    worker_count=3,
                    num_layers=4,
                    assimilation_mode=mode,  # type: ignore[arg-type]
                ),
                task_id=f"protocol-{mode}",
                recursive_synthesizer=recursive_synthesizer,
            )
        )

        assert len(result.layers) == 4
        assert all(len(layer) == 3 for layer in result.layers)
        assert len(aggregator.received) == 3
        assert {item.layer for item in aggregator.received} == {4}

        layer_1_ends = [
            float(event["time"])
            for event in events
            if event["event"] == "end" and event["layer"] == 1
        ]
        layer_2_starts = [
            float(event["time"])
            for event in events
            if event["event"] == "start" and event["layer"] == 2
        ]
        assert max(layer_1_ends) <= min(layer_2_starts)

        first_layer_starts = [
            event
            for event in events
            if event["event"] == "start" and event["layer"] == 1
        ]
        assert all(event["previous"] == () for event in first_layer_starts)

        second_layer_starts = [
            event
            for event in events
            if event["event"] == "start" and event["layer"] == 2
        ]
        expected_previous_count = (
            1 if mode == "recursive_self_report_synthesis" else 0
        )
        assert all(
            len(event["previous"]) == expected_previous_count
            for event in second_layer_starts
        )
        assert len({event["previous"] for event in second_layer_starts}) == 1

        for layer in (3, 4):
            starts = [
                event
                for event in events
                if event["event"] == "start" and event["layer"] == layer
            ]
            expected = 0 if mode == "no_transfer" else 3
            if mode == "recipient_credit" and layer == 4:
                expected = 0
            if mode == "cumulative_success" and layer == 4:
                expected = 6
            if mode in (
                "recursive_synthesis",
                "recursive_self_report_synthesis",
            ):
                expected = 1
            assert all(len(event["previous"]) == expected for event in starts)
            assert len({event["previous"] for event in starts}) == 1
            if mode == "cumulative_success":
                source_layers = {
                    int(str(artifact_id).rsplit(":", 1)[1])
                    for artifact_id in starts[0]["previous"]
                }
                expected_layers = {2} if layer == 3 else {2, 3}
                assert source_layers == expected_layers
        if recursive_synthesizer is not None:
            expected_layers = (
                [1, 2, 3]
                if mode == "recursive_self_report_synthesis"
                else [2, 3]
            )
            assert [
                call["layer"] for call in recursive_synthesizer.calls
            ] == expected_layers
            assert recursive_synthesizer.calls[0]["previous"] is None
            if mode == "recursive_self_report_synthesis":
                assert all(
                    str(source).endswith(":self_report_acceptance")
                    for call in recursive_synthesizer.calls
                    for source in call["sources"]
                )
                assert (
                    recursive_synthesizer.calls[1]["previous"]
                    == "protocol-recursive_self_report_synthesis:manager:1"
                )
            else:
                assert (
                    recursive_synthesizer.calls[1]["previous"]
                    == "protocol-recursive_synthesis:manager:2"
                )


def run_bootstrapped_recursive_test() -> None:
    events: list[dict[str, object]] = []
    synthesizer = RecordingRecursiveSynthesizer()
    verification = VerificationResult(
        core_passed=1,
        core_total=1,
        pytest_exit_code=0,
        infrastructure_failure=False,
    )
    seed_artifact = ExperienceArtifact(
        artifact_id="frozen-bootstrap-manager",
        source_worker="manager",
        source_layer=0,
        summary="frozen verified bootstrap",
        verification=verification,
    )
    seed = WorkerOutput(
        worker_id="manager",
        layer=0,
        workspace="bootstrap",
        summary=seed_artifact.summary,
        verification=verification,
        artifact=seed_artifact,
    )
    with tempfile.TemporaryDirectory(
        prefix="antmill-moa-bootstrap-"
    ) as root:
        asyncio.run(
            run_moa(
                task="Solve the same coding task independently.",
                worker_backend_factory=lambda worker_id, workspace: (
                    RecordingBackend(worker_id, workspace, events)
                ),
                aggregator=SummaryAggregator(),
                config=MoARunConfig(
                    run_root=Path(root),
                    worker_count=3,
                    num_layers=3,
                    assimilation_mode="recursive_synthesis",
                ),
                task_id="protocol-recursive-bootstrap",
                recursive_synthesizer=synthesizer,
                initial_shared_experience=seed,
            )
        )
    first_layer = [
        event
        for event in events
        if event["event"] == "start" and event["layer"] == 1
    ]
    assert all(
        event["previous"] == ("frozen-bootstrap-manager",)
        for event in first_layer
    )
    assert synthesizer.calls[0]["previous"] == "frozen-bootstrap-manager"


def run_bootstrapped_cumulative_test() -> None:
    events: list[dict[str, object]] = []
    verification = VerificationResult(
        core_passed=1,
        core_total=1,
        pytest_exit_code=0,
        infrastructure_failure=False,
    )
    seeds = []
    for index in range(2):
        artifact = ExperienceArtifact(
            artifact_id=f"frozen-cumulative-seed-{index}",
            source_worker=f"seed_{index}",
            source_layer=0,
            summary=f"verified seed {index}",
            verification=verification,
        )
        seeds.append(
            WorkerOutput(
                worker_id=f"seed_{index}",
                layer=0,
                workspace="bootstrap",
                summary=artifact.summary,
                verification=verification,
                artifact=artifact,
            )
        )
    with tempfile.TemporaryDirectory(
        prefix="antmill-moa-cumulative-bootstrap-"
    ) as root:
        asyncio.run(
            run_moa(
                task="Solve the same coding task independently.",
                worker_backend_factory=lambda worker_id, workspace: (
                    RecordingBackend(worker_id, workspace, events)
                ),
                aggregator=SummaryAggregator(),
                config=MoARunConfig(
                    run_root=Path(root),
                    worker_count=3,
                    num_layers=3,
                    assimilation_mode="cumulative_success",
                ),
                task_id="protocol-cumulative-bootstrap",
                initial_references=tuple(seeds),
            )
        )
    starts_by_layer = {
        layer: [
            event
            for event in events
            if event["event"] == "start" and event["layer"] == layer
        ]
        for layer in (1, 2, 3)
    }
    assert all(
        len(event["previous"]) == 2 for event in starts_by_layer[1]
    )
    assert all(
        len(event["previous"]) == 2 for event in starts_by_layer[2]
    )
    assert all(
        len(event["previous"]) == 5 for event in starts_by_layer[3]
    )


def run_local_acceptance_test() -> None:
    events: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(
        prefix="antmill-moa-local-acceptance-"
    ) as root:
        asyncio.run(
            run_moa(
                task="Solve the same coding task independently.",
                worker_backend_factory=lambda worker_id, workspace: (
                    RecordingBackend(worker_id, workspace, events)
                ),
                aggregator=SummaryAggregator(),
                config=MoARunConfig(
                    run_root=Path(root),
                    worker_count=3,
                    num_layers=3,
                    assimilation_mode="cumulative_local_acceptance",
                ),
                task_id="protocol-local-acceptance",
            )
        )
    starts_by_layer = {
        layer: [
            event
            for event in events
            if event["event"] == "start" and event["layer"] == layer
        ]
        for layer in (1, 2, 3)
    }
    assert all(
        len(event["previous"]) == 0 for event in starts_by_layer[1]
    )
    assert all(
        len(event["previous"]) == 3 for event in starts_by_layer[2]
    )
    assert all(
        len(event["previous"]) == 6 for event in starts_by_layer[3]
    )
    assert all(
        str(artifact_id).endswith(":local_acceptance")
        for artifact_id in starts_by_layer[3][0]["previous"]
    )


def run_self_report_acceptance_test() -> None:
    events: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(
        prefix="antmill-moa-self-report-acceptance-"
    ) as root:
        asyncio.run(
            run_moa(
                task="Solve the same coding task independently.",
                worker_backend_factory=lambda worker_id, workspace: (
                    RecordingBackend(worker_id, workspace, events)
                ),
                aggregator=SummaryAggregator(),
                config=MoARunConfig(
                    run_root=Path(root),
                    worker_count=3,
                    num_layers=3,
                    assimilation_mode=(
                        "cumulative_self_report_acceptance"
                    ),
                ),
                task_id="protocol-self-report-acceptance",
            )
        )
    starts_by_layer = {
        layer: [
            event
            for event in events
            if event["event"] == "start" and event["layer"] == layer
        ]
        for layer in (1, 2, 3)
    }
    assert all(
        len(event["previous"]) == 0 for event in starts_by_layer[1]
    )
    assert all(
        len(event["previous"]) == 3 for event in starts_by_layer[2]
    )
    assert all(
        len(event["previous"]) == 6 for event in starts_by_layer[3]
    )
    assert all(
        str(artifact_id).endswith(":self_report_acceptance")
        for artifact_id in starts_by_layer[3][0]["previous"]
    )


def run_bounded_self_report_acceptance_test() -> None:
    events: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(
        prefix="antmill-moa-bounded-self-report-acceptance-"
    ) as root:
        asyncio.run(
            run_moa(
                task="Solve the same coding task independently.",
                worker_backend_factory=lambda worker_id, workspace: (
                    RecordingBackend(worker_id, workspace, events)
                ),
                aggregator=SummaryAggregator(),
                config=MoARunConfig(
                    run_root=Path(root),
                    worker_count=3,
                    num_layers=4,
                    assimilation_mode=(
                        "bounded_recent_self_report_acceptance"
                    ),
                ),
                task_id="protocol-bounded-self-report-acceptance",
            )
        )
    starts_by_layer = {
        layer: [
            event
            for event in events
            if event["event"] == "start" and event["layer"] == layer
        ]
        for layer in (1, 2, 3, 4)
    }
    assert all(
        len(event["previous"]) == 0 for event in starts_by_layer[1]
    )
    assert all(
        len(event["previous"]) == 3
        for layer in (2, 3, 4)
        for event in starts_by_layer[layer]
    )
    assert all(
        str(artifact_id).startswith(
            "protocol-bounded-self-report-acceptance:worker_"
        )
        for artifact_id in starts_by_layer[4][0]["previous"]
    )


def run_diversity_preserving_self_report_acceptance_test() -> None:
    verification = VerificationResult(
        core_passed=1,
        core_total=1,
        pytest_exit_code=0,
        infrastructure_failure=False,
    )
    telemetry = WorkerTelemetry(self_reported_success=True)

    def output(
        worker_id: str,
        layer: int,
        workspace: Path,
        source: str,
    ) -> WorkerOutput:
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "solution.py").write_text(source, encoding="utf-8")
        artifact = ExperienceArtifact(
            artifact_id=f"{worker_id}:{layer}",
            source_worker=worker_id,
            source_layer=layer,
            summary=f"{worker_id} layer {layer}",
            verification=verification,
        )
        return WorkerOutput(
            worker_id=worker_id,
            layer=layer,
            workspace=str(workspace),
            summary=artifact.summary,
            verification=verification,
            artifact=artifact,
            telemetry=telemetry,
        )

    with tempfile.TemporaryDirectory(
        prefix="antmill-moa-diverse-self-report-"
    ) as root_text:
        root = Path(root_text)
        seeds = tuple(
            output(f"seed_{index}", 0, root / f"seed_{index}", source)
            for index, source in enumerate(
                ("print('a')\n", "print('b')\n", "print('c')\n"),
                start=1,
            )
        )
        collapsed_layer = tuple(
            output(
                f"worker_{index}",
                1,
                root / f"worker_{index}",
                "print('a')\n",
            )
            for index in range(1, 4)
        )
        policy = BoundedDiverseSelfReportAcceptancePolicy(
            seed_results=seeds
        )
        references = policy.select(collapsed_layer, (collapsed_layer,))
        assert len(references) == 3
        assert references[-1].artifact.artifact_id.endswith(
            ":self_report_acceptance"
        )
        assert references[-1].worker_id == "worker_3"
        assert {item.worker_id for item in references} == {
            "seed_2",
            "seed_3",
            "worker_3",
        }


def main() -> None:
    for mode in (
        "no_transfer",
        "source_success",
        "cumulative_success",
        "recipient_credit",
        "recursive_synthesis",
        "recursive_self_report_synthesis",
    ):
        run_protocol_test(mode)
    run_bootstrapped_recursive_test()
    run_bootstrapped_cumulative_test()
    run_local_acceptance_test()
    run_self_report_acceptance_test()
    run_bounded_self_report_acceptance_test()
    run_diversity_preserving_self_report_acceptance_test()
    print("SCBench MoA protocol tests passed.")


if __name__ == "__main__":
    main()
