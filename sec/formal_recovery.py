from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CHECKPOINT = "formal_provider_freeze_checkpoint_20260715.json"
DEFAULT_PROBE_REPORT = (
    "runs_provider_freeze_audit/20260715_81006/provider_probe_latest.json"
)
EXPECTED_COMPLETED = {
    "epsilon": 9,
    "p3": 17,
}
INTERRUPTED_TARGETS = {
    "epsilon": (
        "runs_maze_epsilon_controls/"
        "n4_gt_false_seed1_epsilon_shared_consolidated_mmr"
    ),
    "p3": (
        "runs_miniwob_gamma_p3e/"
        "n4_gt_false_seed2_gamma_p3_choose_list_shared_consolidated_expel"
    ),
}
SOURCE_FREEZES = [
    "epsilon_runtime_source.freeze.json",
    "p3e_runtime_source.freeze.json",
]
RECOVERY_SOURCES = [
    "sec/formal_recovery.py",
    "sec/resume_p3e_target.py",
    "scripts/resume_formal_after_provider_unfreeze.ps1",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _relative(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _completed_run_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return sorted(
        path.parent
        for path in runs_dir.glob("*/result.json")
        if path.is_file()
    )


def _file_records(run_dirs: list[Path], root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
            records.append(
                {
                    "path": _relative(path, root),
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    return records


def _freeze_report(path: Path, root: Path) -> dict[str, Any]:
    payload = _load_json(path)
    files: list[dict[str, Any]] = []
    for row in payload.get("files", []):
        source = root / str(row.get("path", ""))
        expected = str(row.get("sha256", ""))
        actual = _sha256(source) if source.exists() else ""
        files.append(
            {
                "path": _relative(source, root) if source.exists() else str(source),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "match": bool(expected and actual == expected),
            }
        )
    return {
        "path": _relative(path, root),
        "sha256": _sha256(path),
        "embedded_files": files,
        "all_match": bool(files) and all(row["match"] for row in files),
    }


def _partial_provider_evidence(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "llm_error_count": 0,
            "provider_error_codes": {},
        }
    payload = _load_json(path)
    errors = list(payload.get("audit", {}).get("llm_errors", []))
    codes: dict[str, int] = {}
    tags: dict[str, int] = {}
    for event in errors:
        message = str(event.get("message", ""))
        match = re.search(r"ModelArts\.([0-9]+)", message)
        code = match.group(1) if match else "unclassified"
        codes[code] = codes.get(code, 0) + 1
        tag = str(event.get("tag", "unknown"))
        tags[tag] = tags.get(tag, 0) + 1
    return {
        "path": str(path).replace("\\", "/"),
        "exists": True,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "llm_error_count": len(errors),
        "provider_error_codes": dict(sorted(codes.items())),
        "llm_error_tags": dict(sorted(tags.items())),
    }


def build_checkpoint(
    *,
    root: Path,
    epsilon_dir: Path,
    p3_dir: Path,
    out_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    suite_dirs = {
        "epsilon": (root / epsilon_dir).resolve(),
        "p3": (root / p3_dir).resolve(),
    }
    suites: dict[str, Any] = {}
    for name, runs_dir in suite_dirs.items():
        completed = _completed_run_dirs(runs_dir)
        expected = EXPECTED_COMPLETED[name]
        if len(completed) != expected:
            raise RuntimeError(
                f"{name} checkpoint requires {expected} completed runs, "
                f"found {len(completed)}"
            )
        target = (root / INTERRUPTED_TARGETS[name]).resolve()
        if (target / "result.json").exists():
            raise RuntimeError(
                f"Interrupted target already has result.json and cannot be "
                f"checkpointed as partial: {target}"
            )
        suites[name] = {
            "runs_dir": _relative(runs_dir, root),
            "completed_run_count": len(completed),
            "completed_run_dirs": [_relative(path, root) for path in completed],
            "completed_files": _file_records(completed, root),
            "interrupted_target": _relative(target, root),
            "interrupted_partial": _partial_provider_evidence(
                target / "partial.json"
            ),
        }

    freeze_reports = [
        _freeze_report((root / path).resolve(), root)
        for path in SOURCE_FREEZES
    ]
    if not all(report["all_match"] for report in freeze_reports):
        raise RuntimeError("Frozen runtime-source hashes do not match.")

    recovery_sources: list[dict[str, Any]] = []
    for raw in RECOVERY_SOURCES:
        path = (root / raw).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        recovery_sources.append(
            {
                "path": _relative(path, root),
                "sha256": _sha256(path),
            }
        )

    result = {
        "status": "formal_runs_paused_provider_resource_frozen",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "provider_error": {
            "http_status": 403,
            "code": "ModelArts.81006",
            "message": "The resource is frozen.",
            "first_confirmed_local_date": "2026-07-15",
        },
        "suites": suites,
        "source_freezes": freeze_reports,
        "recovery_sources": recovery_sources,
        "recovery_policy": {
            "completed_artifacts_must_remain_byte_identical": True,
            "interrupted_targets_must_be_rerun_from_round_zero": True,
            "remaining_matrix_blocks_must_exclude_completed_configs": True,
            "provider_probe_must_pass_before_resume": True,
            "target_quality_must_pass_before_remaining_blocks": True,
        },
    }
    _write_json(out_path, result)
    return result


def verify_checkpoint(*, root: Path, checkpoint_path: Path) -> dict[str, Any]:
    root = root.resolve()
    checkpoint = _load_json(checkpoint_path)
    failures: list[str] = []

    for suite_name, suite in checkpoint.get("suites", {}).items():
        runs_dir = (root / str(suite.get("runs_dir", ""))).resolve()
        current_count = len(_completed_run_dirs(runs_dir))
        checkpoint_count = int(suite.get("completed_run_count", -1))
        if current_count < checkpoint_count:
            failures.append(
                f"{suite_name}: completed count regressed "
                f"{current_count} < {checkpoint_count}"
            )
        for record in suite.get("completed_files", []):
            path = (root / str(record.get("path", ""))).resolve()
            if not path.exists():
                failures.append(f"{suite_name}: missing {path}")
                continue
            if _sha256(path) != str(record.get("sha256", "")):
                failures.append(f"{suite_name}: hash mismatch {path}")

    for record in checkpoint.get("source_freezes", []):
        path = (root / str(record.get("path", ""))).resolve()
        if not path.exists() or _sha256(path) != str(record.get("sha256", "")):
            failures.append(f"source freeze changed: {path}")
        if path.exists():
            current = _freeze_report(path, root)
            if not current["all_match"]:
                failures.append(f"embedded runtime source changed: {path}")

    for record in checkpoint.get("recovery_sources", []):
        path = (root / str(record.get("path", ""))).resolve()
        if not path.exists() or _sha256(path) != str(record.get("sha256", "")):
            failures.append(f"recovery source changed: {path}")

    result = {
        "status": "checkpoint_verified" if not failures else "checkpoint_failed",
        "checkpoint": str(checkpoint_path),
        "failure_count": len(failures),
        "failures": failures,
    }
    return result


async def _provider_probe(
    *,
    model: str,
    base_url: str,
    api_key_env: str,
    timeout_sec: float,
) -> dict[str, Any]:
    from .config import Config
    from .llm import LLMClient

    cfg = Config(
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        cache_policy="off",
        cache_dir="tmp/provider_recovery_probe_cache",
        concurrency=1,
        max_retries=1,
        request_timeout_sec=timeout_sec,
    )
    client = LLMClient(cfg)
    started = time.monotonic()
    try:
        text = await client.chat(
            [{"role": "user", "content": "Reply with exactly OK."}],
            temp=0.0,
            max_tokens=8,
            tag="provider_recovery_probe",
            cache_salt=f"provider-recovery-{time.time_ns()}",
        )
        return {
            "status": "provider_probe_pass",
            "response_nonempty": bool(text.strip()),
            "latency_sec": time.monotonic() - started,
            "error_code": "",
            "error_message": "",
        }
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        match = re.search(r"ModelArts\.([0-9]+)", message)
        return {
            "status": "provider_probe_failed",
            "response_nonempty": False,
            "latency_sec": time.monotonic() - started,
            "error_code": f"ModelArts.{match.group(1)}" if match else "",
            "error_message": message[:800],
        }
    finally:
        await client.client.close()


def probe_provider(
    *,
    model: str,
    base_url: str,
    api_key_env: str,
    timeout_sec: float,
    out_path: Path,
) -> dict[str, Any]:
    result = asyncio.run(
        _provider_probe(
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            timeout_sec=timeout_sec,
        )
    )
    result["created_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    result["model"] = model
    result["base_url"] = base_url
    _write_json(out_path, result)
    return result


def validate_target(*, suite: str, result_path: Path) -> dict[str, Any]:
    if not result_path.exists():
        return {
            "status": "target_quality_failed",
            "suite": suite,
            "result_path": str(result_path),
            "failures": ["result.json is missing"],
        }

    if suite == "epsilon":
        from .epsilon_evidence import _quality_rows

        result = _load_json(result_path)
        config = result.get("config", {})
        arm = str(config.get("run_id", ""))
        seed = int(config.get("seed", -1))
        if not arm.startswith("epsilon_") or seed < 0:
            raise ValueError(
                f"Cannot infer Epsilon arm/seed from {result_path}: "
                f"run_id={arm!r}, seed={seed}"
            )
        row = _quality_rows(
            {(arm, seed): result},
            suite="controls",
            result_paths={(arm, seed): result_path},
        )[0]
        checks = {
            "terminal_round": bool(row["terminal_round_pass"]),
            "route_count": bool(row["route_count_pass"]),
            "configuration": bool(row["configuration_pass"]),
            "manifest": bool(row["manifest_pass"]),
            "no_exhausted_calls": int(row["exhausted_llm_call_count"]) == 0,
            "no_route_llm_errors": (
                int(row["route_llm_error_count_all_rounds"]) == 0
            ),
            "no_parse_failures": (
                int(row["parse_failure_count_all_rounds"]) == 0
            ),
        }
        diagnostics = {
            "condition": row["condition"],
            "seed": row["seed"],
            "terminal_t": row["terminal_t"],
            "expected_terminal_t": row["expected_terminal_t"],
            "route_count_final": row["route_count_final"],
            "expected_route_count_final": row["expected_route_count_final"],
            "exhausted_llm_call_count": row["exhausted_llm_call_count"],
            "route_llm_error_count_all_rounds": (
                row["route_llm_error_count_all_rounds"]
            ),
            "parse_failure_count_all_rounds": (
                row["parse_failure_count_all_rounds"]
            ),
        }
    elif suite == "p3":
        from .miniwob_stats import formal_quality_report

        result = _load_json(result_path)
        config = result.get("config", {})
        notes = list(config.get("notes", []))
        condition = str(notes[0]) if notes else ""
        seed = str(config.get("seed", ""))
        family = str(result.get("task_family", ""))
        if condition not in {"frozen", "append", "consolidated"}:
            raise ValueError(
                f"Cannot infer P3 arm from {result_path}: {condition!r}"
            )
        run = f"{condition}:{seed}:{family}={result_path}"
        quality = formal_quality_report(
            runs=[run],
            require_complete_matrix=False,
        )
        detail = quality.get("runs", [{}])[0]
        checks = {
            "single_run_quality_clear": quality.get("status") == "quality_clear",
            "route_count": bool(detail.get("route_count_pass")),
            "configuration": bool(detail.get("configuration_pass")),
            "manifest": bool(detail.get("manifest_pass")),
            "environment": bool(detail.get("environment_consistency_pass")),
            "llm_behavioral_path": bool(
                detail.get("llm_behavioral_path_pass")
            ),
            "no_infrastructure_errors": bool(
                detail.get("infrastructure_pass")
            ),
            "reviewer_schema": bool(
                detail.get("reviewer_summary_schema_pass")
            ),
        }
        diagnostics = {
            "condition": detail.get("condition"),
            "seed": detail.get("seed"),
            "family": detail.get("family"),
            "route_count": detail.get("route_count"),
            "expected_routes": detail.get("expected_routes"),
            "exhausted_llm_call_count": detail.get(
                "exhausted_llm_call_count"
            ),
            "route_llm_error_count_all_rounds": detail.get(
                "route_llm_error_count_all_rounds"
            ),
            "audit_llm_error_count": detail.get("audit_llm_error_count"),
        }
    else:
        raise ValueError(f"unknown suite: {suite}")

    failures = [name for name, passed in checks.items() if not passed]
    return {
        "status": (
            "target_quality_clear" if not failures else "target_quality_failed"
        ),
        "suite": suite,
        "result_path": str(result_path),
        "result_sha256": _sha256(result_path),
        "checks": checks,
        "diagnostics": diagnostics,
        "failures": failures,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Checkpoint, probe, and verify recovery from a provider outage."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--root", default=".")
    checkpoint.add_argument(
        "--epsilon-dir",
        default="runs_maze_epsilon_controls",
    )
    checkpoint.add_argument(
        "--p3-dir",
        default="runs_miniwob_gamma_p3e",
    )
    checkpoint.add_argument("--out", default=DEFAULT_CHECKPOINT)

    verify = sub.add_parser("verify")
    verify.add_argument("--root", default=".")
    verify.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    verify.add_argument("--out", default="")

    probe = sub.add_parser("probe")
    probe.add_argument("--model", default="DeepSeek-V3")
    probe.add_argument(
        "--base-url",
        default="https://api.modelarts-maas.com/v2",
    )
    probe.add_argument("--api-key-env", default="MODELARTS_MAAS_KEY")
    probe.add_argument("--timeout-sec", type=float, default=15.0)
    probe.add_argument("--out", default=DEFAULT_PROBE_REPORT)

    target = sub.add_parser("validate-target")
    target.add_argument("--suite", choices=["epsilon", "p3"], required=True)
    target.add_argument("--result", required=True)
    target.add_argument("--out", default="")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    if args.command == "checkpoint":
        result = build_checkpoint(
            root=Path(args.root),
            epsilon_dir=Path(args.epsilon_dir),
            p3_dir=Path(args.p3_dir),
            out_path=Path(args.out),
        )
    elif args.command == "verify":
        result = verify_checkpoint(
            root=Path(args.root),
            checkpoint_path=Path(args.checkpoint),
        )
        if args.out:
            _write_json(Path(args.out), result)
    elif args.command == "probe":
        result = probe_provider(
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            timeout_sec=args.timeout_sec,
            out_path=Path(args.out),
        )
    elif args.command == "validate-target":
        result = validate_target(
            suite=args.suite,
            result_path=Path(args.result),
        )
        if args.out:
            _write_json(Path(args.out), result)
    else:
        raise AssertionError(args.command)

    print(result["status"])
    if result["status"] in {
        "checkpoint_failed",
        "provider_probe_failed",
        "target_quality_failed",
    }:
        raise SystemExit(2)
    return result


if __name__ == "__main__":
    main()
