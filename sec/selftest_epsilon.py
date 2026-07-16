from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .epsilon_evidence import (
    CONTROL_ARMS,
    EPSILON_PREREGISTRATION,
    SENSITIVITY_ARMS,
    _expected_epsilon_config,
    build_epsilon_evidence,
)
from .config import Config
from .memory import InsightMemory


def _result(*, arm: str, seed: int, offset: float) -> dict:
    records = []
    for t in range(6):
        episodes = []
        for instance in range(12):
            agents = []
            for agent_id in range(4):
                steps = 20.0 + offset + seed + agent_id + instance / 100.0
                agents.append(
                    {
                        "agent_id": agent_id,
                        "route": {
                            "success": True,
                            "steps": steps,
                            "shortest_path_length": 10,
                            "cost_ratio": steps / 10.0,
                            "failure_penalized_steps": steps,
                            "excess_steps": steps - 10.0,
                            "looped": offset >= 3.0,
                            "stagnation_rate": 0.1 + offset / 100.0,
                            "revisit_max": 2 + offset,
                        },
                    }
                )
            episodes.append(
                {
                    "task_id": f"heldout_{seed}_{instance}",
                    "agents": agents,
                }
            )
        records.append({"t": t, "episodes": episodes})
    return {
        "heldout_records": records,
        "log": [
            {
                "t": t,
                "memory_size": int((t + 1) * (2 + offset)),
                "n_routes": 48,
                "parse_failure_rate": 0.0,
                "retrieval_entropy_norm": 0.8,
                "retrieval_top1_share": 0.2,
                "retrieval_concentration": 0.1,
            }
            for t in range(6)
        ],
        "summary": {"elapsed_sec": 1.0, "llm": {"network_calls": 5, "cache_hits": 0, "errors": 0}},
        "memory_audit": {
            "pool_trajectory": [
                {
                    "distinct_total_injected": 3,
                    "distinct_active_injected": 3,
                    "mean_injected_per_prompt": 2.0,
                }
            ]
        },
        "config": _expected_epsilon_config(
            suite="controls",
            arm=arm,
            seed=seed,
        ),
    }


