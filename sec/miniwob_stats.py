from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .miniwob_gamma import (
    MINIWOB_PLUSPLUS_COMMIT,
    MINIWOB_PRIMARY_TASKS,
    MINIWOB_REPLACEMENT_TASKS,
)


P3_METRICS = [
    "success",
    "steps",
    "failure_penalized_steps",
    "failure_penalized_cost",
    "repeated_action_same_state",
    "nontermination",
    "loop_stall_burden",
]
PRIMARY_METRICS = ["failure_penalized_cost", "loop_stall_burden"]
REVIEWER_SUMMARY_FIELDS = {
    "goal",
    "success",
    "steps",
    "invalid_or_error_count",
    "repeated_state_count",
    "steps_compact",
    "final_axtree",
}
P3_PREREG_FREEZE_FILES = [
    "prereg_phase_gamma_p3_execution.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_01.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_02.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_03.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_04.freeze.json",
]
P3_PREREGISTRATION_LABEL = (
    "prereg_phase_gamma_p3_execution.md + prereg_phase_gamma_p3_execution_amendment_01.md "
    "+ prereg_phase_gamma_p3_execution_amendment_02.md "
    "+ prereg_phase_gamma_p3_execution_amendment_03.md "
    "+ prereg_phase_gamma_p3_execution_amendment_04.md"
)
P3_RUNTIME_SOURCE_FREEZE = "p3e_runtime_source.freeze.json"
P3_BROWSER_VERSION = "150.0.7871.124"
P3_BROWSER_EXECUTABLE_SHA256 = (
    "40ad3d87ea81270f36137e6f84fb36e9a2236aedd835696dd663ac1a27dd1b13"
)
P3_BROWSER_TREE_SHA256 = (
    "aa89fed38bda67c473a1db216cb54d99ed55ee613317de248634e2cabffc9680"
)
P3_BROWSER_TREE_FILE_COUNT = 273
P3_BROWSER_TREE_TOTAL_BYTES = 501_388_593
P3_ENVIRONMENT_FIELDS = [
    "miniwob_plusplus_commit",
    "primary_tasks",
    "replacement_tasks",
    "python_version",
    "browser_executable",
    "browser_version",
    "browser_executable_sha256",
    "browser_tree_root",
    "browser_tree_sha256",
    "browser_tree_file_count",
    "browser_tree_total_bytes",
    "versions",
    "miniwob_url",
    "task_validation",
    "independent_envs_per_task",
]
P3_ARM_CONFIG = {
    "frozen": {
        "suffix": "frozen_reviewer",
        "memory_mode": "frozen",
        "memory_write_protocol": "expel_ops",
    },
    "append": {
        "suffix": "shared_append_ga",
        "memory_mode": "shared",
        "memory_write_protocol": "append",
    },
    "consolidated": {
        "suffix": "shared_consolidated_expel",
        "memory_mode": "shared",
        "memory_write_protocol": "expel_ops",
    },
}
P3_FORMAL_COMMON_CONFIG = {
    "model": "DeepSeek-V3",
    "base_url": "https://api.modelarts-maas.com/v2",
    "api_key_env": "MODELARTS_MAAS_KEY",
    "n_solvers": 4,
    "use_ground_truth": False,
    "batch_M": 4,
    "n_train": 16,
    "heldout_size": 12,
    "T": 4,
    "solver_temp": 0.7,
    "library_cap": 80,
    "retrieval_k": 6,
    "dataset": "miniwob",
    "max_steps": 15,
    "maze_write_mode": "reviewer",
    "skip_final_train": True,
    "retrieval_scoring": "ga",
    "ga_lambda": 0.0,
    "ga_recency": 0.0,
    "similarity_threshold": 0.80,
    "max_reviewer_ops": 6,
    "memory_read_protocol": "standard",
    "cache_policy": "read_write",
    "cache_dir": "cache_miniwob_gamma_p3e",
    "out_dir": "runs_miniwob_gamma_p3e",
    "max_tokens_solver": 256,
    "max_tokens_reviewer": 512,
}


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _p3_runtime_source_provenance() -> dict[str, Any]:
    freeze_path = Path(P3_RUNTIME_SOURCE_FREEZE)
    freeze = _load_json(freeze_path)
    files: list[dict[str, Any]] = []
    for expected in freeze.get("files", []):
        path = Path(str(expected.get("path", "")))
        expected_sha256 = str(expected.get("sha256", "")).lower()
        actual_sha256 = _sha256(path) if path.exists() else ""
        files.append(
            {
                "path": str(path),
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
                "match": bool(
                    path.exists()
                    and expected_sha256
                    and actual_sha256 == expected_sha256
                    and expected.get("before_process_start") is True
                ),
                "last_write_time": str(expected.get("last_write_time", "")),
                "before_process_start": expected.get("before_process_start"),
            }
        )
    return {
        "freeze_record": str(freeze_path),
        "git_head": str(freeze.get("git_head", "")),
        "status": str(freeze.get("status", "")),
        "process": freeze.get("process", {}),
        "files": files,
        "all_match": bool(files) and all(bool(row["match"]) for row in files),
    }


def p3_preregistration_provenance() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for raw_freeze_path in P3_PREREG_FREEZE_FILES:
        freeze_path = Path(raw_freeze_path)
        freeze = _load_json(freeze_path)
        document = Path(freeze.get("path") or freeze.get("document") or "")
        expected = str(freeze.get("sha256") or "").lower()
        actual = _sha256(document)
        rows.append(
            {
                "freeze_record": str(freeze_path),
                "document": str(document),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": actual == expected,
            }
        )
    runtime_source = _p3_runtime_source_provenance()
    return {
        "files": rows,
        "runtime_source": runtime_source,
        "all_match": bool(rows)
        and all(row["match"] for row in rows)
        and bool(runtime_source["all_match"]),
    }


