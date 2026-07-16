from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import Config
from .miniwob_gamma import (
    action_bid_reference,
    extract_bids,
    miniwob_state_hash,
    normalize_axtree_text,
    reviewer_episode_summary,
    solver_axtree_text,
)
from .miniwob_runner import _arms_for_phase, _route_from_trace, heldout_tasks
from .miniwob_gamma import (
    MINIWOB_PLUSPLUS_COMMIT,
    MINIWOB_PRIMARY_TASKS,
    MINIWOB_REPLACEMENT_TASKS,
)
from .miniwob_stats import (
    P3_ARM_CONFIG,
    P3_BROWSER_EXECUTABLE_SHA256,
    P3_BROWSER_TREE_FILE_COUNT,
    P3_BROWSER_TREE_SHA256,
    P3_BROWSER_TREE_TOTAL_BYTES,
    P3_BROWSER_VERSION,
    P3_PREREGISTRATION_LABEL,
    _expected_p3_config,
    _per_family_effects,
    formal_quality_report,
    p3_gate_report,
    smoke_report,
)


def _summary() -> dict:
    return reviewer_episode_summary(
        goal="submit the form",
        success=True,
        steps=2,
        trajectory=[
            {
                "step": 0,
                "action": "click('button')",
                "state_hash": "a",
                "visible_text_delta": "opened",
                "error": "",
            }
        ],
        final_obs={"axtree_txt": "[bid9] button 'Submit' focused=False x=1 y=2"},
    )


def _fake_result(
    *,
    family: str,
    cost: float,
    stall: bool,
    seed: str,
    condition: str = "frozen",
    smoke: bool = False,
) -> dict:
    heldout_size = 2 if smoke else 12
    rounds = 1 if smoke else 4
    heldout_records = []
    for t in range(rounds):
        episodes = []
        for instance in range(heldout_size):
            agents = []
            for agent_id in range(4):
                route = {
                    "success": not stall,
                    "steps": 6,
                    "failure_penalized_steps": int(round(cost * 15)),
                    "failure_penalized_cost": cost,
                    "repeated_action_same_state": stall,
                    "nontermination": False,
                    "loop_stall_burden": stall,
                    "parse_failure_count": 0,
                    "parse_attempt_count": 1,
                    "infrastructure_error_count": 0,
                    "bid_error_count": 0,
                    "executed_action_count": 1,
                }
                agents.append({"agent_id": agent_id, "route": route, "reviewer_summary": _summary()})
            episodes.append(
                {
                    "task_id": f"{family}:heldout:{seed}:{instance}",
                    "task": {"task_name": family, "instance_index": instance},
                    "agents": agents,
                }
            )
        heldout_records.append({"t": 0 if smoke else t, "episodes": episodes})
    config = _expected_p3_config(
        condition=condition,
        seed=seed,
        family=family,
    )
    if smoke:
        config.update(
            {
                "T": 1,
                "heldout_size": 2,
                "batch_M": 2,
                "n_train": 2,
                "skip_final_train": False,
                "cache_policy": "off",
                "cache_dir": "cache_miniwob_gamma_p3e_smoke",
                "out_dir": "runs_miniwob_gamma_p3e_smoke",
            }
        )
    return {
        "config": config,
        "task_family": family,
        "phase": "gamma_p3_smoke" if smoke else "gamma_p3_formal",
        "heldout_records": heldout_records,
        "hash_replays": (
            [{"n_matches": 2, "n_compared": 2}, {"n_matches": 2, "n_compared": 2}] if smoke else []
        ),
        "summary": {"llm": {}},
    }


