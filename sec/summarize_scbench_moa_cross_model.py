from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine DeepSeek, GLM, and Kimi SCBench MoA results."
    )
    parser.add_argument(
        "--deepseek-summary",
        type=Path,
        default=Path(
            "runs_scbench_moa_xjq_replication/replication_summary.json"
        ),
    )
    parser.add_argument(
        "--multimodel-report",
        type=Path,
        default=Path(
            "runs_scbench_moa_multimodel_contrast/contrast_report.json"
        ),
    )
    return parser.parse_args()


def layer_rows(
    rows: list[dict[str, object]],
    model: str,
    mode: str,
) -> dict[int, dict[str, object]]:
    return {
        int(row["layer"]): row
        for row in rows
        if row["model"] == model
        and int(row["replicate"]) == 1
        and row["mode"] == mode
    }


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    deepseek_path = (repo_root / args.deepseek_summary).resolve()
    multimodel_path = (repo_root / args.multimodel_report).resolve()
    deepseek = json.loads(deepseek_path.read_text(encoding="utf-8"))
    multimodel = json.loads(multimodel_path.read_text(encoding="utf-8"))

    deepseek_grouped = {
        (row["mode"], int(row["layer"])): row
        for row in deepseek["grouped"]
    }
    deepseek_decision = deepseek["decision"]
    models: list[dict[str, object]] = [
        {
            "model": "deepseek-v4-flash",
            "valid_replicates": 3,
            "source_input_ratio_l1_to_l3": deepseek_decision[
                "mean_source_success_input_ratio_l1_to_l3"
            ],
            "baseline_input_ratio_l1_to_l3": deepseek_decision[
                "mean_no_transfer_input_ratio_l1_to_l3"
            ],
            "source_layer_3_mean_score": deepseek_grouped[
                ("source_success", 3)
            ]["mean_core_score"],
            "baseline_layer_3_mean_score": deepseek_grouped[
                ("no_transfer", 3)
            ]["mean_core_score"],
            "source_layer_2_to_3_drop_replicates": deepseek_decision[
                "source_success_layer_2_to_3_drop_replicates"
            ],
            "complexity_amplification_observed": True,
            "performance_degradation_observed": True,
            "expansion_status": "complete",
        }
    ]

    for model in ("glm-5", "kimi-k2.6"):
        source = layer_rows(multimodel["rows"], model, "source_success")
        baseline = layer_rows(multimodel["rows"], model, "no_transfer")
        source_ratio = (
            float(source[3]["total_input_tokens"])
            / float(source[1]["total_input_tokens"])
        )
        baseline_ratio = (
            float(baseline[3]["total_input_tokens"])
            / float(baseline[1]["total_input_tokens"])
        )
        performance_drop = (
            float(source[3]["mean_core_score"])
            < float(source[2]["mean_core_score"])
        )
        models.append(
            {
                "model": model,
                "valid_replicates": 1,
                "source_input_ratio_l1_to_l3": source_ratio,
                "baseline_input_ratio_l1_to_l3": baseline_ratio,
                "source_layer_3_mean_score": source[3][
                    "mean_core_score"
                ],
                "baseline_layer_3_mean_score": baseline[3][
                    "mean_core_score"
                ],
                "source_layer_2_to_3_drop_replicates": int(
                    performance_drop
                ),
                "complexity_amplification_observed": (
                    source_ratio >= 1.4 * baseline_ratio
                ),
                "performance_degradation_observed": performance_drop,
                "expansion_status": (
                    "not_triggered_by_frozen_rule"
                    if model == "glm-5"
                    else "blocked_by_maas_parallel_tail_latency"
                ),
            }
        )

    complexity_models = sum(
        bool(item["complexity_amplification_observed"]) for item in models
    )
    degradation_models = sum(
        bool(item["performance_degradation_observed"]) for item in models
    )
    output = {
        "sources": {
            "deepseek": str(deepseek_path),
            "glm_kimi": str(multimodel_path),
        },
        "models": models,
        "cross_model": {
            "complexity_amplification_models": complexity_models,
            "performance_degradation_models": degradation_models,
            "mean_source_input_ratio_l1_to_l3": statistics.mean(
                float(item["source_input_ratio_l1_to_l3"])
                for item in models
            ),
            "claim_boundary": (
                "Experience broadcast increases coordination context across "
                "all three tested models. Performance degradation is supported "
                "for DeepSeek and one valid Kimi replicate, but is not universal "
                "and was not observed for GLM in its initial replicate."
            ),
            "kimi_reliability_note": (
                "The current MaaS gateway could not complete Kimi replicates "
                "2-3 under two-worker parallel MoA because two independent "
                "workers exceeded 900s and 1200s outer timeouts."
            ),
        },
    }
    output_path = multimodel_path.parent / "cross_model_summary.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["cross_model"], indent=2))


if __name__ == "__main__":
    main()
