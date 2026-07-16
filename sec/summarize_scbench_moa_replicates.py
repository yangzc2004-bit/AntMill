from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


MODES = ("no_transfer", "source_success", "recipient_credit")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize the frozen SCBench MoA replication report."
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "runs_scbench_moa_xjq_replication/replication_report.json"
        ),
    )
    return parser.parse_args()


def mean(values: list[float]) -> float:
    return statistics.mean(values)


def sample_sd(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    report_path = (repo_root / args.report).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report["rows"]

    grouped: list[dict[str, object]] = []
    for mode in MODES:
        for layer in (1, 2, 3):
            selected = [
                row
                for row in rows
                if row["mode"] == mode and int(row["layer"]) == layer
            ]
            scores = [float(row["mean_core_score"]) for row in selected]
            inputs = [float(row["total_input_tokens"]) for row in selected]
            experience = [
                float(row["mean_received_experience_chars"])
                for row in selected
            ]
            durations = [
                float(row["mean_duration_sec"]) for row in selected
            ]
            grouped.append(
                {
                    "mode": mode,
                    "layer": layer,
                    "replicates": len(selected),
                    "mean_core_score": mean(scores),
                    "sd_core_score": sample_sd(scores),
                    "mean_total_input_tokens": mean(inputs),
                    "sd_total_input_tokens": sample_sd(inputs),
                    "mean_received_experience_chars": mean(experience),
                    "mean_duration_sec": mean(durations),
                }
            )

    transitions: list[dict[str, object]] = []
    for replicate in (1, 2, 3):
        for mode in MODES:
            selected = {
                int(row["layer"]): row
                for row in rows
                if int(row["replicate"]) == replicate and row["mode"] == mode
            }
            transitions.append(
                {
                    "replicate": replicate,
                    "mode": mode,
                    "layer_2_to_3_core_delta": (
                        float(selected[3]["mean_core_score"])
                        - float(selected[2]["mean_core_score"])
                    ),
                    "layer_1_to_3_input_ratio": (
                        float(selected[3]["total_input_tokens"])
                        / float(selected[1]["total_input_tokens"])
                    ),
                    "layer_3_core_score": float(
                        selected[3]["mean_core_score"]
                    ),
                }
            )

    source_transitions = [
        row for row in transitions if row["mode"] == "source_success"
    ]
    baseline_transitions = [
        row for row in transitions if row["mode"] == "no_transfer"
    ]
    credit_transitions = [
        row for row in transitions if row["mode"] == "recipient_credit"
    ]
    paired_layer_3 = []
    for replicate in (1, 2, 3):
        source = next(
            row
            for row in source_transitions
            if row["replicate"] == replicate
        )
        baseline = next(
            row
            for row in baseline_transitions
            if row["replicate"] == replicate
        )
        paired_layer_3.append(
            {
                "replicate": replicate,
                "source_success_minus_no_transfer": (
                    float(source["layer_3_core_score"])
                    - float(baseline["layer_3_core_score"])
                ),
            }
        )

    source_drop_count = sum(
        float(row["layer_2_to_3_core_delta"]) < 0
        for row in source_transitions
    )
    source_input_ratios = [
        float(row["layer_1_to_3_input_ratio"])
        for row in source_transitions
    ]
    baseline_input_ratios = [
        float(row["layer_1_to_3_input_ratio"])
        for row in baseline_transitions
    ]
    credit_input_ratios = [
        float(row["layer_1_to_3_input_ratio"])
        for row in credit_transitions
    ]
    go_multi_model = (
        source_drop_count >= 2
        and mean(source_input_ratios) >= 1.5
        and mean(baseline_input_ratios) <= 1.2
    )

    summary = {
        "source_report": str(report_path),
        "valid_arms": len(report["arms"]),
        "layer_rows": len(rows),
        "worker_layer_trajectories": len(rows) * 2,
        "grouped": grouped,
        "transitions": transitions,
        "paired_layer_3": paired_layer_3,
        "decision": {
            "source_success_layer_2_to_3_drop_replicates": source_drop_count,
            "replicates": 3,
            "mean_source_success_input_ratio_l1_to_l3": mean(
                source_input_ratios
            ),
            "mean_recipient_credit_input_ratio_l1_to_l3": mean(
                credit_input_ratios
            ),
            "mean_no_transfer_input_ratio_l1_to_l3": mean(
                baseline_input_ratios
            ),
            "go_multi_model_replication": go_multi_model,
            "scope": (
                "Mechanism-screening evidence only; n=3 is not sufficient "
                "for manuscript-level statistical inference."
            ),
        },
    }

    output_dir = report_path.parent
    summary_path = output_dir / "replication_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (output_dir / "replication_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(grouped[0]))
        writer.writeheader()
        writer.writerows(grouped)
    print(json.dumps(summary["decision"], indent=2))


if __name__ == "__main__":
    main()
