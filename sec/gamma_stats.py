from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from .maze_stats import PAIRED_METRICS, bootstrap_ci, paired_diff, route_rows


DRIFT_METRICS = ["success", "looped", "cost_ratio", "failure_penalized_steps"]


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_run(raw: str) -> tuple[str, str, Path]:
    if "=" not in raw:
        raise ValueError(f"--run must be condition[:seed]=path, got {raw!r}")
    label, path = raw.split("=", 1)
    if ":" in label:
        condition, seed = label.split(":", 1)
    else:
        condition, seed = label, "0"
    return condition.strip(), seed.strip(), Path(path.strip())


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean_metric(rows: list[dict[str, Any]], metric: str, *, t: int) -> float:
    vals = [float(row[metric]) for row in rows if int(row["t"]) == t and row.get(metric) is not None]
    return float(np.mean(vals)) if vals else 0.0


def drift_probe_report(
    *,
    baseline_result: Path,
    probe_result: Path,
    out_dir: Path,
    t: int = 0,
    n_boot: int = 10000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    baseline_rows = route_rows(_load_json(baseline_result), condition="baseline", seed="0")
    probe_rows = route_rows(_load_json(probe_result), condition="probe", seed="0")
    rows: list[dict[str, Any]] = []
    for metric in DRIFT_METRICS:
        base_vals = [float(row[metric]) for row in baseline_rows if int(row["t"]) == t and row.get(metric) is not None]
        if not base_vals:
            raise ValueError(f"baseline has no values for {metric} at t={t}")
        lo, hi = bootstrap_ci(base_vals, n_boot=n_boot, rng_seed=rng_seed)
        probe_mean = _mean_metric(probe_rows, metric, t=t)
        rows.append(
            {
                "metric": metric,
                "baseline_mean": float(np.mean(base_vals)),
                "baseline_ci_lo": lo,
                "baseline_ci_hi": hi,
                "probe_mean": probe_mean,
                "passed": bool(lo <= probe_mean <= hi),
            }
        )
    passed = all(row["passed"] for row in rows)
    result = {
        "kind": "gamma_drift_probe",
        "baseline_result": str(baseline_result),
        "probe_result": str(probe_result),
        "t": t,
        "passed": passed,
        "metrics": rows,
        "decision": "reuse_e2_controls_allowed" if passed else "rerun_contemporaneous_controls_required",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "drift_probe_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(rows, out_dir / "drift_probe_metrics.csv")
    lines = [
        "# Gamma Drift Probe",
        "",
        f"Decision: **{result['decision']}**",
        "",
        "| metric | baseline mean | bootstrap lo | bootstrap hi | probe mean | pass |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['metric']} | {row['baseline_mean']:.4f} | {row['baseline_ci_lo']:.4f} | "
            f"{row['baseline_ci_hi']:.4f} | {row['probe_mean']:.4f} | {'yes' if row['passed'] else 'no'} |"
        )
    (out_dir / "drift_probe_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def _load_route_rows(runs: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, path = _parse_run(raw)
        rows.extend(route_rows(_load_json(path), condition=condition, seed=seed))
    return rows


def _paired_by_metric(
    rows: list[dict[str, Any]],
    *,
    intervention: str,
    baseline: str,
    t: int,
    n_boot: int,
    rng_seed: int,
) -> dict[str, dict[str, Any]]:
    a = [row for row in rows if row["condition"] == intervention]
    b = [row for row in rows if row["condition"] == baseline]
    return {
        metric: paired_diff(a, b, metric, t=t, n_boot=n_boot, rng_seed=rng_seed)
        for metric in PAIRED_METRICS
    }


def _seed_direction_count(
    rows: list[dict[str, Any]],
    *,
    intervention: str,
    baseline: str,
    metric: str,
    t: int,
    direction: str,
) -> dict[str, Any]:
    seeds = sorted({str(row["seed"]) for row in rows if row["condition"] in {intervention, baseline}})
    diffs: dict[str, float] = {}
    for seed in seeds:
        a = [row for row in rows if row["condition"] == intervention and str(row["seed"]) == seed]
        b = [row for row in rows if row["condition"] == baseline and str(row["seed"]) == seed]
        stat = paired_diff(a, b, metric, t=t, n_boot=500, rng_seed=0)
        diffs[seed] = float(stat["mean_diff"])
    if direction == "negative":
        count = sum(1 for value in diffs.values() if value < 0.0)
    else:
        count = sum(1 for value in diffs.values() if value > 0.0)
    return {"metric": metric, "direction": direction, "count": count, "n": len(diffs), "diffs": diffs}


def gamma_gate_report(
    *,
    kind: str,
    runs: list[str],
    intervention: str,
    baseline: str,
    out_dir: Path,
    t: int,
    n_boot: int = 10000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    rows = _load_route_rows(runs)
    stats = _paired_by_metric(
        rows,
        intervention=intervention,
        baseline=baseline,
        t=t,
        n_boot=n_boot,
        rng_seed=rng_seed,
    )
    decision = "inconclusive"
    checks: dict[str, Any] = {}
    if kind == "rescue":
        success = stats["success"]
        sxs = stats["success_excess_steps"]
        loop = stats["looped"]
        cost = stats["failure_penalized_steps"]
        sxs_improves = bool(sxs["ci_hi"] < 0.0)
        loop_improves = bool(loop["ci_hi"] < 0.0)
        primary_metric = "success_excess_steps" if sxs_improves else "looped"
        seed_dir = _seed_direction_count(
            rows, intervention=intervention, baseline=baseline, metric=primary_metric, t=t, direction="negative"
        )
        checks = {
            "success_noninferior": bool(success["ci_lo"] > -0.05),
            "sxs_improves": sxs_improves,
            "loop_improves": loop_improves,
            "other_endpoint_point_not_worse": bool((sxs_improves and loop["mean_diff"] <= 0.0) or (loop_improves and sxs["mean_diff"] <= 0.0)),
            "failure_penalized_cost_point_not_worse": bool(cost["mean_diff"] <= 0.0),
            "seed_direction": seed_dir,
        }
        min_same = 4 if seed_dir["n"] >= 5 else 2
        passed = (
            checks["success_noninferior"]
            and (sxs_improves or loop_improves)
            and checks["other_endpoint_point_not_worse"]
            and checks["failure_penalized_cost_point_not_worse"]
            and seed_dir["count"] >= min_same
        )
        decision = "rescue_pass" if passed else "rescue_inconclusive_or_fail"
    elif kind == "compression":
        sxs = stats["success_excess_steps"]
        loop = stats["looped"]
        cost = stats["failure_penalized_steps"]
        sxs_worse = bool(sxs["ci_lo"] > 0.0)
        loop_worse = bool(loop["ci_lo"] > 0.0)
        primary_metric = "success_excess_steps" if sxs_worse else "looped"
        seed_dir = _seed_direction_count(
            rows, intervention=intervention, baseline=baseline, metric=primary_metric, t=t, direction="positive"
        )
        min_same = 4 if seed_dir["n"] >= 5 else 2
        checks = {
            "sxs_worse": sxs_worse,
            "loop_worse": loop_worse,
            "failure_penalized_cost_point_worse": bool(cost["mean_diff"] > 0.0),
            "seed_direction": seed_dir,
        }
        passed = (sxs_worse or loop_worse) and checks["failure_penalized_cost_point_worse"] and seed_dir["count"] >= min_same
        decision = "compression_pass" if passed else "compression_inconclusive_or_fail"
    elif kind == "p2":
        sxs = stats["success_excess_steps"]
        loop = stats["looped"]
        seed_dir = _seed_direction_count(
            rows, intervention=intervention, baseline=baseline, metric="success_excess_steps", t=t, direction="positive"
        )
        checks = {
            "sxs_worse_ci": bool(sxs["ci_lo"] > 0.0),
            "loop_worse_ci": bool(loop["ci_lo"] > 0.0),
            "seed_direction": seed_dir,
        }
        passed = checks["sxs_worse_ci"] and checks["loop_worse_ci"] and seed_dir["count"] == seed_dir["n"] and seed_dir["n"] >= 3
        decision = "p2_phenomenon_pass" if passed else "p2_not_detected_or_underpowered"
    elif kind == "delta":
        cost = stats["failure_penalized_steps"]
        loop = stats["looped"]
        cost_seed_dir = _seed_direction_count(
            rows, intervention=intervention, baseline=baseline, metric="failure_penalized_steps", t=t, direction="positive"
        )
        loop_seed_dir = _seed_direction_count(
            rows, intervention=intervention, baseline=baseline, metric="looped", t=t, direction="positive"
        )
        checks = {
            "failure_penalized_steps_worse_ci": bool(cost["ci_lo"] > 0.0),
            "looped_worse_ci": bool(loop["ci_lo"] > 0.0),
            "failure_penalized_steps_seed_direction": cost_seed_dir,
            "looped_seed_direction": loop_seed_dir,
        }
        passed = (
            checks["failure_penalized_steps_worse_ci"]
            and checks["looped_worse_ci"]
            and cost_seed_dir["count"] >= 2
            and loop_seed_dir["count"] >= 2
        )
        decision = "delta_maze_phenomenon_positive" if passed else "delta_not_detected_or_underpowered"
    else:
        raise ValueError(f"unknown gate kind {kind!r}")

    result = {
        "kind": kind,
        "intervention": intervention,
        "baseline": baseline,
        "t": t,
        "decision": decision,
        "checks": checks,
        "paired_stats": stats,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{kind}_gate_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv([{**{"metric": metric}, **stat} for metric, stat in stats.items()], out_dir / f"{kind}_paired_stats.csv")
    lines = [
        f"# Gamma {kind.title()} Gate",
        "",
        f"Decision: **{decision}**",
        "",
        "| metric | mean diff | ci lo | ci hi | n pairs | excludes zero |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for metric, stat in stats.items():
        lines.append(
            f"| {metric} | {stat['mean_diff']:.4f} | {stat['ci_lo']:.4f} | "
            f"{stat['ci_hi']:.4f} | {stat['n_pairs']} | {'yes' if stat['ci_excludes_zero'] else 'no'} |"
        )
    lines.extend(["", "## Checks", "", "```json", json.dumps(checks, ensure_ascii=False, indent=2), "```"])
    (out_dir / f"{kind}_gate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def latency_summary(*, runs: list[str], out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, path = _parse_run(raw)
        result = _load_json(path)
        summary = result.get("summary", {})
        llm = summary.get("llm", {})
        rows.append(
            {
                "condition": condition,
                "seed": seed,
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
                "parse_failure_count_final": summary.get("parse_failure_count_final", 0.0),
            }
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, out_dir / "latency_summary.csv")
    (out_dir / "latency_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def _result_audit(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _load_json(path)
    audit = data.get("memory_audit", data)
    if not isinstance(audit, dict):
        raise ValueError(f"missing memory audit in {path}")
    summary = data.get("summary", {}) if isinstance(data.get("summary", {}), dict) else {}
    return audit, summary


def _final_pool_state(audit: dict[str, Any], *, t: int | None = None) -> dict[str, Any]:
    trajectory = list(audit.get("pool_trajectory", []))
    if not trajectory:
        return {}
    if t is None:
        return max(trajectory, key=lambda row: int(row.get("t", -1)))
    matches = [row for row in trajectory if int(row.get("t", -1)) == t]
    return matches[-1] if matches else {}


def _distinct_injected_through_t(
    audit: dict[str, Any],
    *,
    t: int | None,
) -> dict[str, int]:
    retrievals = list(audit.get("retrievals", []))
    if t is None:
        t = max((int(rec.get("t", -1)) for rec in retrievals), default=-1)
    active_ids: set[str] = set()
    archive_ids: set[str] = set()
    for rec in retrievals:
        if int(rec.get("t", -1)) > t:
            continue
        items = list(rec.get("items", []))
        sources = list(rec.get("sources", ["active"] * len(items)))
        for item_id, source in zip(items, sources, strict=False):
            if source == "archive":
                archive_ids.add(str(item_id))
            else:
                active_ids.add(str(item_id))
    return {
        "t": t,
        "active": len(active_ids),
        "archive": len(archive_ids),
        "total": len(active_ids | archive_ids),
    }


def retrieval_audit_report(
    *,
    mode: str,
    runs: list[str],
    out_dir: Path,
    baseline_runs: list[str] | None = None,
    t: int | None = None,
    expected_limit: int = 6,
    distinct_ratio_min: float = 1.5,
) -> dict[str, Any]:
    if mode not in {"smoke", "formal"}:
        raise ValueError(f"unknown retrieval audit mode {mode!r}")
    rows: list[dict[str, Any]] = []
    for raw in runs:
        condition, seed, path = _parse_run(raw)
        audit, summary = _result_audit(path)
        retrievals = list(audit.get("retrievals", []))
        violations = []
        for rec in retrievals:
            total = int(rec.get("injected_count", len(rec.get("items", []))))
            active = int(rec.get("active_injected", 0))
            archive = int(rec.get("archive_injected", 0))
            limit = int(rec.get("configured_total_limit", total))
            if (
                not bool(rec.get("dose_compliant", total <= limit))
                or active + archive != total
                or total > limit
                or limit > expected_limit
            ):
                violations.append(rec)
        archive_available = [
            rec for rec in retrievals if int(rec.get("archive_candidate_count", 0)) > 0
        ]
        archive_selected = [
            rec for rec in archive_available if int(rec.get("archive_injected", 0)) > 0
        ]
        distinct = _distinct_injected_through_t(audit, t=t)
        rows.append(
            {
                "condition": condition,
                "seed": seed,
                "path": str(path),
                "retrieval_records": len(retrievals),
                "max_injected": max(
                    (int(rec.get("injected_count", len(rec.get("items", [])))) for rec in retrievals),
                    default=0,
                ),
                "dose_violation_count": len(violations),
                "all_joint_rank": bool(retrievals) and all(rec.get("joint_rank") is True for rec in retrievals),
                "archive_available_records": len(archive_available),
                "archive_selected_records": len(archive_selected),
                "archive_selected_when_available": bool(archive_available) and bool(archive_selected),
                "parse_failure_rate_final": float(summary.get("parse_failure_rate_final", 0.0)),
                "final_t": distinct["t"],
                "distinct_scope": "cumulative_through_t",
                "distinct_active_injected": distinct["active"],
                "distinct_archive_injected": distinct["archive"],
                "distinct_total_injected": distinct["total"],
            }
        )

    baseline_by_seed: dict[str, int] = {}
    for raw in baseline_runs or []:
        _, seed, path = _parse_run(raw)
        audit, _ = _result_audit(path)
        baseline_by_seed[seed] = _distinct_injected_through_t(audit, t=t)["total"]
    for row in rows:
        baseline_distinct = baseline_by_seed.get(str(row["seed"]))
        row["baseline_distinct_injected"] = baseline_distinct
        row["distinct_ratio_vs_baseline"] = (
            float(row["distinct_total_injected"]) / baseline_distinct
            if baseline_distinct and baseline_distinct > 0
            else None
        )
        row["distinct_ratio_pass"] = bool(
            row["distinct_ratio_vs_baseline"] is not None
            and float(row["distinct_ratio_vs_baseline"]) >= distinct_ratio_min
        )

    dose_pass = bool(rows) and all(
        int(row["dose_violation_count"]) == 0 and int(row["max_injected"]) <= expected_limit
        for row in rows
    )
    joint_rank_pass = bool(rows) and all(bool(row["all_joint_rank"]) for row in rows)
    archive_access_pass = bool(rows) and all(
        bool(row["archive_selected_when_available"]) for row in rows
    )
    parse_pass = bool(rows) and all(
        float(row["parse_failure_rate_final"]) < 0.05 for row in rows
    )
    ratio_count = sum(1 for row in rows if bool(row["distinct_ratio_pass"]))
    ratio_required = 2 if len(rows) >= 3 else len(rows)
    distinct_ratio_pass = mode == "smoke" or (
        bool(rows) and ratio_count >= ratio_required
    )
    passed = dose_pass and joint_rank_pass and archive_access_pass and parse_pass and distinct_ratio_pass
    if passed:
        decision = "smoke_pass" if mode == "smoke" else "manipulation_pass"
    elif not dose_pass or not joint_rank_pass:
        decision = "invalid_dose_or_ranking"
    elif not archive_access_pass:
        decision = (
            "archive_ranking_inaccessible_in_smoke"
            if mode == "smoke"
            else "ranking_inaccessible_not_evaluable"
        )
    elif not parse_pass:
        decision = "parse_gate_fail"
    else:
        decision = "ranking_inaccessible_not_evaluable"

    checks = {
        "dose_pass": dose_pass,
        "joint_rank_pass": joint_rank_pass,
        "archive_access_pass": archive_access_pass,
        "parse_pass": parse_pass,
        "distinct_ratio_pass": distinct_ratio_pass,
        "distinct_ratio_count": ratio_count,
        "distinct_ratio_required": ratio_required,
        "expected_limit": expected_limit,
        "distinct_ratio_min": distinct_ratio_min,
    }
    result = {
        "kind": "gamma_retrieval_audit",
        "mode": mode,
        "decision": decision,
        "passed": passed,
        "t": t,
        "checks": checks,
        "runs": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "retrieval_audit_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(rows, out_dir / "retrieval_audit_runs.csv")
    lines = [
        f"# Gamma Retrieval Audit ({mode})",
        "",
        f"Decision: **{decision}**",
        "",
        "| seed | max injected | violations | joint rank | archive selected | parse fail | distinct total | baseline | ratio |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        ratio = row["distinct_ratio_vs_baseline"]
        ratio_text = f"{ratio:.3f}" if ratio is not None else "-"
        lines.append(
            f"| {row['seed']} | {row['max_injected']} | {row['dose_violation_count']} | "
            f"{'yes' if row['all_joint_rank'] else 'no'} | "
            f"{'yes' if row['archive_selected_when_available'] else 'no'} | "
            f"{row['parse_failure_rate_final']:.4f} | {row['distinct_total_injected']} | "
            f"{row['baseline_distinct_injected'] if row['baseline_distinct_injected'] is not None else '-'} | "
            f"{ratio_text} |"
        )
    lines.extend(["", "## Checks", "", "```json", json.dumps(checks, ensure_ascii=False, indent=2), "```"])
    (out_dir / "retrieval_audit_report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return result


def model_smoke_report(
    *,
    result_path: Path,
    out_dir: Path,
    expected_routes: int = 48,
    success_min: float = 0.25,
    success_max: float = 0.85,
    parse_min: float = 0.95,
    error_rate_max: float = 0.01,
) -> dict[str, Any]:
    data = _load_json(result_path)
    heldout = list(data.get("heldout_records", []))
    if not heldout:
        raise ValueError(f"no heldout records in {result_path}")
    final = max(heldout, key=lambda row: int(row.get("t", -1)))
    routes = [
        agent.get("route", {})
        for episode in final.get("episodes", [])
        for agent in episode.get("agents", [])
    ]
    route_count = len(routes)
    success = float(np.mean([bool(route.get("success")) for route in routes])) if routes else 0.0
    parse_failure_rate = (
        float(np.mean([float(route.get("parse_failure_rate", 0.0)) for route in routes]))
        if routes
        else 1.0
    )
    parse_rate = 1.0 - parse_failure_rate
    total_steps = sum(max(int(route.get("steps", 0)), 0) for route in routes)
    llm_error_count = sum(max(int(route.get("llm_error_count", 0)), 0) for route in routes)
    llm_error_rate = llm_error_count / max(total_steps, 1)
    config = data.get("config", {})
    summary = data.get("summary", {})
    llm = summary.get("llm", {})
    checks = {
        "route_count_pass": route_count == expected_routes,
        "success_calibrated": success_min <= success <= success_max,
        "parse_pass": parse_rate >= parse_min,
        "llm_error_pass": llm_error_rate <= error_rate_max,
    }
    passed = all(checks.values())
    max_tokens = int(config.get("max_tokens_solver", 0))
    if passed:
        decision = "smoke_pass"
    elif checks["route_count_pass"] and checks["success_calibrated"] and not checks["parse_pass"] and max_tokens < 512:
        decision = "retry_with_512"
    else:
        decision = "model_not_evaluable"
    result = {
        "kind": "gamma_model_smoke",
        "decision": decision,
        "passed": passed,
        "result_path": str(result_path),
        "model": config.get("model", ""),
        "max_tokens_solver": max_tokens,
        "metrics": {
            "route_count": route_count,
            "success": success,
            "parse_rate": parse_rate,
            "parse_failure_rate": parse_failure_rate,
            "llm_error_count": llm_error_count,
            "total_route_steps": total_steps,
            "llm_error_rate": llm_error_rate,
            "network_calls": int(llm.get("network_calls", 0)),
            "retry_count": int(llm.get("retry_count", 0)),
            "content_filter_hits": int(llm.get("content_filter_hits", 0)),
            "latency_p50_sec": float(llm.get("latency_p50_sec", 0.0)),
            "latency_p95_sec": float(llm.get("latency_p95_sec", 0.0)),
        },
        "thresholds": {
            "expected_routes": expected_routes,
            "success_min": success_min,
            "success_max": success_max,
            "parse_min": parse_min,
            "error_rate_max": error_rate_max,
        },
        "checks": checks,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model_smoke_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metrics = result["metrics"]
    lines = [
        "# Gamma P2 Model Smoke",
        "",
        f"Decision: **{decision}**",
        "",
        f"- model: `{result['model']}`",
        f"- max_tokens_solver: {max_tokens}",
        f"- routes: {metrics['route_count']} / {expected_routes}",
        f"- success: {metrics['success']:.4f}",
        f"- action parse rate: {metrics['parse_rate']:.4f}",
        f"- exhausted-call error rate: {metrics['llm_error_rate']:.6f}",
        f"- latency p50/p95: {metrics['latency_p50_sec']:.3f}s / {metrics['latency_p95_sec']:.3f}s",
        f"- retries/content filters: {metrics['retry_count']} / {metrics['content_filter_hits']}",
        "",
        "## Checks",
        "",
        "```json",
        json.dumps(checks, ensure_ascii=False, indent=2),
        "```",
    ]
    (out_dir / "model_smoke_report.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gamma preregistered drift/gate/audit helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    drift = sub.add_parser("drift-probe")
    drift.add_argument("--baseline-result", required=True)
    drift.add_argument("--probe-result", required=True)
    drift.add_argument("--out-dir", required=True)
    drift.add_argument("--t", type=int, default=0)
    drift.add_argument("--n-boot", type=int, default=10000)
    gate = sub.add_parser("gate")
    gate.add_argument("--kind", choices=["rescue", "compression", "p2", "delta"], required=True)
    gate.add_argument("--run", action="append", default=[], required=True)
    gate.add_argument("--intervention", required=True)
    gate.add_argument("--baseline", required=True)
    gate.add_argument("--out-dir", required=True)
    gate.add_argument("--t", type=int, default=-1)
    gate.add_argument("--n-boot", type=int, default=10000)
    audit = sub.add_parser("latency-summary")
    audit.add_argument("--run", action="append", default=[], required=True)
    audit.add_argument("--out-dir", required=True)
    retrieval = sub.add_parser("retrieval-audit")
    retrieval.add_argument("--mode", choices=["smoke", "formal"], required=True)
    retrieval.add_argument("--run", action="append", default=[], required=True)
    retrieval.add_argument("--baseline-run", action="append", default=[])
    retrieval.add_argument("--out-dir", required=True)
    retrieval.add_argument("--t", type=int, default=-1)
    retrieval.add_argument("--expected-limit", type=int, default=6)
    retrieval.add_argument("--distinct-ratio-min", type=float, default=1.5)
    smoke = sub.add_parser("model-smoke")
    smoke.add_argument("--result", required=True)
    smoke.add_argument("--out-dir", required=True)
    smoke.add_argument("--expected-routes", type=int, default=48)
    smoke.add_argument("--success-min", type=float, default=0.25)
    smoke.add_argument("--success-max", type=float, default=0.85)
    smoke.add_argument("--parse-min", type=float, default=0.95)
    smoke.add_argument("--error-rate-max", type=float, default=0.01)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.cmd == "drift-probe":
        drift_probe_report(
            baseline_result=Path(args.baseline_result),
            probe_result=Path(args.probe_result),
            out_dir=Path(args.out_dir),
            t=args.t,
            n_boot=args.n_boot,
        )
        return
    if args.cmd == "gate":
        t = args.t
        if t < 0:
            rows = _load_route_rows(args.run)
            t = max(int(row["t"]) for row in rows)
        gamma_gate_report(
            kind=args.kind,
            runs=args.run,
            intervention=args.intervention,
            baseline=args.baseline,
            out_dir=Path(args.out_dir),
            t=t,
            n_boot=args.n_boot,
        )
        return
    if args.cmd == "latency-summary":
        latency_summary(runs=args.run, out_dir=Path(args.out_dir))
        return
    if args.cmd == "retrieval-audit":
        retrieval_audit_report(
            mode=args.mode,
            runs=args.run,
            baseline_runs=args.baseline_run,
            out_dir=Path(args.out_dir),
            t=None if args.t < 0 else args.t,
            expected_limit=args.expected_limit,
            distinct_ratio_min=args.distinct_ratio_min,
        )
        return
    if args.cmd == "model-smoke":
        model_smoke_report(
            result_path=Path(args.result),
            out_dir=Path(args.out_dir),
            expected_routes=args.expected_routes,
            success_min=args.success_min,
            success_max=args.success_max,
            parse_min=args.parse_min,
            error_rate_max=args.error_rate_max,
        )
        return
    raise ValueError(args.cmd)


if __name__ == "__main__":
    main()
