from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .epsilon_evidence import (
    EPSILON_PREREGISTRATION,
    _expected_epsilon_config,
)
from .epsilon_yoke import (
    ROUNDS,
    SEEDS,
    SOURCE_RUN_ID,
    ZETA_RUN_ID,
    extract_schedule,
    verify_schedule,
)
from .zeta_evidence import (
    ZETA_PREREGISTRATION,
    _expected_zeta_config,
    build_zeta_evidence,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _result(*, run_id: str, seed: int, offset: float, targets: list[int]) -> dict:
    heldout = []
    for t in range(ROUNDS):
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
                            "looped": offset > 0,
                            "stagnation_rate": 0.1 + offset / 100.0,
                            "revisit_max": 2 + offset,
                            "parse_failure_count": 0,
                        },
                    }
                )
            episodes.append(
                {
                    "task_id": f"heldout_{seed}_{instance}",
                    "agents": agents,
                }
            )
        heldout.append({"t": t, "episodes": episodes})
    trajectory = [
        {
            "t": t,
            "active_pool_size": target,
            "budgeted_append_budget": target if run_id == ZETA_RUN_ID else 0,
            "budgeted_append_selected": target if run_id == ZETA_RUN_ID else 0,
            "distinct_total_injected": target,
            "distinct_active_injected": target,
            "mean_injected_per_prompt": min(target, 6),
        }
        for t, target in enumerate(targets)
    ]
    retrievals = [
        {
            "t": t,
            "task_id": f"heldout_{seed}_{instance}",
            "agent_id": agent_id,
            "active_candidate_count": targets[t],
        }
        for t in range(ROUNDS)
        for instance in range(12)
        for agent_id in range(4)
    ]
    config = (
        _expected_epsilon_config(
            suite="controls",
            arm=SOURCE_RUN_ID,
            seed=seed,
        )
        if run_id == SOURCE_RUN_ID
        else _expected_zeta_config(seed=seed)
    )
    return {
        "config": config,
        "heldout_records": heldout,
        "log": [
            {
                "t": t,
                "n_routes": 48,
                "memory_size": targets[t],
                "parse_failure_rate": 0.0,
                "retrieval_entropy_norm": 0.8,
                "retrieval_top1_share": 0.2,
                "retrieval_concentration": 0.2,
            }
            for t in range(ROUNDS)
        ],
        "summary": {"llm": {"network_calls": 1, "cache_hits": 0, "errors": 0}},
        "memory_audit": {
            "pool_trajectory": trajectory,
            "retrievals": retrievals,
        },
    }


