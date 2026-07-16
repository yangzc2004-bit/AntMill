from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .epsilon_evidence import (
    EPSILON_COMMON_CONFIG,
    PRIMARY_METRICS,
    _config_mismatches,
    _epsilon_manifest_check,
    _expected_epsilon_config,
    _memory_rows,
    _quality_rows,
)
from .epsilon_yoke import (
    ROUNDS,
    SEEDS,
    SOURCE_RUN_ID,
    YOKE_SCHEDULE_NAME,
    ZETA_RUN_ID,
    verify_schedule,
)
from .maze_stats import PAIRED_METRICS, hierarchical_paired_diff, per_seed_paired_effects, route_rows


CONTRAST = "zeta_exact_yoke_minus_epsilon_shared_consolidated"
ZETA_PREREGISTRATION = "prereg_phase_zeta.md"


def _expected_zeta_config(*, seed: int) -> dict[str, Any]:
    return {
        **EPSILON_COMMON_CONFIG,
        "seed": seed,
        "run_id": ZETA_RUN_ID,
        "notes": [],
        "memory_mode": "shared",
        "memory_write_protocol": "append",
        "retrieval_scoring": "ga",
        "ga_lambda": 0.0,
        "ga_recency": 0.0,
        "memory_read_protocol": "budgeted_append",
        "budget_schedule_name": YOKE_SCHEDULE_NAME,
        "concurrency": 8,
        "out_dir": "runs_maze_zeta_exact_yoke",
        "cache_dir": "cache_maze_zeta_exact_yoke",
    }


