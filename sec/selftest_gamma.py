from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("SEC_MOCK_KEY", "x")

from .config import Config
from .expel_ops import apply_memory_ops, parse_memory_ops
from .gamma_stats import drift_probe_report, model_smoke_report, retrieval_audit_report
from .maze_alpha import MazeMemoryAudit
from .memory import InsightMemory
from .miniwob_gamma import (
    MINIWOB_ALL_PREREG_TASKS,
    browsergym_version_manifest,
    miniwob_state_hash,
    normalize_axtree_text,
    reviewer_episode_summary,
)


def _cfg(**overrides):
    params = dict(
        api_key_env="SEC_MOCK_KEY",
        model="mock",
        base_url="http://mock.invalid/v1",
        n_solvers=2,
        memory_mode="shared",
        maze_write_mode="reviewer",
        T=1,
        batch_M=1,
        n_train=1,
        heldout_size=1,
        max_steps=4,
        retrieval_k=2,
        max_retries=1,
        cache_dir="./.sec_mock_cache/gamma",
        out_dir="./.sec_mock_runs/gamma",
    )
    params.update(overrides)
    return Config(**params)


def _config_checks() -> None:
    cfg = _cfg(
        memory_read_protocol="archive_joint_topk",
        cache_policy="off",
        disable_thinking=True,
        llm_extra_body={"x": 1},
        retrieval_scoring="ga_mmr",
        mmr_relevance_weight=0.7,
        max_reviewer_ops=3,
    )
    assert cfg.memory_read_protocol == "archive_joint_topk"
    assert cfg.cache_policy == "off"
    assert cfg.disable_thinking
    assert cfg.retrieval_scoring == "ga_mmr"
    assert cfg.max_reviewer_ops == 3
    try:
        _cfg(memory_read_protocol="bad")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid memory_read_protocol must fail")
    try:
        _cfg(budget_schedule_name="unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid budget_schedule_name must fail")
    print("gamma config checks OK")


def _mmr_and_operation_budget_checks() -> None:
    cfg = _cfg(retrieval_scoring="ga_mmr", retrieval_k=2, mmr_relevance_weight=0.10)
    memory = InsightMemory(cfg)
    duplicate_a = {"id": "a", "kind": "do", "text": "repeat the same route"}
    duplicate_b = {"id": "b", "kind": "do", "text": "repeat the same route"}
    diverse = {"id": "c", "kind": "avoid", "text": "inspect an unvisited branch before backtracking"}
    memory._ga_rank_entries = lambda _pool, _query, t: [  # type: ignore[method-assign]
        (duplicate_a, 1.0, 1.0),
        (duplicate_b, 0.99, 0.99),
        (diverse, 0.80, 0.80),
    ]
    selected = memory._rank([duplicate_a, duplicate_b, diverse], "route", k=2, t=0)
    assert [item["id"] for item in selected] == ["a", "c"], selected
    parsed = parse_memory_ops(
        '[{"op":"ADD","target_id":null,"kind":"do","text":"one"},'
        '{"op":"ADD","target_id":null,"kind":"do","text":"two"},'
        '{"op":"ADD","target_id":null,"kind":"do","text":"three"}]',
        max_ops=2,
    )
    assert len(parsed) == 2, parsed
    print("gamma MMR and operation-budget checks OK")


def _archive_source_checks() -> None:
    cfg = _cfg()
    pool = [
        {"kind": "do", "text": "prefer unvisited open directions", "votes": 2},
        {"kind": "avoid", "text": "avoid repeating failed corrections", "votes": 2},
    ]
    archive_log: list[dict] = []
    new_pool, applied = apply_memory_ops(
        pool,
        [
            {"op": "EDIT", "target_id": 0, "kind": "do", "text": "prefer untried open directions after a revisit"},
            {"op": "DOWNVOTE", "target_id": 1},
            {"op": "ADD", "target_id": None, "kind": "do", "text": "prefer untried open directions after a revisit"},
        ],
        cfg=cfg,
        archive_log=archive_log,
    )
    sources = [row["source"] for row in archive_log]
    assert "edit_before" in sources and "downvote" in sources and "similarity_merge" in sources, archive_log
    assert any(op.get("converted_from") == "ADD" for op in applied), applied
    assert len(new_pool) == 2
    print("gamma archive source checks OK")