def main() -> None:
    mmr_memory = InsightMemory(
        Config(
            retrieval_scoring="ga_mmr",
            mmr_relevance_weight=0.70,
        )
    )
    mmr_ranked = [
        ({"text": "go north then east"}, 1.00, 1.00),
        ({"text": "go north then east quickly"}, 0.95, 0.95),
        ({"text": "backtrack from a dead end"}, 0.80, 0.80),
    ]
    mmr_selected = mmr_memory._mmr_rerank(mmr_ranked, k=2)
    assert [row[0]["text"] for row in mmr_selected] == [
        "go north then east",
        "backtrack from a dead end",
    ]

    sensitivity_configs = {
        arm: _expected_epsilon_config(
            suite="sensitivity",
            arm=arm,
            seed=0,
        )
        for arm in SENSITIVITY_ARMS
    }
    assert sensitivity_configs["epsilon_sens_k3"]["retrieval_k"] == 3
    assert sensitivity_configs["epsilon_sens_k10"]["retrieval_k"] == 10
    assert sensitivity_configs["epsilon_sens_cap40"]["library_cap"] == 40
    assert sensitivity_configs["epsilon_sens_ops3"]["max_reviewer_ops"] == 3
    assert sensitivity_configs["epsilon_sens_ops9"]["max_reviewer_ops"] == 9
    assert sensitivity_configs["epsilon_sens_merge07"]["similarity_threshold"] == 0.70
    assert sensitivity_configs["epsilon_sens_merge09"]["similarity_threshold"] == 0.90
    assert sensitivity_configs["epsilon_sens_recency1"]["ga_recency"] == 1.0
    assert all(
        config["out_dir"] == "runs_maze_epsilon_sensitivity"
        and config["cache_dir"] == "cache_maze_epsilon_sensitivity"
        for config in sensitivity_configs.values()
    )

    offsets = {
        "epsilon_frozen_reviewer": 0.0,
        "epsilon_private_consolidated": 1.0,
        "epsilon_shared_consolidated": 3.0,
        "epsilon_shared_append_cap14": 2.0,
        "epsilon_shared_consolidated_mmr": 1.5,
    }
    with tempfile.TemporaryDirectory(prefix="antmill-epsilon-selftest-") as raw:
        root = Path(raw)
        runs = root / "runs"
        for arm in CONTROL_ARMS:
            for seed in range(5):
                path = runs / f"n4_gt_false_seed{seed}_{arm}" / "result.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                result = _result(arm=arm, seed=seed, offset=offsets[arm])
                path.write_text(json.dumps(result), encoding="utf-8")
                (path.parent / "manifest.json").write_text(
                    json.dumps(
                        {
                            "condition": f"n4_gt_false_seed{seed}_{arm}",
                            "run_id": arm,
                            "seed": seed,
                            "config": result["config"],
                            "preregistration": EPSILON_PREREGISTRATION,
                        }
                    ),
                    encoding="utf-8",
                )
        report = build_epsilon_evidence(
            suite="controls",
            runs_dir=runs,
            out_dir=root / "evidence",
            seeds=[0, 1, 2, 3, 4],
            n_boot=300,
            rng_seed=7,
        )
        assert report["final_t"] == 5
        assert len(report["stats"]) == 3 * 8
        assert len(report["per_seed_effects"]) == 3 * 8 * 5
        assert all(row["route_count_pass"] for row in report["data_quality"])
        assert all(row["terminal_round_pass"] for row in report["data_quality"])
        assert all(row["configuration_pass"] for row in report["data_quality"])
        assert all(row["manifest_pass"] for row in report["data_quality"])
        assert all(
            row["route_llm_error_count_all_rounds"] == 0
            and row["route_llm_error_count_final"] == 0
            and row["exhausted_llm_call_count"] == 0
            and row["parse_failure_count_all_rounds"] == 0
            and row["parse_failure_count_final"] == 0
            for row in report["data_quality"]
        )
        assert len(report["source_results"]) == len(CONTROL_ARMS) * 5
        assert len(report["source_manifests"]) == len(CONTROL_ARMS) * 5
        assert report["provenance"]["preregistration"]["match"]
        assert report["provenance"]["runtime_source"]["all_match"]
        loop = next(
            row
            for row in report["stats"]
            if row["contrast"] == "shared_consolidated_minus_private_consolidated" and row["metric"] == "looped"
        )
        assert loop["n_seeds"] == 5 and loop["mean_diff"] > 0.0 and loop["ci_lo"] > 0.0
        for name in (
            "hierarchical_paired_stats.csv",
            "per_seed_paired_effects.csv",
            "data_quality.csv",
            "memory_summary.csv",
            "evidence_manifest.json",
            "evidence_report.md",
        ):
            assert (root / "evidence" / name).exists(), name
        evidence = (root / "evidence" / "evidence_report.md").read_text(encoding="utf-8")
        assert "## Per-Seed Primary Effects" in evidence
        assert "## Provenance" in evidence
        assert "shared_consolidated_minus_private_consolidated" in evidence

        bad_path = runs / "n4_gt_false_seed0_epsilon_frozen_reviewer" / "result.json"
        bad_result = json.loads(bad_path.read_text(encoding="utf-8"))
        bad_result["config"]["retrieval_k"] = 5
        bad_path.write_text(json.dumps(bad_result), encoding="utf-8")
        bad_report = build_epsilon_evidence(
            suite="controls",
            runs_dir=runs,
            out_dir=root / "bad-evidence",
            seeds=[0, 1, 2, 3, 4],
            n_boot=20,
            rng_seed=7,
        )
        bad_row = next(
            row
            for row in bad_report["data_quality"]
            if row["condition"] == "epsilon_frozen_reviewer" and row["seed"] == 0
        )
        assert not bad_row["configuration_pass"]
        assert any(
            row["field"] == "retrieval_k"
            for row in bad_row["configuration_mismatches"]
        )
    print("selftest_epsilon OK")


if __name__ == "__main__":
    main()