def main() -> None:
    targets = [0, 3, 2, 4, 4, 5]
    with tempfile.TemporaryDirectory(prefix="antmill-zeta-evidence-") as raw:
        root = Path(raw)
        controls = root / "controls"
        zeta = root / "zeta"
        for seed in SEEDS:
            baseline = _result(run_id=SOURCE_RUN_ID, seed=seed, offset=2.0, targets=targets)
            baseline_dir = controls / f"n4_gt_false_seed{seed}_{SOURCE_RUN_ID}"
            _write(baseline_dir / "result.json", baseline)
            _write(baseline_dir / "memory_audit.json", baseline["memory_audit"])
            _write(
                baseline_dir / "manifest.json",
                {
                    "condition": f"n4_gt_false_seed{seed}_{SOURCE_RUN_ID}",
                    "run_id": SOURCE_RUN_ID,
                    "seed": seed,
                    "reviewer_temp": baseline["config"]["reviewer_temp"],
                    "tie_rule": baseline["config"]["tie_rule"],
                    "append_dedup": baseline["config"]["append_dedup"],
                    "config": baseline["config"],
                    "preregistration": EPSILON_PREREGISTRATION,
                },
            )
            yoke = _result(run_id=ZETA_RUN_ID, seed=seed, offset=0.0, targets=targets)
            _write(zeta / f"n4_gt_false_seed{seed}_{ZETA_RUN_ID}" / "result.json", yoke)
        schedule_path = root / "schedule.json"
        extract_schedule(controls_dir=controls, out_path=schedule_path)
        schedule = verify_schedule(schedule_path)
        for seed in SEEDS:
            yoke_dir = zeta / f"n4_gt_false_seed{seed}_{ZETA_RUN_ID}"
            yoke = json.loads((yoke_dir / "result.json").read_text(encoding="utf-8"))
            _write(
                yoke_dir / "manifest.json",
                {
                    "condition": f"n4_gt_false_seed{seed}_{ZETA_RUN_ID}",
                    "run_id": ZETA_RUN_ID,
                    "seed": seed,
                    "config": yoke["config"],
                    "preregistration": ZETA_PREREGISTRATION,
                    "zeta_exact_supply_yoke": {
                        "schedule_sha256": schedule["schedule_sha256"],
                        "source_arm": SOURCE_RUN_ID,
                        "target_sizes": schedule["seeds"][str(seed)],
                        "target_definition": schedule["target_definition"],
                        "preregistration": schedule["verified_preregistration"],
                    },
                },
            )
        report = build_zeta_evidence(
            controls_dir=controls,
            zeta_dir=zeta,
            schedule_path=schedule_path,
            out_dir=root / "stats",
            n_boot=300,
            rng_seed=4,
        )
        assert report["decision"] == "zeta_supply_yoke_evaluable", report
        assert len(report["stats"]) == 8
        assert len(report["per_seed_effects"]) == 8 * 5
        assert all(row["passed"] for row in report["manipulation_checks"])
        assert all(
            row["retrieval_candidate_match"]
            and row["retrieval_record_count"] == 48
            for row in report["manipulation_checks"]
        )
        assert all(row["configuration_pass"] for row in report["data_quality"])
        assert all(row["manifest_pass"] for row in report["data_quality"])
        assert len(report["source_manifests"]) == 10
        assert (root / "stats" / "evidence_report.md").exists()

        bad_path = zeta / f"n4_gt_false_seed0_{ZETA_RUN_ID}" / "result.json"
        bad_result = json.loads(bad_path.read_text(encoding="utf-8"))
        bad_result["config"]["retrieval_k"] = 5
        _write(bad_path, bad_result)
        bad_manifest_path = bad_path.parent / "manifest.json"
        bad_manifest = json.loads(bad_manifest_path.read_text(encoding="utf-8"))
        bad_manifest["config"] = bad_result["config"]
        _write(bad_manifest_path, bad_manifest)
        bad_report = build_zeta_evidence(
            controls_dir=controls,
            zeta_dir=zeta,
            schedule_path=schedule_path,
            out_dir=root / "bad-stats",
            n_boot=20,
            rng_seed=4,
        )
        bad_quality = next(
            row
            for row in bad_report["data_quality"]
            if row["condition"] == ZETA_RUN_ID and row["seed"] == 0
        )
        assert not bad_quality["configuration_pass"]

        candidate_bad_result = json.loads(
            bad_path.read_text(encoding="utf-8")
        )
        candidate_bad_result["config"]["retrieval_k"] = 6
        candidate_bad_result["memory_audit"]["retrievals"][0][
            "active_candidate_count"
        ] += 1
        _write(bad_path, candidate_bad_result)
        candidate_bad_manifest = json.loads(
            bad_manifest_path.read_text(encoding="utf-8")
        )
        candidate_bad_manifest["config"] = candidate_bad_result["config"]
        _write(bad_manifest_path, candidate_bad_manifest)
        candidate_bad_report = build_zeta_evidence(
            controls_dir=controls,
            zeta_dir=zeta,
            schedule_path=schedule_path,
            out_dir=root / "candidate-bad-stats",
            n_boot=20,
            rng_seed=4,
        )
        assert (
            candidate_bad_report["decision"]
            == "zeta_supply_yoke_not_evaluable"
        )
        candidate_bad_check = next(
            row
            for row in candidate_bad_report["manipulation_checks"]
            if row["seed"] == 0 and row["t"] == 0
        )
        assert not candidate_bad_check["retrieval_candidate_match"]
    print("selftest_zeta_evidence OK")


if __name__ == "__main__":
    main()