def _parse_run(raw: str) -> tuple[str, str, str, Path]:
    if "=" not in raw:
        raise ValueError(f"--run must be condition:seed:family=path, got {raw!r}")
    label, raw_path = raw.split("=", 1)
    parts = label.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"--run label must be condition:seed:family, got {label!r}")
    return parts[0].strip(), parts[1].strip(), parts[2].strip(), Path(raw_path.strip())


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def route_rows(result: dict[str, Any], *, condition: str, seed: str, family: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in result.get("heldout_records", []):
        t = int(record.get("t", 0))
        for episode in record.get("episodes", []):
            task = episode.get("task", {})
            task_id = str(episode.get("task_id") or task.get("task_id") or "")
            instance_index = int(task.get("instance_index", 0))
            for agent in episode.get("agents", []):
                route = agent.get("route") or {}
                rows.append(
                    {
                        "condition": condition,
                        "seed": str(seed),
                        "family": family,
                        "t": t,
                        "task_id": task_id,
                        "instance_index": instance_index,
                        "agent_id": int(agent.get("agent_id", 0)),
                        "success": 1.0 if route.get("success") else 0.0,
                        "steps": float(route.get("steps") or 0.0),
                        "failure_penalized_steps": float(route.get("failure_penalized_steps") or 0.0),
                        "failure_penalized_cost": float(route.get("failure_penalized_cost") or 0.0),
                        "repeated_action_same_state": 1.0 if route.get("repeated_action_same_state") else 0.0,
                        "nontermination": 1.0 if route.get("nontermination") else 0.0,
                        "loop_stall_burden": 1.0 if route.get("loop_stall_burden") else 0.0,
                        "parse_failure_count": float(route.get("parse_failure_count") or 0.0),
                        "parse_attempt_count": float(route.get("parse_attempt_count") or 0.0),
                        "llm_error_count": float(route.get("llm_error_count") or 0.0),
                        "infrastructure_error_count": float(route.get("infrastructure_error_count") or 0.0),
                        "bid_error_count": float(route.get("bid_error_count") or 0.0),
                        "executed_action_count": float(route.get("executed_action_count") or 0.0),
                    }
                )
    return rows


def _load_route_rows(runs: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, family, path = _parse_run(raw)
        if not path.exists():
            raise FileNotFoundError(path)
        rows.extend(route_rows(_load_json(path), condition=condition, seed=seed, family=family))
    return rows


def _source_result_records(runs: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, family, path = _parse_run(raw)
        if not path.exists():
            raise FileNotFoundError(path)
        records.append(
            {
                "condition": condition,
                "seed": seed,
                "family": family,
                "path": str(path),
                "sha256": _sha256(path),
            }
        )
    return sorted(
        records,
        key=lambda row: (
            str(row["condition"]),
            str(row["seed"]),
            str(row["family"]),
        ),
    )


def _config_mismatches(actual: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "expected": expected_value,
            "actual": actual.get(field),
        }
        for field, expected_value in expected.items()
        if actual.get(field) != expected_value
    ]


def _expected_p3_config(*, condition: str, seed: str, family: str) -> dict[str, Any]:
    arm = P3_ARM_CONFIG.get(condition)
    if arm is None:
        return {"notes": [condition], "__unexpected_condition__": True}
    run_id = f"gamma_p3_{family.replace('-', '_')}_{arm['suffix']}"
    return {
        **P3_FORMAL_COMMON_CONFIG,
        "seed": int(seed),
        "run_id": run_id,
        "notes": [condition],
        "memory_mode": arm["memory_mode"],
        "memory_write_protocol": arm["memory_write_protocol"],
    }


def _expected_p3_smoke_config(
    *,
    condition: str,
    seed: str,
    family: str,
) -> dict[str, Any]:
    expected = _expected_p3_config(
        condition=condition,
        seed=seed,
        family=family,
    )
    expected.update(
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
    return expected


def _p3_environment_mismatches(miniwob: dict[str, Any]) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    task_validation = miniwob.get("task_validation", {})
    versions = miniwob.get("versions", {})
    miniwob_expected = {
        "miniwob_plusplus_commit": MINIWOB_PLUSPLUS_COMMIT,
        "primary_tasks": MINIWOB_PRIMARY_TASKS,
        "replacement_tasks": MINIWOB_REPLACEMENT_TASKS,
        "browser_version": P3_BROWSER_VERSION,
        "browser_executable_sha256": P3_BROWSER_EXECUTABLE_SHA256,
        "browser_tree_sha256": P3_BROWSER_TREE_SHA256,
        "browser_tree_file_count": P3_BROWSER_TREE_FILE_COUNT,
        "browser_tree_total_bytes": P3_BROWSER_TREE_TOTAL_BYTES,
        "independent_envs_per_task": 4,
    }
    mismatches.extend(
        {
            "field": f"miniwob.{row['field']}",
            "expected": row["expected"],
            "actual": row["actual"],
        }
        for row in _config_mismatches(miniwob, miniwob_expected)
    )
    required_nonempty = {
        "miniwob.browser_executable": miniwob.get("browser_executable"),
        "miniwob.browser_version": miniwob.get("browser_version"),
        "miniwob.browser_executable_sha256": miniwob.get(
            "browser_executable_sha256"
        ),
        "miniwob.browser_tree_root": miniwob.get("browser_tree_root"),
        "miniwob.browser_tree_sha256": miniwob.get("browser_tree_sha256"),
        "miniwob.miniwob_url": miniwob.get("miniwob_url"),
    }
    for field, value in required_nonempty.items():
        if not str(value or "").strip() or str(value).strip().lower() == "unavailable":
            mismatches.append(
                {
                    "field": field,
                    "expected": "nonempty recorded value",
                    "actual": value,
                }
            )
    for package in (
        "browsergym-core",
        "browsergym-miniwob",
        "gymnasium",
        "playwright",
    ):
        value = versions.get(package)
        if not str(value or "").strip() or str(value).strip().lower() in {
            "not-installed",
            "unavailable",
        }:
            mismatches.append(
                {
                    "field": f"miniwob.versions.{package}",
                    "expected": "installed version",
                    "actual": value,
                }
            )
    task_expected = {
        "ok": True,
        "missing": [],
        "miniwob_plusplus_commit": MINIWOB_PLUSPLUS_COMMIT,
    }
    mismatches.extend(
        {
            "field": f"miniwob.task_validation.{row['field']}",
            "expected": row["expected"],
            "actual": row["actual"],
        }
        for row in _config_mismatches(task_validation, task_expected)
    )
    if int(task_validation.get("n_registered") or 0) <= 0:
        mismatches.append(
            {
                "field": "miniwob.task_validation.n_registered",
                "expected": "positive integer",
                "actual": task_validation.get("n_registered"),
            }
        )
    for field in (
        "browser_executable",
        "browser_version",
        "browser_executable_sha256",
        "browser_tree_root",
        "browser_tree_sha256",
        "browser_tree_file_count",
        "browser_tree_total_bytes",
        "python_version",
        "versions",
    ):
        if task_validation.get(field) != miniwob.get(field):
            mismatches.append(
                {
                    "field": f"miniwob.task_validation.{field}",
                    "expected": miniwob.get(field),
                    "actual": task_validation.get(field),
                }
            )
    return mismatches


def _p3_manifest_validation(
    *,
    path: Path,
    result: dict[str, Any],
    condition: str,
    seed: str,
    family: str,
) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    manifest_path = path.parent / "manifest.json"
    source = {
        "condition": condition,
        "seed": seed,
        "family": family,
        "path": str(manifest_path),
        "sha256": _sha256(manifest_path) if manifest_path.exists() else "",
    }
    if not manifest_path.exists():
        return (
            False,
            [{"field": "manifest_path", "expected": str(manifest_path), "actual": "missing"}],
            source,
        )
    manifest = _load_json(manifest_path)
    arm = P3_ARM_CONFIG.get(condition, {})
    run_id = f"gamma_p3_{family.replace('-', '_')}_{arm.get('suffix', '')}"
    expected_condition = f"n4_gt_false_seed{seed}_{run_id}"
    mismatches = _config_mismatches(
        manifest,
        {
            "condition": expected_condition,
            "run_id": run_id,
            "phase": "gamma_p3_formal",
            "arm": condition,
            "task_family": family,
            "seed": int(seed),
            "config": result.get("config", {}),
            "preregistration": P3_PREREGISTRATION_LABEL,
        },
    )
    miniwob = manifest.get("miniwob", {})
    mismatches.extend(_p3_environment_mismatches(miniwob))
    return not mismatches, mismatches, source


def _p3_smoke_manifest_validation(
    *,
    path: Path,
    result: dict[str, Any],
    condition: str,
    seed: str,
    family: str,
) -> tuple[bool, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    manifest_path = path.parent / "manifest.json"
    source = {
        "condition": condition,
        "seed": seed,
        "family": family,
        "path": str(manifest_path),
        "sha256": _sha256(manifest_path) if manifest_path.exists() else "",
    }
    if not manifest_path.exists():
        return (
            False,
            [
                {
                    "field": "manifest_path",
                    "expected": str(manifest_path),
                    "actual": "missing",
                }
            ],
            source,
            {},
        )
    manifest = _load_json(manifest_path)
    arm = P3_ARM_CONFIG.get(condition, {})
    run_id = f"gamma_p3_{family.replace('-', '_')}_{arm.get('suffix', '')}"
    expected_condition = f"n4_gt_false_seed{seed}_{run_id}"
    mismatches = _config_mismatches(
        manifest,
        {
            "condition": expected_condition,
            "run_id": run_id,
            "phase": "gamma_p3_smoke",
            "arm": condition,
            "task_family": family,
            "seed": int(seed),
            "config": result.get("config", {}),
            "preregistration": P3_PREREGISTRATION_LABEL,
        },
    )
    miniwob = manifest.get("miniwob", {})
    mismatches.extend(_p3_environment_mismatches(miniwob))
    return not mismatches, mismatches, source, miniwob


def _source_manifest_records(runs: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, family, path = _parse_run(raw)
        result = _load_json(path)
        _passed, _mismatches, source = _p3_manifest_validation(
            path=path,
            result=result,
            condition=condition,
            seed=seed,
            family=family,
        )
        records.append(source)
    return sorted(
        records,
        key=lambda row: (
            str(row["condition"]),
            str(row["seed"]),
            str(row["family"]),
        ),
    )


def _reviewer_summary_schema_pass(result: dict[str, Any]) -> bool:
    for record in result.get("heldout_records", []):
        for episode in record.get("episodes", []):
            for agent in episode.get("agents", []):
                summary = agent.get("reviewer_summary", {})
                if (
                    not isinstance(summary, dict)
                    or not REVIEWER_SUMMARY_FIELDS <= set(summary)
                    or len(str(summary.get("final_axtree", ""))) > 1200
                ):
                    return False
    return True


def formal_quality_report(
    *,
    runs: list[str],
    parse_min: float = 0.95,
    infrastructure_error_max: float = 0.02,
    bid_error_max: float = 0.10,
    require_complete_matrix: bool = True,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    total_routes = 0
    total_parse_failures = 0.0
    total_parse_attempts = 0.0
    total_api_errors = 0
    total_retries = 0
    total_content_filter_hits = 0
    total_exhausted_llm_calls = 0
    total_route_llm_errors_all_rounds = 0
    total_route_llm_errors_final = 0
    total_route_llm_error_affected_routes = 0
    total_nonheldout_exhausted_llm_calls = 0
    total_audit_llm_errors = 0
    total_infrastructure_error_routes = 0
    total_bid_errors = 0.0
    total_executed_actions = 0.0
    for raw in runs:
        condition, seed, family, path = _parse_run(raw)
        result = _load_json(path)
        rows = route_rows(result, condition=condition, seed=seed, family=family)
        config = result.get("config", {})
        expected_config = _expected_p3_config(
            condition=condition,
            seed=seed,
            family=family,
        )
        config_mismatches = _config_mismatches(config, expected_config)
        result_metadata_mismatches = _config_mismatches(
            result,
            {
                "phase": "gamma_p3_formal",
                "task_family": family,
            },
        )
        config_mismatches.extend(
            {
                "field": f"result.{row['field']}",
                "expected": row["expected"],
                "actual": row["actual"],
            }
            for row in result_metadata_mismatches
        )
        manifest_pass, manifest_mismatches, manifest_source = _p3_manifest_validation(
            path=path,
            result=result,
            condition=condition,
            seed=seed,
            family=family,
        )
        manifest_path = path.parent / "manifest.json"
        manifest = _load_json(manifest_path) if manifest_path.exists() else {}
        miniwob_environment = manifest.get("miniwob", {})
        environment = {
            field: miniwob_environment.get(field)
            for field in P3_ENVIRONMENT_FIELDS
        }
        environment_digest = hashlib.sha256(
            json.dumps(
                environment,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        expected_rounds = int(config.get("T") or len(result.get("heldout_records", [])))
        expected_heldout = int(config.get("heldout_size") or 0)
        expected_solvers = int(config.get("n_solvers") or 0)
        expected_routes = expected_rounds * expected_heldout * expected_solvers
        if expected_routes <= 0:
            expected_routes = len(rows)
        parse_failures = sum(float(row["parse_failure_count"]) for row in rows)
        parse_attempts = sum(float(row["parse_attempt_count"]) for row in rows)
        llm_summary = result.get("summary", {}).get("llm", {})
        api_errors = int(llm_summary.get("errors", 0) or 0)
        retries = int(llm_summary.get("retry_count", 0) or 0)
        content_filter_hits = int(
            llm_summary.get("content_filter_hits", 0) or 0
        )
        exhausted_llm_calls = max(api_errors - retries, 0)
        route_llm_errors_all_rounds = int(
            sum(float(row["llm_error_count"]) for row in rows)
        )
        final_t = max((int(row["t"]) for row in rows), default=-1)
        route_llm_errors_final = int(
            sum(
                float(row["llm_error_count"])
                for row in rows
                if int(row["t"]) == final_t
            )
        )
        route_llm_error_affected_routes = sum(
            1 for row in rows if float(row["llm_error_count"]) > 0.0
        )
        route_llm_error_rounds = sorted(
            {
                int(row["t"])
                for row in rows
                if float(row["llm_error_count"]) > 0.0
            }
        )
        audit_llm_events = list(
            result.get("memory_audit", {}).get("llm_errors", [])
        )
        audit_llm_error_tags: dict[str, int] = defaultdict(int)
        for event in audit_llm_events:
            audit_llm_error_tags[str(event.get("tag", "unknown"))] += 1
        nonheldout_exhausted_llm_calls = max(
            exhausted_llm_calls - route_llm_errors_all_rounds,
            0,
        )
        active_memory_arm = condition in {"append", "consolidated"}
        llm_behavioral_path_pass = bool(
            route_llm_errors_final == 0
            and (
                not active_memory_arm
                or (
                    route_llm_errors_all_rounds == 0
                    and nonheldout_exhausted_llm_calls == 0
                    and not audit_llm_events
                )
            )
        )
        infrastructure_error_routes = sum(1 for row in rows if float(row["infrastructure_error_count"]) > 0.0)
        bid_errors = sum(float(row["bid_error_count"]) for row in rows)
        executed_actions = sum(float(row["executed_action_count"]) for row in rows)
        parse_rate = 1.0 - parse_failures / max(parse_attempts, 1.0)
        infrastructure_error_rate = infrastructure_error_routes / max(len(rows), 1)
        bid_error_rate = bid_errors / max(executed_actions, 1.0)
        schema_pass = _reviewer_summary_schema_pass(result)
        entry = {
            "condition": condition,
            "seed": seed,
            "family": family,
            "path": str(path),
            "route_count": len(rows),
            "expected_routes": expected_routes,
            "route_count_pass": len(rows) == expected_routes,
            "parse_rate": parse_rate,
            "parse_pass": parse_rate >= parse_min,
            "api_error_count": api_errors,
            "retry_count": retries,
            "content_filter_hits": content_filter_hits,
            "exhausted_llm_call_count": exhausted_llm_calls,
            "route_llm_error_count_all_rounds": (
                route_llm_errors_all_rounds
            ),
            "route_llm_error_count_final": route_llm_errors_final,
            "route_llm_error_count_nonterminal": max(
                route_llm_errors_all_rounds - route_llm_errors_final,
                0,
            ),
            "route_llm_error_affected_routes": (
                route_llm_error_affected_routes
            ),
            "route_llm_error_rounds": route_llm_error_rounds,
            "nonheldout_exhausted_llm_call_count": (
                nonheldout_exhausted_llm_calls
            ),
            "audit_llm_error_count": len(audit_llm_events),
            "audit_llm_error_tags": dict(
                sorted(audit_llm_error_tags.items())
            ),
            "active_memory_arm": active_memory_arm,
            "llm_behavioral_path_pass": llm_behavioral_path_pass,
            "llm_disclosure_warning": bool(
                api_errors
                or retries
                or content_filter_hits
                or exhausted_llm_calls
                or route_llm_errors_all_rounds
                or audit_llm_events
            ),
            "infrastructure_error_route_rate": infrastructure_error_rate,
            "infrastructure_pass": infrastructure_error_rate <= infrastructure_error_max,
            "bid_error_rate": bid_error_rate,
            "bid_pass": bid_error_rate <= bid_error_max,
            "reviewer_summary_schema_pass": schema_pass,
            "configuration_pass": not config_mismatches,
            "configuration_mismatches": config_mismatches,
            "manifest_pass": manifest_pass,
            "manifest_mismatches": manifest_mismatches,
            "manifest_path": manifest_source["path"],
            "manifest_sha256": manifest_source["sha256"],
            "environment_signature_sha256": environment_digest,
            "environment": environment,
        }
        entry["passed"] = bool(
            entry["route_count_pass"]
            and entry["parse_pass"]
            and entry["llm_behavioral_path_pass"]
            and entry["infrastructure_pass"]
            and entry["bid_pass"]
            and entry["reviewer_summary_schema_pass"]
            and entry["configuration_pass"]
            and entry["manifest_pass"]
        )
        details.append(entry)
        total_routes += len(rows)
        total_parse_failures += parse_failures
        total_parse_attempts += parse_attempts
        total_api_errors += api_errors
        total_retries += retries
        total_content_filter_hits += content_filter_hits
        total_exhausted_llm_calls += exhausted_llm_calls
        total_route_llm_errors_all_rounds += (
            route_llm_errors_all_rounds
        )
        total_route_llm_errors_final += route_llm_errors_final
        total_route_llm_error_affected_routes += (
            route_llm_error_affected_routes
        )
        total_nonheldout_exhausted_llm_calls += (
            nonheldout_exhausted_llm_calls
        )
        total_audit_llm_errors += len(audit_llm_events)
        total_infrastructure_error_routes += infrastructure_error_routes
        total_bid_errors += bid_errors
        total_executed_actions += executed_actions
    environment_groups: dict[str, dict[str, Any]] = {}
    for row in details:
        digest = str(row["environment_signature_sha256"])
        group = environment_groups.setdefault(
            digest,
            {
                "sha256": digest,
                "environment": row["environment"],
                "runs": [],
            },
        )
        group["runs"].append(
            {
                "condition": row["condition"],
                "seed": row["seed"],
                "family": row["family"],
                "path": row["path"],
            }
        )
    environments_consistent = bool(details) and len(environment_groups) == 1
    for row in details:
        row["environment_consistency_pass"] = environments_consistent
        row["passed"] = bool(row["passed"] and environments_consistent)
    expected_run_keys = {
        (condition, str(seed), family)
        for condition in P3_ARM_CONFIG
        for seed in range(3)
        for family in MINIWOB_PRIMARY_TASKS
    }
    actual_run_keys = {
        (str(row["condition"]), str(row["seed"]), str(row["family"]))
        for row in details
    }
    checks = {
        "complete_matrix": len(details) == len(expected_run_keys)
        and actual_run_keys == expected_run_keys,
        "all_route_counts": all(bool(row["route_count_pass"]) for row in details),
        "all_parse_rates": all(bool(row["parse_pass"]) for row in details),
        "all_llm_behavioral_paths": all(
            bool(row["llm_behavioral_path_pass"]) for row in details
        ),
        "all_infrastructure_error_rates": all(bool(row["infrastructure_pass"]) for row in details),
        "all_bid_error_rates": all(bool(row["bid_pass"]) for row in details),
        "all_reviewer_summary_schemas": all(bool(row["reviewer_summary_schema_pass"]) for row in details),
        "all_configurations": all(bool(row["configuration_pass"]) for row in details),
        "all_manifests": all(bool(row["manifest_pass"]) for row in details),
        "all_environments_consistent": environments_consistent,
    }
    status_checks = {
        key: value
        for key, value in checks.items()
        if require_complete_matrix or key != "complete_matrix"
    }
    return {
        "status": (
            "quality_clear"
            if details and all(status_checks.values())
            else "quality_warning_review_required"
        ),
        "thresholds": {
            "parse_min": parse_min,
            "infrastructure_error_max": infrastructure_error_max,
            "bid_error_max": bid_error_max,
            "require_complete_matrix": require_complete_matrix,
        },
        "checks": checks,
        "aggregate": {
            "run_count": len(details),
            "route_count": total_routes,
            "parse_rate": 1.0 - total_parse_failures / max(total_parse_attempts, 1.0),
            "api_error_count": total_api_errors,
            "retry_count": total_retries,
            "content_filter_hits": total_content_filter_hits,
            "exhausted_llm_call_count": total_exhausted_llm_calls,
            "route_llm_error_count_all_rounds": (
                total_route_llm_errors_all_rounds
            ),
            "route_llm_error_count_final": (
                total_route_llm_errors_final
            ),
            "route_llm_error_affected_routes": (
                total_route_llm_error_affected_routes
            ),
            "nonheldout_exhausted_llm_call_count": (
                total_nonheldout_exhausted_llm_calls
            ),
            "audit_llm_error_count": total_audit_llm_errors,
            "llm_disclosure_warning_run_count": sum(
                1
                for row in details
                if bool(row["llm_disclosure_warning"])
            ),
            "infrastructure_error_route_rate": total_infrastructure_error_routes / max(total_routes, 1),
            "bid_error_rate": total_bid_errors / max(total_executed_actions, 1.0),
        },
        "environment_consistency": {
            "fields": P3_ENVIRONMENT_FIELDS,
            "signature_count": len(environment_groups),
            "consistent": environments_consistent,
            "groups": sorted(
                environment_groups.values(),
                key=lambda group: str(group["sha256"]),
            ),
        },
        "runs": details,
    }


def _pair_diffs(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    *,
    metric: str,
    t: int,
) -> tuple[dict[tuple[str, str], list[float]], int]:
    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int, str, int], dict[str, Any]]:
        return {
            (
                str(row["family"]),
                str(row["seed"]),
                int(row["t"]),
                str(row["task_id"]),
                int(row["agent_id"]),
            ): row
            for row in rows
            if int(row["t"]) == t
        }

    a_index = index(rows_a)
    b_index = index(rows_b)
    keys = sorted(set(a_index) & set(b_index))
    dropped = (len(a_index) - len(keys)) + (len(b_index) - len(keys))
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for key in keys:
        value_a = a_index[key].get(metric)
        value_b = b_index[key].get(metric)
        if value_a is None or value_b is None:
            dropped += 1
            continue
        grouped[(key[0], key[1])].append(float(value_a) - float(value_b))
    return grouped, dropped


def _equal_family_mean(grouped: dict[tuple[str, str], list[float]]) -> float:
    per_family: dict[str, list[float]] = defaultdict(list)
    for (family, _seed), values in grouped.items():
        if values:
            per_family[family].append(float(np.mean(values)))
    return float(np.mean([float(np.mean(values)) for values in per_family.values()])) if per_family else 0.0


def _cluster_bootstrap(
    grouped: dict[tuple[str, str], list[float]],
    *,
    n_boot: int,
    rng_seed: int,
) -> tuple[float, float]:
    families = sorted({family for family, _seed in grouped})
    if not families:
        return 0.0, 0.0
    rng = np.random.default_rng(rng_seed)
    boots: list[float] = []
    for _ in range(n_boot):
        family_means: list[float] = []
        for family in families:
            seed_groups = [values for (group_family, _seed), values in grouped.items() if group_family == family and values]
            if not seed_groups:
                continue
            selected_seed_groups = rng.integers(0, len(seed_groups), size=len(seed_groups))
            seed_means: list[float] = []
            for index in selected_seed_groups:
                values = np.asarray(seed_groups[int(index)], dtype=float)
                sampled = values[rng.integers(0, len(values), size=len(values))]
                seed_means.append(float(sampled.mean()))
            family_means.append(float(np.mean(seed_means)))
        if family_means:
            boots.append(float(np.mean(family_means)))
    if not boots:
        return 0.0, 0.0
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def paired_stat(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    *,
    metric: str,
    t: int,
    n_boot: int,
    rng_seed: int,
) -> dict[str, Any]:
    grouped, dropped = _pair_diffs(rows_a, rows_b, metric=metric, t=t)
    pair_count = sum(len(values) for values in grouped.values())
    family_count = len({family for family, _seed in grouped})
    seed_count = len({seed for _family, seed in grouped})
    if not pair_count:
        return {
            "metric": metric,
            "n_pairs": 0,
            "n_families": 0,
            "n_seeds": 0,
            "n_dropped": dropped,
            "mean_diff": 0.0,
            "ci_lo": 0.0,
            "ci_hi": 0.0,
            "ci_excludes_zero": False,
        }
    lo, hi = _cluster_bootstrap(grouped, n_boot=n_boot, rng_seed=rng_seed)
    return {
        "metric": metric,
        "n_pairs": pair_count,
        "n_families": family_count,
        "n_seeds": seed_count,
        "n_dropped": dropped,
        "mean_diff": _equal_family_mean(grouped),
        "ci_lo": lo,
        "ci_hi": hi,
        "ci_excludes_zero": bool(lo > 0.0 or hi < 0.0),
    }


def _per_seed_signs(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    *,
    metric: str,
    t: int,
) -> dict[str, Any]:
    grouped, _dropped = _pair_diffs(rows_a, rows_b, metric=metric, t=t)
    by_seed: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (family, seed), values in grouped.items():
        by_seed[seed][family].extend(values)
    diffs = {
        seed: float(np.mean([float(np.mean(values)) for values in by_family.values() if values]))
        for seed, by_family in by_seed.items()
    }
    return {
        "metric": metric,
        "direction": "positive_is_worse",
        "count": sum(1 for value in diffs.values() if value > 0.0),
        "n": len(diffs),
        "diffs": diffs,
    }


def _per_family_effects(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    *,
    t: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for family in sorted({str(row["family"]) for row in rows_a + rows_b}):
        a = [row for row in rows_a if row["family"] == family]
        b = [row for row in rows_b if row["family"] == family]
        for metric in P3_METRICS:
            grouped, dropped = _pair_diffs(a, b, metric=metric, t=t)
            seed_means = {
                seed: float(np.mean(values))
                for (group_family, seed), values in sorted(grouped.items())
                if group_family == family and values
            }
            rows.append(
                {
                    "family": family,
                    "metric": metric,
                    "n_pairs": sum(
                        len(values)
                        for (group_family, _seed), values in grouped.items()
                        if group_family == family
                    ),
                    "n_seeds": len(seed_means),
                    "n_dropped": dropped,
                    "mean_diff": (
                        float(np.mean(list(seed_means.values())))
                        if seed_means
                        else 0.0
                    ),
                    "per_seed_diffs": seed_means,
                    "aggregation": "equal_seed_mean_within_family",
                }
            )
    return rows


def p3_gate_report(
    *,
    runs: list[str],
    intervention: str,
    baseline: str,
    out_dir: Path,
    t: int,
    n_boot: int = 10_000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    quality = formal_quality_report(runs=runs)
    provenance = p3_preregistration_provenance()
    source_results = _source_result_records(runs)
    source_manifests = _source_manifest_records(runs)
    if quality["status"] != "quality_clear" or not provenance["all_match"]:
        result = {
            "kind": "p3",
            "intervention": intervention,
            "baseline": baseline,
            "t": t,
            "decision": "p3_not_behaviorally_interpretable_quality_warning",
            "checks": {},
            "paired_stats": {},
            "per_family_effects": [],
            "formal_data_quality": quality,
            "preregistration_provenance": provenance,
            "source_results": source_results,
            "source_manifests": source_manifests,
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "p3_gate_report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_csv(quality["runs"], out_dir / "p3_formal_data_quality.csv")
        (out_dir / "p3_gate_report.md").write_text(
            "\n".join(
                [
                    "# Gamma P3 MiniWoB Gate",
                    "",
                    "Decision: **p3_not_behaviorally_interpretable_quality_warning**",
                    "",
                    "Behavioral estimates are withheld because formal data quality "
                    "or preregistration provenance is not clear.",
                    "",
                    "```json",
                    json.dumps(
                        {
                            "quality_status": quality["status"],
                            "quality_checks": quality["checks"],
                            "preregistration_hashes_match": provenance["all_match"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return result
    rows = _load_route_rows(runs)
    a = [row for row in rows if row["condition"] == intervention]
    b = [row for row in rows if row["condition"] == baseline]
    stats = {
        metric: paired_stat(a, b, metric=metric, t=t, n_boot=n_boot, rng_seed=rng_seed)
        for metric in P3_METRICS
    }
    signs = {
        metric: _per_seed_signs(a, b, metric=metric, t=t)
        for metric in PRIMARY_METRICS
    }
    checks = {
        "failure_penalized_cost_worse_ci": bool(stats["failure_penalized_cost"]["ci_lo"] > 0.0),
        "loop_stall_burden_worse_ci": bool(stats["loop_stall_burden"]["ci_lo"] > 0.0),
        "failure_penalized_cost_same_sign_seeds": signs["failure_penalized_cost"],
        "loop_stall_burden_same_sign_seeds": signs["loop_stall_burden"],
    }
    passed = (
        checks["failure_penalized_cost_worse_ci"]
        and checks["loop_stall_burden_worse_ci"]
        and signs["failure_penalized_cost"]["count"] >= 2
        and signs["failure_penalized_cost"]["n"] >= 3
        and signs["loop_stall_burden"]["count"] >= 2
        and signs["loop_stall_burden"]["n"] >= 3
    )
    result = {
        "kind": "p3",
        "intervention": intervention,
        "baseline": baseline,
        "t": t,
        "decision": "p3_phenomenon_pass" if passed else "p3_not_detected_or_underpowered",
        "checks": checks,
        "paired_stats": stats,
        "per_family_effects": _per_family_effects(a, b, t=t),
        "formal_data_quality": quality,
        "preregistration_provenance": provenance,
        "source_results": source_results,
        "source_manifests": source_manifests,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "p3_gate_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(rows, out_dir / "per_route_metrics.csv")
    _write_csv(
        [{"metric": metric, **stat} for metric, stat in stats.items()],
        out_dir / "p3_paired_stats.csv",
    )
    _write_csv(result["per_family_effects"], out_dir / "p3_per_family_effects.csv")
    _write_csv(quality["runs"], out_dir / "p3_formal_data_quality.csv")
    per_seed = []
    for metric, summary in signs.items():
        for seed, diff in summary["diffs"].items():
            per_seed.append({"metric": metric, "seed": seed, "mean_diff": diff, "positive_is_worse": diff > 0.0})
    _write_csv(per_seed, out_dir / "p3_per_seed_signs.csv")
    lines = [
        "# Gamma P3 MiniWoB Gate",
        "",
        f"Decision: **{result['decision']}**",
        "",
        "Primary contrast: consolidated minus frozen at terminal t=3. Positive cost/stall effects are worse. "
        "Bootstrap resamples seed clusters within each task family and averages task families equally.",
        "",
        "| metric | mean diff | ci lo | ci hi | n pairs | excludes zero |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for metric, stat in stats.items():
        lines.append(
            f"| {metric} | {stat['mean_diff']:.4f} | {stat['ci_lo']:.4f} | "
            f"{stat['ci_hi']:.4f} | {stat['n_pairs']} | {'yes' if stat['ci_excludes_zero'] else 'no'} |"
        )
    lines.extend(["", "## Gate Checks", "", "```json", json.dumps(checks, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(
        [
            "## Formal Data Quality",
            "",
            f"Status: **{quality['status']}**",
            "",
            "These descriptive checks reuse the frozen smoke engineering thresholds; "
            "they do not alter the preregistered outcome gate. The LLM-path gate "
            "additionally withholds any terminal route error and any unresolved "
            "active-memory held-out, training, or reviewer error; nonterminal "
            "frozen-arm errors remain disclosed because frozen memory is never injected.",
            "",
            "```json",
            json.dumps({"checks": quality["checks"], "aggregate": quality["aggregate"]}, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    lines.extend(
        [
            "## Preregistration Provenance",
            "",
            f"All frozen document hashes match: **{'yes' if provenance['all_match'] else 'no'}**",
            "",
        ]
    )
    (out_dir / "p3_gate_report.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def smoke_report(
    *,
    runs: list[str],
    out_dir: Path,
    parse_min: float = 0.95,
    infrastructure_error_max: float = 0.02,
    hash_agreement_min: float = 0.95,
    expected_routes_per_result: int = 8,
    bid_error_max: float = 0.10,
    min_family_successes: int = 1,
) -> dict[str, Any]:
    task_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_routes = 0
    total_parse_failures = 0.0
    total_parse_attempts = 0.0
    total_infra_error_routes = 0
    total_hash_matches = 0
    total_hash_compared = 0
    summary_valid = True
    details: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, family, path = _parse_run(raw)
        result = _load_json(path)
        expected_config = _expected_p3_smoke_config(
            condition=condition,
            seed=seed,
            family=family,
        )
        config_mismatches = _config_mismatches(
            result.get("config", {}),
            expected_config,
        )
        result_metadata_mismatches = _config_mismatches(
            result,
            {
                "phase": "gamma_p3_smoke",
                "task_family": family,
            },
        )
        config_mismatches.extend(
            {
                "field": f"result.{row['field']}",
                "expected": row["expected"],
                "actual": row["actual"],
            }
            for row in result_metadata_mismatches
        )
        (
            manifest_pass,
            manifest_mismatches,
            manifest_source,
            miniwob_environment,
        ) = _p3_smoke_manifest_validation(
            path=path,
            result=result,
            condition=condition,
            seed=seed,
            family=family,
        )
        environment = {
            field: miniwob_environment.get(field)
            for field in P3_ENVIRONMENT_FIELDS
        }
        environment_digest = hashlib.sha256(
            json.dumps(
                environment,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        rows = route_rows(result, condition=condition, seed=seed, family=family)
        expected_ok = len(rows) == expected_routes_per_result
        route_parse_failures = sum(row["parse_failure_count"] for row in rows)
        route_parse_attempts = sum(row["parse_attempt_count"] for row in rows)
        route_infra = sum(1 for row in rows if row["infrastructure_error_count"] > 0)
        for record in result.get("heldout_records", []):
            for episode in record.get("episodes", []):
                for agent in episode.get("agents", []):
                    summary = agent.get("reviewer_summary", {})
                    valid = (
                        isinstance(summary, dict)
                        and REVIEWER_SUMMARY_FIELDS <= set(summary)
                        and len(str(summary.get("final_axtree", ""))) <= 1200
                    )
                    summary_valid = summary_valid and valid
        for replay in result.get("hash_replays", []):
            total_hash_matches += int(replay.get("n_matches", 0))
            total_hash_compared += int(replay.get("n_compared", 0))
        total_routes += len(rows)
        total_parse_failures += route_parse_failures
        total_parse_attempts += route_parse_attempts
        total_infra_error_routes += route_infra
        route_bid_errors = sum(row["bid_error_count"] for row in rows)
        route_executed = sum(row["executed_action_count"] for row in rows)
        entry = {
            "condition": condition,
            "seed": seed,
            "family": family,
            "path": str(path),
            "route_count": len(rows),
            "expected_routes": expected_routes_per_result,
            "route_count_pass": expected_ok,
            "parse_rate": 1.0 - route_parse_failures / max(route_parse_attempts, 1.0),
            "infrastructure_error_route_rate": route_infra / max(len(rows), 1),
            "bid_error_rate": route_bid_errors / max(route_executed, 1.0),
            "success_count": sum(1 for row in rows if row["success"] > 0),
            "configuration_pass": not config_mismatches,
            "configuration_mismatches": config_mismatches,
            "manifest_pass": manifest_pass,
            "manifest_mismatches": manifest_mismatches,
            "manifest_path": manifest_source["path"],
            "manifest_sha256": manifest_source["sha256"],
            "environment_signature_sha256": environment_digest,
            "environment": environment,
        }
        details.append(entry)
        task_rows[family].append(entry)
    parse_rate = 1.0 - total_parse_failures / max(total_parse_attempts, 1.0)
    infra_rate = total_infra_error_routes / max(total_routes, 1)
    hash_agreement = total_hash_matches / max(total_hash_compared, 1)
    expected_run_keys = {
        (condition, "0", family)
        for condition in P3_ARM_CONFIG
        for family in MINIWOB_PRIMARY_TASKS
    }
    actual_run_keys = {
        (str(row["condition"]), str(row["seed"]), str(row["family"]))
        for row in details
    }
    provenance = p3_preregistration_provenance()
    environment_groups: dict[str, dict[str, Any]] = {}
    for row in details:
        digest = str(row["environment_signature_sha256"])
        group = environment_groups.setdefault(
            digest,
            {
                "sha256": digest,
                "environment": row["environment"],
                "runs": [],
            },
        )
        group["runs"].append(
            {
                "condition": row["condition"],
                "seed": row["seed"],
                "family": row["family"],
                "path": row["path"],
            }
        )
    environments_consistent = bool(details) and len(environment_groups) == 1
    for row in details:
        row["environment_consistency_pass"] = environments_consistent
    task_eligibility = []
    for family, rows in sorted(task_rows.items()):
        family_bid_ok = all(row["bid_error_rate"] <= bid_error_max for row in rows)
        family_successes = sum(int(row["success_count"]) for row in rows)
        passed = (
            all(row["route_count_pass"] for row in rows)
            and all(row["parse_rate"] >= parse_min for row in rows)
            and all(row["infrastructure_error_route_rate"] <= infrastructure_error_max for row in rows)
            and family_bid_ok
            and family_successes >= min_family_successes
        )
        task_eligibility.append(
            {
                "family": family,
                "passed": passed,
                "runs": len(rows),
                "bid_error_ok": family_bid_ok,
                "success_count": family_successes,
            }
        )
    checks = {
        "complete_matrix": len(details) == len(expected_run_keys)
        and actual_run_keys == expected_run_keys,
        "task_route_counts": all(row["route_count_pass"] for row in details),
        "parse_rate": parse_rate >= parse_min,
        "infrastructure_error_rate": infra_rate <= infrastructure_error_max,
        "hash_agreement": hash_agreement >= hash_agreement_min,
        "reviewer_summary_schema": summary_valid,
        "semantic_action_calibration": all(row["bid_error_ok"] for row in task_eligibility)
        and all(int(row["success_count"]) >= min_family_successes for row in task_eligibility),
        "all_task_eligible": all(row["passed"] for row in task_eligibility),
        "all_configurations": all(
            bool(row["configuration_pass"]) for row in details
        ),
        "all_manifests": all(bool(row["manifest_pass"]) for row in details),
        "all_environments_consistent": environments_consistent,
        "preregistration_hashes": bool(provenance["all_match"]),
    }
    result = {
        "kind": "p3_smoke",
        "decision": "smoke_pass" if all(checks.values()) else "smoke_fail",
        "checks": checks,
        "metrics": {
            "route_count": total_routes,
            "parse_rate": parse_rate,
            "infrastructure_error_route_rate": infra_rate,
            "state_hash_agreement": hash_agreement,
            "hash_compared": total_hash_compared,
            "bid_error_rate_max_per_run": max((row["bid_error_rate"] for row in details), default=0.0),
        },
        "task_eligibility": task_eligibility,
        "environment_consistency": {
            "fields": P3_ENVIRONMENT_FIELDS,
            "signature_count": len(environment_groups),
            "consistent": environments_consistent,
            "groups": sorted(
                environment_groups.values(),
                key=lambda group: str(group["sha256"]),
            ),
        },
        "preregistration_provenance": provenance,
        "source_results": _source_result_records(runs),
        "source_manifests": sorted(
            [
                {
                    "condition": row["condition"],
                    "seed": row["seed"],
                    "family": row["family"],
                    "path": row["manifest_path"],
                    "sha256": row["manifest_sha256"],
                }
                for row in details
            ],
            key=lambda row: (
                str(row["condition"]),
                str(row["seed"]),
                str(row["family"]),
            ),
        ),
        "runs": details,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "p3_smoke_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(details, out_dir / "p3_smoke_runs.csv")
    _write_csv(task_eligibility, out_dir / "p3_smoke_task_eligibility.csv")
    lines = [
        "# Gamma P3 MiniWoB Smoke",
        "",
        f"Decision: **{result['decision']}**",
        "",
        f"- routes: {total_routes}",
        f"- action parse rate: {parse_rate:.4f}",
        f"- infrastructure-error route rate: {infra_rate:.4f}",
        f"- state-hash agreement: {hash_agreement:.4f} ({total_hash_compared} hashes)",
        f"- worst per-run bid-error rate: {max((row['bid_error_rate'] for row in details), default=0.0):.4f}",
        "",
        "## Checks",
        "",
        "```json",
        json.dumps(checks, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    (out_dir / "p3_smoke_report.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def latency_summary(*, runs: list[str], out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, family, path = _parse_run(raw)
        result = _load_json(path)
        summary = result.get("summary", {})
        llm = summary.get("llm", {})
        rows.append(
            {
                "condition": condition,
                "seed": seed,
                "family": family,
                "path": str(path),
                "elapsed_sec": summary.get("elapsed_sec", 0.0),
                "total_calls": llm.get("total_calls", 0),
                "network_calls": llm.get("network_calls", 0),
                "cache_hits": llm.get("cache_hits", 0),
                "trace_total_tokens": llm.get("trace_total_tokens", 0),
                "latency_p50_sec": llm.get("latency_p50_sec", 0.0),
                "latency_p95_sec": llm.get("latency_p95_sec", 0.0),
                "retry_count": llm.get("retry_count", 0),
                "content_filter_hits": llm.get("content_filter_hits", 0),
                "parse_failure_rate_final": summary.get("parse_failure_rate_final", 0.0),
                "infrastructure_error_route_rate_final": summary.get("infrastructure_error_route_rate_final", 0.0),
            }
        )
    _write_csv(rows, out_dir / "latency_summary.csv")
    (out_dir / "latency_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gamma P3 MiniWoB smoke, paired statistics, and gate helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--run", action="append", default=[], required=True)
    smoke.add_argument("--out-dir", required=True)
    smoke.add_argument("--parse-min", type=float, default=0.95)
    smoke.add_argument("--infrastructure-error-max", type=float, default=0.02)
    smoke.add_argument("--hash-agreement-min", type=float, default=0.95)
    smoke.add_argument("--expected-routes-per-result", type=int, default=8)
    gate = sub.add_parser("gate")
    gate.add_argument("--run", action="append", default=[], required=True)
    gate.add_argument("--intervention", default="consolidated")
    gate.add_argument("--baseline", default="frozen")
    gate.add_argument("--out-dir", required=True)
    gate.add_argument("--t", type=int, default=3)
    gate.add_argument("--n-boot", type=int, default=10_000)
    gate.add_argument("--rng-seed", type=int, default=0)
    latency = sub.add_parser("latency-summary")
    latency.add_argument("--run", action="append", default=[], required=True)
    latency.add_argument("--out-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.cmd == "smoke":
        smoke_report(
            runs=args.run,
            out_dir=Path(args.out_dir),
            parse_min=args.parse_min,
            infrastructure_error_max=args.infrastructure_error_max,
            hash_agreement_min=args.hash_agreement_min,
            expected_routes_per_result=args.expected_routes_per_result,
        )
        return
    if args.cmd == "gate":
        p3_gate_report(
            runs=args.run,
            intervention=args.intervention,
            baseline=args.baseline,
            out_dir=Path(args.out_dir),
            t=args.t,
            n_boot=args.n_boot,
            rng_seed=args.rng_seed,
        )
        return
    if args.cmd == "latency-summary":
        latency_summary(runs=args.run, out_dir=Path(args.out_dir))
        return
    raise ValueError(args.cmd)


if __name__ == "__main__":
    main()