def _archive_rescue_retrieval_checks() -> None:
    cfg = _cfg(memory_read_protocol="archive_rescue", retrieval_scoring="similarity", retrieval_k=1, archive_retrieval_k=1)
    memory = InsightMemory(cfg)
    memory.shared = [
        {"kind": "do", "text": "active lesson about open directions", "votes": 1},
        {"kind": "do", "text": "unrelated active lesson", "votes": 1},
    ]
    memory.add_archive_item(
        {"kind": "avoid", "text": "archive lesson about repeated corrections", "votes": 0},
        source="downvote",
        t=0,
        task_id="task",
        agent_id=0,
        op="DOWNVOTE",
    )
    got = memory.retrieve(0, "open directions and repeated corrections", t=1)
    assert len(got) == 2, got
    assert any(item.get("archived") for item in got), got
    assert any(not item.get("archived") for item in got), got
    memory.shared = []
    archive_only = memory.retrieve(0, "repeated corrections", t=2)
    assert len(archive_only) == 1 and archive_only[0].get("archived"), archive_only
    print("gamma archive rescue retrieval checks OK")


def _archive_joint_topk_checks() -> None:
    cfg = _cfg(
        memory_read_protocol="archive_joint_topk",
        retrieval_scoring="similarity",
        retrieval_k=2,
    )
    memory = InsightMemory(cfg)
    memory.shared = [
        {"kind": "do", "text": "active lesson about open directions", "votes": 1, "id": "active:relevant"},
        {"kind": "do", "text": "unrelated active lesson", "votes": 1, "id": "active:other"},
    ]
    memory.add_archive_item(
        {"kind": "avoid", "text": "archive lesson about repeated corrections", "votes": 0},
        source="downvote",
        t=0,
        task_id="task",
        agent_id=0,
        op="DOWNVOTE",
    )
    got = memory.retrieve(0, "open directions and repeated corrections", t=1)
    meta = memory.retrieval_metadata(0)
    assert len(got) == cfg.retrieval_k, got
    assert meta["injected_count"] == cfg.retrieval_k, meta
    assert meta["active_injected"] + meta["archive_injected"] == meta["injected_count"], meta
    assert meta["configured_total_limit"] == cfg.retrieval_k, meta
    assert meta["dose_compliant"] and meta["joint_rank"], meta
    assert any(item.get("archived") for item in got), got
    assert [row["rank"] for row in meta["ranking"]] == [1, 2], meta

    audit = MazeMemoryAudit()
    audit.record_retrieval(t=1, task_id="task", agent_id=0, items=got, metadata=meta)
    dose = audit.retrieval_dose_summary()
    assert dose["dose_violation_count"] == 0, dose
    assert dose["archive_selected_when_available"], dose
    print("gamma archive joint top-k checks OK")


def _budgeted_append_checks() -> None:
    cfg = _cfg(
        seed=0,
        memory_read_protocol="budgeted_append",
        budget_schedule_name="gamma_consolidated_active_cummax",
        retrieval_scoring="similarity",
        retrieval_k=99,
    )
    memory = InsightMemory(cfg)
    memory.shared = [{"kind": "do", "text": f"lesson {i}", "votes": 1} for i in range(10)]
    first = memory.retrieve(0, "lesson", t=1)
    first_ids = {item["id"] for item in first}
    assert len(first) == 6, first
    memory.shared = []
    second = memory.retrieve(0, "lesson", t=2)
    second_ids = {item["id"] for item in second}
    assert len(second) == 6, second
    assert first_ids == second_ids, "persistent snapshots must survive live-pool removal"
    print("gamma budgeted append checks OK")