def _zeta_manifest_check(
    *,
    result_path: Path,
    result_config: dict[str, Any],
    seed: int,
    schedule: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    manifest_path = result_path.parent / "manifest.json"
    source = {
        "condition": ZETA_RUN_ID,
        "seed": seed,
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
    expected_yoke = {
        "schedule_sha256": schedule["schedule_sha256"],
        "source_arm": SOURCE_RUN_ID,
        "target_sizes": [int(value) for value in schedule["seeds"][str(seed)]],
        "target_definition": schedule["target_definition"],
        "preregistration": schedule["verified_preregistration"],
    }
    mismatches = _config_mismatches(
        manifest,
        {
            "condition": f"n4_gt_false_seed{seed}_{ZETA_RUN_ID}",
            "run_id": ZETA_RUN_ID,
            "seed": seed,
            "config": result_config,
            "preregistration": ZETA_PREREGISTRATION,
            "zeta_exact_supply_yoke": expected_yoke,
        },
    )
    return not mismatches, mismatches, source


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def build_zeta_evidence(
    *,
    controls_dir: Path,
    zeta_dir: Path,
    schedule_path: Path,
    out_dir: Path,
    n_boot: int = 10_000,
    rng_seed: int = 0,
) -> dict[str, Any]:
    schedule = verify_schedule(schedule_path)
    results: dict[tuple[str, int], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    manipulation: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    source_manifests: list[dict[str, Any]] = []
    for seed in SEEDS:
        baseline_path = controls_dir / f"n4_gt_false_seed{seed}_{SOURCE_RUN_ID}" / "result.json"
        zeta_path = zeta_dir / f"n4_gt_false_seed{seed}_{ZETA_RUN_ID}" / "result.json"
        if not baseline_path.exists() or not zeta_path.exists():
            raise FileNotFoundError(f"Missing Zeta contrast artifacts for seed {seed}.")
        baseline = _load_json(baseline_path)
        zeta = _load_json(zeta_path)
        results[(SOURCE_RUN_ID, seed)] = baseline
        results[(ZETA_RUN_ID, seed)] = zeta
        rows.extend(route_rows(baseline, condition=SOURCE_RUN_ID, seed=str(seed)))
        rows.extend(route_rows(zeta, condition=ZETA_RUN_ID, seed=str(seed)))
        source_results.extend(
            [
                {
                    "condition": SOURCE_RUN_ID,
                    "seed": seed,
                    "path": str(baseline_path),
                    "sha256": _sha256(baseline_path),
                },
                {
                    "condition": ZETA_RUN_ID,
                    "seed": seed,
                    "path": str(zeta_path),
                    "sha256": _sha256(zeta_path),
                },
            ]
        )
        baseline_manifest_pass, baseline_manifest_mismatches, baseline_manifest = (
            _epsilon_manifest_check(
                result_path=baseline_path,
                result_config=baseline.get("config", {}),
                arm=SOURCE_RUN_ID,
                seed=seed,
            )
        )
        zeta_manifest_pass, zeta_manifest_mismatches, zeta_manifest = (
            _zeta_manifest_check(
                result_path=zeta_path,
                result_config=zeta.get("config", {}),
                seed=seed,
                schedule=schedule,
            )
        )
        source_manifests.extend(
            [
                {
                    "condition": SOURCE_RUN_ID,
                    "seed": seed,
                    **baseline_manifest,
                },
                zeta_manifest,
            ]
        )
        baseline_config_mismatches = _config_mismatches(
            baseline.get("config", {}),
            _expected_epsilon_config(
                suite="controls",
                arm=SOURCE_RUN_ID,
                seed=seed,
            ),
        )
        zeta_config_mismatches = _config_mismatches(
            zeta.get("config", {}),
            _expected_zeta_config(seed=seed),
        )
        baseline["_zeta_evidence_configuration"] = {
            "pass": not baseline_config_mismatches,
            "mismatches": baseline_config_mismatches,
            "manifest_pass": baseline_manifest_pass,
            "manifest_mismatches": baseline_manifest_mismatches,
        }
        zeta["_zeta_evidence_configuration"] = {
            "pass": not zeta_config_mismatches,
            "mismatches": zeta_config_mismatches,
            "manifest_pass": zeta_manifest_pass,
            "manifest_mismatches": zeta_manifest_mismatches,
        }
        trajectory = {
            int(row["t"]): row
            for row in zeta.get("memory_audit", {}).get("pool_trajectory", [])
            if "t" in row
        }
        retrievals_by_t: dict[int, list[dict[str, Any]]] = {}
        for retrieval in zeta.get("memory_audit", {}).get("retrievals", []):
            if "t" not in retrieval:
                continue
            retrievals_by_t.setdefault(int(retrieval["t"]), []).append(retrieval)
        targets = [int(value) for value in schedule["seeds"][str(seed)]]
        for t in range(ROUNDS):
            row = trajectory.get(t, {})
            budget = int(row.get("budgeted_append_budget", -1))
            selected = int(row.get("budgeted_append_selected", -1))
            target = targets[t]
            retrievals = retrievals_by_t.get(t, [])
            candidate_counts = [
                int(retrieval.get("active_candidate_count", -1))
                for retrieval in retrievals
            ]
            retrieval_candidate_match = (
                len(candidate_counts) >= 12 * 4
                and all(value == target for value in candidate_counts)
            )
            manipulation.append(
                {
                    "seed": seed,
                    "t": t,
                    "target": target,
                    "budget": budget,
                    "selected": selected,
                    "retrieval_record_count": len(candidate_counts),
                    "retrieval_candidate_min": min(candidate_counts, default=-1),
                    "retrieval_candidate_max": max(candidate_counts, default=-1),
                    "budget_match": budget == target,
                    "selected_match": selected == target,
                    "retrieval_candidate_match": retrieval_candidate_match,
                    "passed": (
                        budget == target
                        and selected == target
                        and retrieval_candidate_match
                    ),
                }
            )
    final_t = ROUNDS - 1
    zeta_rows = [row for row in rows if row["condition"] == ZETA_RUN_ID]
    baseline_rows = [row for row in rows if row["condition"] == SOURCE_RUN_ID]
    stats: list[dict[str, Any]] = []
    for metric in PAIRED_METRICS:
        stat = hierarchical_paired_diff(
            zeta_rows,
            baseline_rows,
            metric,
            t=final_t,
            n_boot=n_boot,
            rng_seed=rng_seed,
        )
        stats.append(
            {
                "contrast": CONTRAST,
                "intervention": ZETA_RUN_ID,
                "baseline": SOURCE_RUN_ID,
                "t": final_t,
                "analysis_method": "seed_clustered_paired_bootstrap",
                **stat,
            }
        )
    effects = [
        {
            "contrast": CONTRAST,
            "intervention": ZETA_RUN_ID,
            "baseline": SOURCE_RUN_ID,
            **row,
        }
        for row in per_seed_paired_effects(zeta_rows, baseline_rows, t=final_t)
    ]
    manipulation_pass = len(manipulation) == len(SEEDS) * ROUNDS and all(row["passed"] for row in manipulation)
    quality = _quality_rows(results)
    for row in quality:
        key = (str(row["condition"]), int(row["seed"]))
        validation = results[key].get("_zeta_evidence_configuration", {})
        manifest_record = next(
            (
                source
                for source in source_manifests
                if source["condition"] == key[0] and int(source["seed"]) == key[1]
            ),
            {},
        )
        row["configuration_pass"] = bool(validation.get("pass"))
        row["configuration_mismatches"] = validation.get("mismatches", [])
        row["manifest_pass"] = bool(validation.get("manifest_pass"))
        row["manifest_mismatches"] = validation.get("manifest_mismatches", [])
        row["manifest_path"] = manifest_record.get("path", "")
        row["manifest_sha256"] = manifest_record.get("sha256", "")
    memory = _memory_rows(results)
    report = {
        "suite": "zeta_exact_supply_yoke",
        "decision": "zeta_supply_yoke_evaluable" if manipulation_pass else "zeta_supply_yoke_not_evaluable",
        "contrast": CONTRAST,
        "seeds": SEEDS,
        "final_t": final_t,
        "analysis_method": "seed_clustered_paired_bootstrap",
        "stats": stats,
        "per_seed_effects": effects,
        "manipulation_checks": manipulation,
        "data_quality": quality,
        "memory_summary": memory,
        "source_results": source_results,
        "source_manifests": source_manifests,
        "schedule": {
            "path": str(schedule_path),
            "sha256": schedule["schedule_sha256"],
            "preregistration": schedule["verified_preregistration"],
            "phase": schedule["phase"],
            "schedule_name": schedule["schedule_name"],
            "source_arm": schedule["source_arm"],
            "target_definition": schedule["target_definition"],
            "source_count": len(schedule["sources"]),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(stats, out_dir / "hierarchical_paired_stats.csv")
    _write_csv(effects, out_dir / "per_seed_paired_effects.csv")
    _write_csv(manipulation, out_dir / "manipulation_checks.csv")
    _write_csv(quality, out_dir / "data_quality.csv")
    _write_csv(memory, out_dir / "memory_summary.csv")
    (out_dir / "evidence_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Phase Zeta Exact Supply Yoke",
        "",
        f"Decision: **{report['decision']}**",
        "",
        f"Manipulation checks passed: {sum(1 for row in manipulation if row['passed'])}/{len(manipulation)}.",
        "",
        "| metric | mean diff | 95% CI | paired routes | seeds |",
        "|---|---:|---|---:|---:|",
    ]
    for row in stats:
        if row["metric"] in PRIMARY_METRICS:
            lines.append(
                f"| {row['metric']} | {row['mean_diff']:.4f} | "
                f"[{row['ci_lo']:.4f}, {row['ci_hi']:.4f}] | {row['n_pairs']} | {row['n_seeds']} |"
            )
    lines.extend(["", "## Per-Seed Primary Effects", ""])
    for row in effects:
        if row["metric"] in PRIMARY_METRICS:
            lines.append(
                f"- {row['metric']}, seed {row['seed']}: {row['mean_diff']:.4f} "
                f"({row['n_pairs']} paired routes)"
            )
    lines.append("")
    (out_dir / "evidence_report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze the exact Phase Zeta supply-yoked append control.")
    parser.add_argument("--controls-dir", default="runs_maze_epsilon_controls")
    parser.add_argument("--zeta-dir", default="runs_maze_zeta_exact_yoke")
    parser.add_argument("--schedule-json", default="runs_maze_zeta_schedule/zeta_schedule.json")
    parser.add_argument("--out-dir", default="runs_maze_zeta_exact_yoke_stats")
    parser.add_argument("--n-boot", type=int, default=10_000)
    parser.add_argument("--rng-seed", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    report = build_zeta_evidence(
        controls_dir=Path(args.controls_dir),
        zeta_dir=Path(args.zeta_dir),
        schedule_path=Path(args.schedule_json),
        out_dir=Path(args.out_dir),
        n_boot=args.n_boot,
        rng_seed=args.rng_seed,
    )
    print(report["decision"])
    return report


if __name__ == "__main__":
    main()