def _fake_manifest(
    *,
    result: dict,
    family: str,
    seed: str,
    condition: str,
    smoke: bool = False,
) -> dict:
    arm = P3_ARM_CONFIG[condition]
    run_id = f"gamma_p3_{family.replace('-', '_')}_{arm['suffix']}"
    browser_executable = "C:/Program Files/Google/Chrome/Application/chrome.exe"
    browser_version = P3_BROWSER_VERSION
    browser_tree_root = "D:/antmill/tmp/pinned_chrome_150.0.7871.124/Application"
    versions = {
        "browsergym": "not-installed",
        "browsergym-core": "0.14.3",
        "browsergym-miniwob": "0.14.3",
        "gymnasium": "1.2.3",
        "playwright": "1.44.0",
    }
    task_validation = {
        "ok": True,
        "missing": [],
        "n_registered": 189,
        "miniwob_plusplus_commit": MINIWOB_PLUSPLUS_COMMIT,
        "browser_executable": browser_executable,
        "browser_version": browser_version,
        "browser_executable_sha256": P3_BROWSER_EXECUTABLE_SHA256,
        "browser_tree_root": browser_tree_root,
        "browser_tree_sha256": P3_BROWSER_TREE_SHA256,
        "browser_tree_file_count": P3_BROWSER_TREE_FILE_COUNT,
        "browser_tree_total_bytes": P3_BROWSER_TREE_TOTAL_BYTES,
        "python_version": "3.12.12 test",
        "versions": versions,
    }
    return {
        "condition": f"n4_gt_false_seed{seed}_{run_id}",
        "run_id": run_id,
        "phase": "gamma_p3_smoke" if smoke else "gamma_p3_formal",
        "arm": condition,
        "task_family": family,
        "seed": int(seed),
        "config": result["config"],
        "miniwob": {
            "miniwob_plusplus_commit": MINIWOB_PLUSPLUS_COMMIT,
            "primary_tasks": MINIWOB_PRIMARY_TASKS,
            "replacement_tasks": MINIWOB_REPLACEMENT_TASKS,
            "browser_executable": browser_executable,
            "browser_version": browser_version,
            "browser_executable_sha256": P3_BROWSER_EXECUTABLE_SHA256,
            "browser_tree_root": browser_tree_root,
            "browser_tree_sha256": P3_BROWSER_TREE_SHA256,
            "browser_tree_file_count": P3_BROWSER_TREE_FILE_COUNT,
            "browser_tree_total_bytes": P3_BROWSER_TREE_TOTAL_BYTES,
            "python_version": "3.12.12 test",
            "versions": versions,
            "miniwob_url": "file:///D:/antmill/tmp/miniwob-plusplus/miniwob/html/miniwob/",
            "task_validation": task_validation,
            "independent_envs_per_task": 4,
        },
        "preregistration": P3_PREREGISTRATION_LABEL,
    }


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    family_rows_a = [
        {
            "family": "click-button",
            "seed": "0",
            "t": 3,
            "task_id": f"task-{index}",
            "agent_id": 0,
            "failure_penalized_cost": 1.0,
        }
        for index in range(9)
    ] + [
        {
            "family": "click-button",
            "seed": "1",
            "t": 3,
            "task_id": "task-0",
            "agent_id": 0,
            "failure_penalized_cost": 9.0,
        }
    ]
    family_rows_b = [
        {
            **row,
            "failure_penalized_cost": 0.0,
        }
        for row in family_rows_a
    ]
    family_effect = next(
        row
        for row in _per_family_effects(
            family_rows_a,
            family_rows_b,
            t=3,
        )
        if row["metric"] == "failure_penalized_cost"
    )
    assert family_effect["mean_diff"] == 5.0
    assert family_effect["n_seeds"] == 2
    assert family_effect["aggregation"] == "equal_seed_mean_within_family"

    obs_a = {"axtree_txt": "[bid1] textbox value='Ada' focused=True x=1 y=2"}
    obs_b = {"axtree_txt": "[bid2] textbox value='Ada' focused=False x=9 y=2"}
    assert miniwob_state_hash(obs_a) == miniwob_state_hash(obs_b)
    assert "bid" not in normalize_axtree_text(obs_a).lower()
    assert len(_summary()["final_axtree"]) <= 1200

    solver_view = solver_axtree_text(obs_a)
    assert "[bid1]" in solver_view, "solver observation must preserve bids"
    assert "bid" not in _summary()["final_axtree"].lower(), "reviewer summary must stay bid-free"
    visible = extract_bids('GOAL: x\nAXTREE:\n[12] button "No"\n[a5] textbox')
    assert visible == {"12", "a5"}
    name, bid = action_bid_reference("click('No')")
    assert name == "click" and bid == "No" and bid not in visible, "label-as-bid must be flagged invalid"
    name, bid = action_bid_reference('fill("a5", "john")')
    assert name == "fill" and bid == "a5" and bid in visible
    name, bid = action_bid_reference("noop()")
    assert name == "noop" and bid is None
    route = _route_from_trace(
        success=True,
        steps=3,
        terminated=True,
        repeated_action_same_state=False,
        parse_failure_count=0,
        parse_attempt_count=3,
        llm_error_count=0,
        infrastructure_error_count=0,
        max_steps=15,
        bid_error_count=1,
        executed_action_count=3,
    )
    assert abs(route["bid_error_rate"] - 1 / 3) < 1e-9

    cfg = Config(dataset="miniwob", T=4, batch_M=4, n_train=16, heldout_size=12, run_id="p3_test")
    tasks = heldout_tasks("click-button", cfg)
    assert len(tasks) == 12 and len({task.reset_seed for task in tasks}) == 12
    arms = _arms_for_phase("gamma_p3_formal")
    assert {arm["arm"] for arm in arms} == {"frozen", "append", "consolidated"}
    assert next(arm for arm in arms if arm["arm"] == "frozen")["memory_mode"] == "frozen"
    failed = _route_from_trace(
        success=False,
        steps=4,
        terminated=False,
        repeated_action_same_state=True,
        parse_failure_count=1,
        parse_attempt_count=2,
        llm_error_count=0,
        infrastructure_error_count=0,
        max_steps=15,
    )
    assert failed["failure_penalized_cost"] == 1.0 and failed["loop_stall_burden"]

    root = Path(".sec_mock_runs/p3")
    shutil.rmtree(root, ignore_errors=True)
    families = ["click-button", "choose-list", "enter-text", "click-checkboxes", "login-user", "use-autocomplete-nodelay"]
    specs: list[str] = []
    for family in families:
        for seed in ("0", "1", "2"):
            frozen = root / f"{family}_frozen_{seed}" / "result.json"
            consolidated = root / f"{family}_consolidated_{seed}" / "result.json"
            append = root / f"{family}_append_{seed}" / "result.json"
            frozen_result = _fake_result(
                family=family,
                cost=0.4,
                stall=False,
                seed=seed,
                condition="frozen",
            )
            consolidated_result = _fake_result(
                family=family,
                cost=0.8,
                stall=True,
                seed=seed,
                condition="consolidated",
            )
            append_result = _fake_result(
                family=family,
                cost=0.5,
                stall=False,
                seed=seed,
                condition="append",
            )
            _write(frozen, frozen_result)
            _write(
                frozen.parent / "manifest.json",
                _fake_manifest(
                    result=frozen_result,
                    family=family,
                    seed=seed,
                    condition="frozen",
                ),
            )
            _write(consolidated, consolidated_result)
            _write(
                consolidated.parent / "manifest.json",
                _fake_manifest(
                    result=consolidated_result,
                    family=family,
                    seed=seed,
                    condition="consolidated",
                ),
            )
            _write(append, append_result)
            _write(
                append.parent / "manifest.json",
                _fake_manifest(
                    result=append_result,
                    family=family,
                    seed=seed,
                    condition="append",
                ),
            )
            specs.extend(
                [
                    f"frozen:{seed}:{family}={frozen}",
                    f"append:{seed}:{family}={append}",
                    f"consolidated:{seed}:{family}={consolidated}",
                ]
            )
    gate = p3_gate_report(
        runs=specs,
        intervention="consolidated",
        baseline="frozen",
        out_dir=root / "gate",
        t=3,
        n_boot=200,
    )
    assert gate["decision"] == "p3_phenomenon_pass", gate
    assert gate["formal_data_quality"]["status"] == "quality_clear", gate["formal_data_quality"]
    assert gate["preregistration_provenance"]["all_match"], gate["preregistration_provenance"]
    assert gate["preregistration_provenance"]["runtime_source"]["all_match"]
    assert len(gate["source_results"]) == len(specs)
    assert len(gate["source_manifests"]) == len(specs)
    quality = formal_quality_report(runs=specs)
    assert quality["aggregate"]["route_count"] == len(specs) * 192
    assert quality["status"] == "quality_clear", quality
    assert quality["checks"]["complete_matrix"]
    assert quality["checks"]["all_configurations"]
    assert quality["checks"]["all_manifests"]
    assert quality["checks"]["all_environments_consistent"]
    assert quality["checks"]["all_llm_behavioral_paths"]

    frozen_error_path = root / "click-button_frozen_0" / "result.json"
    frozen_error_result = json.loads(
        frozen_error_path.read_text(encoding="utf-8")
    )
    frozen_error_result["heldout_records"][0]["episodes"][0]["agents"][0][
        "route"
    ]["llm_error_count"] = 1
    frozen_error_result["summary"]["llm"] = {
        "errors": 1,
        "retry_count": 0,
        "content_filter_hits": 0,
    }
    frozen_error_path.write_text(
        json.dumps(frozen_error_result),
        encoding="utf-8",
    )
    frozen_warning_quality = formal_quality_report(runs=specs)
    frozen_warning_row = next(
        row
        for row in frozen_warning_quality["runs"]
        if row["condition"] == "frozen"
        and row["seed"] == "0"
        and row["family"] == "click-button"
    )
    assert frozen_warning_quality["status"] == "quality_clear"
    assert frozen_warning_row["llm_disclosure_warning"]
    assert frozen_warning_row["route_llm_error_count_all_rounds"] == 1
    assert frozen_warning_row["route_llm_error_count_final"] == 0
    assert frozen_warning_row["llm_behavioral_path_pass"]
    _write(
        frozen_error_path,
        _fake_result(
            family="click-button",
            cost=0.4,
            stall=False,
            seed="0",
            condition="frozen",
        ),
    )

    active_error_path = root / "click-button_consolidated_0" / "result.json"
    active_error_result = json.loads(
        active_error_path.read_text(encoding="utf-8")
    )
    active_error_result["heldout_records"][0]["episodes"][0]["agents"][0][
        "route"
    ]["llm_error_count"] = 1
    active_error_result["summary"]["llm"] = {
        "errors": 1,
        "retry_count": 0,
        "content_filter_hits": 0,
    }
    active_error_path.write_text(
        json.dumps(active_error_result),
        encoding="utf-8",
    )
    active_error_quality = formal_quality_report(runs=specs)
    active_error_row = next(
        row
        for row in active_error_quality["runs"]
        if row["condition"] == "consolidated"
        and row["seed"] == "0"
        and row["family"] == "click-button"
    )
    assert (
        active_error_quality["status"]
        == "quality_warning_review_required"
    )
    assert not active_error_quality["checks"]["all_llm_behavioral_paths"]
    assert not active_error_row["llm_behavioral_path_pass"]
    _write(
        active_error_path,
        _fake_result(
            family="click-button",
            cost=0.8,
            stall=True,
            seed="0",
            condition="consolidated",
        ),
    )

    partial_quality = formal_quality_report(runs=specs[:3])
    assert partial_quality["status"] == "quality_warning_review_required"
    assert not partial_quality["checks"]["complete_matrix"]
    partial_completed_health = formal_quality_report(
        runs=specs[:3],
        require_complete_matrix=False,
    )
    assert partial_completed_health["status"] == "quality_clear"
    assert not partial_completed_health["checks"]["complete_matrix"]

    bad_manifest_path = Path(gate["source_manifests"][0]["path"])
    bad_manifest = json.loads(bad_manifest_path.read_text(encoding="utf-8"))
    original_bad_manifest = json.loads(json.dumps(bad_manifest))
    bad_manifest["miniwob"]["miniwob_plusplus_commit"] = "wrong-commit"
    bad_manifest_path.write_text(json.dumps(bad_manifest), encoding="utf-8")
    bad_quality = formal_quality_report(runs=specs)
    assert bad_quality["status"] == "quality_warning_review_required"
    assert not bad_quality["checks"]["all_manifests"]
    assert any(
        not row["manifest_pass"]
        and any(
            mismatch["field"] == "miniwob.miniwob_plusplus_commit"
            for mismatch in row["manifest_mismatches"]
        )
        for row in bad_quality["runs"]
    )
    bad_manifest_path.write_text(
        json.dumps(original_bad_manifest),
        encoding="utf-8",
    )

    drift_manifest_path = Path(gate["source_manifests"][1]["path"])
    drift_manifest = json.loads(drift_manifest_path.read_text(encoding="utf-8"))
    drift_manifest["miniwob"]["browser_version"] = "150.0.7871.999"
    drift_manifest["miniwob"]["task_validation"]["browser_version"] = (
        "150.0.7871.999"
    )
    drift_manifest_path.write_text(json.dumps(drift_manifest), encoding="utf-8")
    drift_quality = formal_quality_report(runs=specs)
    assert drift_quality["status"] == "quality_warning_review_required"
    assert not drift_quality["checks"]["all_environments_consistent"]
    assert drift_quality["environment_consistency"]["signature_count"] == 2
    drift_gate = p3_gate_report(
        runs=specs,
        intervention="consolidated",
        baseline="frozen",
        out_dir=root / "drift_gate",
        t=3,
        n_boot=20,
    )
    assert (
        drift_gate["decision"]
        == "p3_not_behaviorally_interpretable_quality_warning"
    )
    assert drift_gate["paired_stats"] == {}
    assert drift_gate["per_family_effects"] == []

    smoke_specs: list[str] = []
    for family in families:
        for condition in ("frozen", "append", "consolidated"):
            smoke_path = root / "smoke" / family / condition / "result.json"
            smoke_result = _fake_result(
                family=family,
                cost=0.4,
                stall=False,
                seed="0",
                condition=condition,
                smoke=True,
            )
            _write(smoke_path, smoke_result)
            _write(
                smoke_path.parent / "manifest.json",
                _fake_manifest(
                    result=smoke_result,
                    family=family,
                    seed="0",
                    condition=condition,
                    smoke=True,
                ),
            )
            smoke_specs.append(
                f"{condition}:0:{family}={smoke_path}"
            )
    smoke = smoke_report(
        runs=smoke_specs,
        out_dir=root / "smoke_gate",
        expected_routes_per_result=8,
    )
    assert smoke["decision"] == "smoke_pass", smoke
    assert smoke["checks"]["complete_matrix"]
    assert smoke["checks"]["preregistration_hashes"]
    partial_smoke = smoke_report(
        runs=smoke_specs[:3],
        out_dir=root / "partial_smoke_gate",
        expected_routes_per_result=8,
    )
    assert partial_smoke["decision"] == "smoke_fail"
    assert not partial_smoke["checks"]["complete_matrix"]
    print("selftest_p3 OK")


if __name__ == "__main__":
    main()
