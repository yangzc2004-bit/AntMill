from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the frozen multimodel expansion rule."
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "runs_scbench_moa_multimodel_contrast/contrast_report.json"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    report_path = (repo_root / args.report).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report["rows"]
    decisions: list[dict[str, object]] = []

    for model_spec in report["contrast_config"]["models"]:
        model = str(model_spec["model"])
        selected = [
            row
            for row in rows
            if row["model"] == model and int(row["replicate"]) == 1
        ]
        by_mode_layer = {
            (str(row["mode"]), int(row["layer"])): row for row in selected
        }
        required = {
            (mode, layer)
            for mode in ("no_transfer", "source_success")
            for layer in (1, 2, 3)
        }
        if not required.issubset(by_mode_layer):
            decisions.append(
                {
                    "model": model,
                    "complete": False,
                    "expand_to_three_repeats": False,
                }
            )
            continue

        source_ratio = (
            float(
                by_mode_layer[
                    ("source_success", 3)
                ]["total_input_tokens"]
            )
            / float(
                by_mode_layer[
                    ("source_success", 1)
                ]["total_input_tokens"]
            )
        )
        baseline_ratio = (
            float(
                by_mode_layer[
                    ("no_transfer", 3)
                ]["total_input_tokens"]
            )
            / float(
                by_mode_layer[
                    ("no_transfer", 1)
                ]["total_input_tokens"]
            )
        )
        source_l2 = float(
            by_mode_layer[("source_success", 2)]["mean_core_score"]
        )
        source_l3 = float(
            by_mode_layer[("source_success", 3)]["mean_core_score"]
        )
        baseline_l3 = float(
            by_mode_layer[("no_transfer", 3)]["mean_core_score"]
        )
        input_growth = source_ratio >= 1.4 * baseline_ratio
        performance_direction = (
            source_l3 < source_l2 or source_l3 < baseline_l3
        )
        decisions.append(
            {
                "model": model,
                "complete": True,
                "source_input_ratio_l1_to_l3": source_ratio,
                "baseline_input_ratio_l1_to_l3": baseline_ratio,
                "source_layer_2_score": source_l2,
                "source_layer_3_score": source_l3,
                "baseline_layer_3_score": baseline_l3,
                "input_growth_same_direction": input_growth,
                "performance_same_direction": performance_direction,
                "expand_to_three_repeats": (
                    input_growth and performance_direction
                ),
            }
        )

    output = {
        "source_report": str(report_path),
        "decisions": decisions,
    }
    output_path = report_path.parent / "initial_stage_decision.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