def _drift_probe_checks() -> None:
    root = Path(".sec_mock_runs/gamma_stats")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    def result(successes: list[bool], loops: list[bool], steps: list[int]) -> dict:
        episodes = []
        for idx, success in enumerate(successes):
            route = {
                "success": success,
                "looped": loops[idx],
                "cost_ratio": steps[idx] / 10.0,
                "failure_penalized_steps": steps[idx],
                "excess_steps": steps[idx] - 10,
            }
            episodes.append({"task_id": f"task{idx}", "agents": [{"agent_id": 0, "route": route}]})
        return {"heldout_records": [{"t": 0, "episodes": episodes}]}

    baseline = root / "baseline.json"
    probe = root / "probe.json"
    baseline.write_text(json.dumps(result([True, True, False, True], [False, False, True, False], [10, 11, 20, 12])), encoding="utf-8")
    probe.write_text(json.dumps(result([True, True, False, True], [False, False, True, False], [10, 11, 20, 12])), encoding="utf-8")
    report = drift_probe_report(baseline_result=baseline, probe_result=probe, out_dir=root / "out", n_boot=200)
    assert report["passed"], report
    print("gamma drift probe checks OK")


def _retrieval_audit_checks() -> None:
    root = Path(".sec_mock_runs/gamma_retrieval_audit")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    intervention = root / "intervention.json"
    baseline = root / "baseline.json"
    intervention.write_text(
        json.dumps(
            {
                "summary": {"parse_failure_rate_final": 0.0},
                "memory_audit": {
                    "retrievals": [
                        {
                            "t": 1,
                            "items": ["active:a", "archive:b"],
                            "sources": ["active", "archive"],
                            "injected_count": 2,
                            "active_injected": 1,
                            "archive_injected": 1,
                            "configured_total_limit": 2,
                            "dose_compliant": True,
                            "joint_rank": True,
                            "archive_candidate_count": 1,
                        }
                    ],
                    "pool_trajectory": [
                        {
                            "t": 1,
                            "distinct_active_injected": 2,
                            "distinct_archive_injected": 2,
                            "distinct_total_injected": 4,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps(
            {
                "memory_audit": {
                    "retrievals": [
                        {
                            "t": 1,
                            "items": ["active:a"],
                            "sources": ["active"],
                        }
                    ],
                    "pool_trajectory": [{"t": 1, "distinct_active_injected": 2}],
                }
            }
        ),
        encoding="utf-8",
    )
    smoke = retrieval_audit_report(
        mode="smoke",
        runs=[f"clean:0={intervention}"],
        out_dir=root / "smoke",
        expected_limit=2,
    )
    assert smoke["decision"] == "smoke_pass", smoke
    formal = retrieval_audit_report(
        mode="formal",
        runs=[f"clean:0={intervention}"],
        baseline_runs=[f"consolidated:0={baseline}"],
        out_dir=root / "formal",
        t=1,
        expected_limit=2,
        distinct_ratio_min=1.5,
    )
    assert formal["decision"] == "manipulation_pass", formal
    print("gamma retrieval audit checks OK")


def _model_smoke_checks() -> None:
    root = Path(".sec_mock_runs/gamma_model_smoke")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    result_path = root / "result.json"
    agents = []
    for idx in range(48):
        agents.append(
            {
                "agent_id": idx,
                "route": {
                    "success": idx < 24,
                    "steps": 10,
                    "parse_failure_rate": 0.0,
                    "llm_error_count": 0,
                },
            }
        )
    result_path.write_text(
        json.dumps(
            {
                "config": {"model": "mock-qwen", "max_tokens_solver": 256},
                "summary": {
                    "llm": {
                        "network_calls": 480,
                        "retry_count": 1,
                        "content_filter_hits": 1,
                        "latency_p50_sec": 1.0,
                        "latency_p95_sec": 2.0,
                    }
                },
                "heldout_records": [
                    {
                        "t": 0,
                        "episodes": [{"task_id": "smoke", "agents": agents}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = model_smoke_report(result_path=result_path, out_dir=root / "out")
    assert report["decision"] == "smoke_pass", report
    assert report["metrics"]["route_count"] == 48, report
    print("gamma model smoke checks OK")


def _miniwob_summary_checks() -> None:
    obs_a = {"axtree_txt": "[bid123] textbox 'Name' value='Ada' focused=True x=10 y=20", "last_action_error": ""}
    obs_b = {"axtree_txt": "[bid999] textbox 'Name' value='Ada' focused=False x=99 y=20", "last_action_error": ""}
    obs_c = {"axtree_txt": "[bid999] textbox 'Name' value='Grace' focused=False x=99 y=20", "last_action_error": ""}
    assert miniwob_state_hash(obs_a) == miniwob_state_hash(obs_b)
    assert miniwob_state_hash(obs_a) != miniwob_state_hash(obs_c), "form values must remain in the hash"
    assert "bid" not in normalize_axtree_text(obs_a).lower()
    traj = [
        {"step": i, "action": f"click({i})", "state_hash": str(i % 2), "visible_text_delta": "delta", "error": "" if i != 3 else "bad"}
        for i in range(12)
    ]
    summary = reviewer_episode_summary(goal="click the button", success=False, steps=12, trajectory=traj, final_obs=obs_a)
    assert summary["invalid_or_error_count"] == 1
    assert summary["repeated_state_count"] == 10
    assert len(summary["final_axtree"]) <= 1200
    manifest = browsergym_version_manifest()
    assert set(MINIWOB_ALL_PREREG_TASKS) <= set(manifest["primary_tasks"] + manifest["replacement_tasks"])
    print("gamma miniwob summary checks OK")


def _phase_wiring_checks() -> None:
    from .maze_alpha import _arms_for_phase

    rescue = _arms_for_phase("gamma_p1_rescue")[0]
    assert rescue["memory_read_protocol"] == "archive_rescue"
    clean = _arms_for_phase("gamma_p1b_clean_rescue")[0]
    assert clean["memory_read_protocol"] == "archive_joint_topk"
    assert clean["run_id"] == "gamma_p1b_shared_consolidated_archive_joint_topk"
    budget = _arms_for_phase("gamma_p1_budgeted_append")[0]
    assert budget["memory_read_protocol"] == "budgeted_append"
    assert budget["budget_schedule_name"] == "gamma_consolidated_active_cummax"
    drift = _arms_for_phase("gamma_drift_probe")[0]
    assert drift["cache_policy"] == "off" and drift["T"] == 1 and drift["batch_M"] == 0
    p2 = _arms_for_phase("gamma_p2_cross_model")
    assert {arm["run_id"] for arm in p2} == {
        "gamma_p2_frozen_reviewer",
        "gamma_p2_shared_append_ga",
        "gamma_p2_shared_consolidated_expel",
    }
    delta = _arms_for_phase("delta_cross_model")
    assert {arm["run_id"] for arm in delta} == {
        "delta_frozen_reviewer",
        "delta_shared_append_ga",
        "delta_shared_consolidated_expel",
    }
    epsilon = _arms_for_phase("epsilon_controls")
    assert {arm["run_id"] for arm in epsilon} == {
        "epsilon_frozen_reviewer",
        "epsilon_private_consolidated",
        "epsilon_shared_consolidated",
        "epsilon_shared_append_cap14",
        "epsilon_shared_consolidated_mmr",
    }
    append_cap = next(arm for arm in epsilon if arm["run_id"] == "epsilon_shared_append_cap14")
    assert append_cap["library_cap"] == 14
    mmr = next(arm for arm in epsilon if arm["run_id"] == "epsilon_shared_consolidated_mmr")
    assert mmr["retrieval_scoring"] == "ga_mmr"
    sensitivity = _arms_for_phase("epsilon_sensitivity")
    assert len(sensitivity) == 9
    assert next(arm for arm in sensitivity if arm["run_id"] == "epsilon_sens_ops3")["max_reviewer_ops"] == 3
    print("gamma phase wiring checks OK")


def main() -> None:
    _config_checks()
    _mmr_and_operation_budget_checks()
    _archive_source_checks()
    _archive_rescue_retrieval_checks()
    _archive_joint_topk_checks()
    _budgeted_append_checks()
    _drift_probe_checks()
    _retrieval_audit_checks()
    _model_smoke_checks()
    _miniwob_summary_checks()
    _phase_wiring_checks()
    print("selftest_gamma OK")


if __name__ == "__main__":
    main()
