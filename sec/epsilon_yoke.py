from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .config import Config, condition_name
from .epsilon_evidence import (
    _config_mismatches,
    _epsilon_manifest_check,
    _expected_epsilon_config,
)


ZETA_PREREG_FREEZE = Path("prereg_phase_zeta.freeze.json")
YOKE_SCHEDULE_NAME = "gamma_consolidated_active_cummax"
ZETA_RUN_ID = "zeta_shared_append_exact_yoke"
SOURCE_RUN_ID = "epsilon_shared_consolidated"
SEEDS = [0, 1, 2, 3, 4]
ROUNDS = 6


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zeta_prereg_provenance() -> dict[str, Any]:
    freeze = _load_json(ZETA_PREREG_FREEZE)
    document = Path(freeze["document"])
    expected = str(freeze["sha256"]).lower()
    actual = _sha256(document)
    return {
        "freeze_record": str(ZETA_PREREG_FREEZE),
        "document": str(document),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "match": actual == expected,
    }


def extract_schedule(*, controls_dir: Path, out_path: Path) -> dict[str, Any]:
    prereg = _zeta_prereg_provenance()
    if not prereg["match"]:
        raise RuntimeError("Phase Zeta preregistration hash mismatch.")
    sources: list[dict[str, Any]] = []
    schedules: dict[str, list[int]] = {}
    for seed in SEEDS:
        run_dir = controls_dir / f"n4_gt_false_seed{seed}_{SOURCE_RUN_ID}"
        result_path = run_dir / "result.json"
        audit_path = run_dir / "memory_audit.json"
        if not result_path.exists() or not audit_path.exists():
            raise FileNotFoundError(f"Missing consolidated source artifacts for seed {seed}: {run_dir}")
        result = _load_json(result_path)
        audit = _load_json(audit_path)
        config = result.get("config", {})
        config_mismatches = _config_mismatches(
            config,
            _expected_epsilon_config(
                suite="controls",
                arm=SOURCE_RUN_ID,
                seed=seed,
            ),
        )
        if config_mismatches:
            raise ValueError(
                f"Unexpected consolidated source config for seed {seed}: "
                f"{config_mismatches}"
            )
        manifest_pass, manifest_mismatches, manifest_source = _epsilon_manifest_check(
            result_path=result_path,
            result_config=config,
            arm=SOURCE_RUN_ID,
            seed=seed,
        )
        if not manifest_pass:
            raise ValueError(
                f"Unexpected consolidated source manifest for seed {seed}: "
                f"{manifest_mismatches}"
            )
        by_t = {
            int(row["t"]): int(row["active_pool_size"])
            for row in audit.get("pool_trajectory", [])
            if "t" in row and "active_pool_size" in row
        }
        expected_rounds = list(range(ROUNDS))
        if sorted(by_t) != expected_rounds:
            raise ValueError(f"Seed {seed} pool trajectory rounds are {sorted(by_t)}, expected {expected_rounds}.")
        targets = [by_t[t] for t in expected_rounds]
        schedules[str(seed)] = targets
        sources.append(
            {
                "seed": seed,
                "run_id": SOURCE_RUN_ID,
                "result_path": str(result_path),
                "result_sha256": _sha256(result_path),
                "memory_audit_path": str(audit_path),
                "memory_audit_sha256": _sha256(audit_path),
                "manifest_path": manifest_source["path"],
                "manifest_sha256": manifest_source["sha256"],
                "target_sizes": targets,
            }
        )
    schedule = {
        "phase": "zeta_exact_supply_yoke",
        "schedule_name": YOKE_SCHEDULE_NAME,
        "source_arm": SOURCE_RUN_ID,
        "target_definition": "active_pool_size at the matching evaluation round",
        "seeds": schedules,
        "sources": sources,
        "preregistration": prereg,
        "behavioral_fields_read": [],
    }
    _write_json(out_path, schedule)
    return schedule


def verify_schedule(schedule_path: Path) -> dict[str, Any]:
    schedule = _load_json(schedule_path)
    prereg = _zeta_prereg_provenance()
    if not prereg["match"]:
        raise RuntimeError("Phase Zeta preregistration hash mismatch.")
    expected_metadata = {
        "phase": "zeta_exact_supply_yoke",
        "schedule_name": YOKE_SCHEDULE_NAME,
        "source_arm": SOURCE_RUN_ID,
        "target_definition": "active_pool_size at the matching evaluation round",
        "behavioral_fields_read": [],
    }
    metadata_mismatches = _config_mismatches(schedule, expected_metadata)
    if metadata_mismatches:
        raise ValueError(f"Unexpected yoke schedule metadata: {metadata_mismatches}")
    if sorted(int(seed) for seed in schedule.get("seeds", {})) != SEEDS:
        raise ValueError("Yoke schedule does not contain exactly seeds 0..4.")
    for seed in SEEDS:
        values = schedule["seeds"].get(str(seed), [])
        if len(values) != ROUNDS or any(int(value) < 0 for value in values):
            raise ValueError(f"Invalid yoke target schedule for seed {seed}: {values}")
    sources = schedule.get("sources", [])
    source_seeds = [int(source.get("seed", -1)) for source in sources]
    if len(sources) != len(SEEDS) or len(set(source_seeds)) != len(SEEDS) or sorted(source_seeds) != SEEDS:
        raise ValueError("Yoke schedule must contain exactly one source record for each seed 0..4.")
    for source in sources:
        seed = int(source["seed"])
        if source.get("run_id") != SOURCE_RUN_ID:
            raise ValueError(f"Unexpected source arm for seed {seed}: {source.get('run_id')!r}")
        if [int(value) for value in source.get("target_sizes", [])] != [
            int(value) for value in schedule["seeds"][str(seed)]
        ]:
            raise ValueError(f"Source target sizes do not match schedule for seed {seed}.")
        result_path = Path(source["result_path"])
        audit_path = Path(source["memory_audit_path"])
        manifest_path = Path(source["manifest_path"])
        if _sha256(result_path) != source["result_sha256"]:
            raise RuntimeError(f"Source result hash changed: {result_path}")
        if _sha256(audit_path) != source["memory_audit_sha256"]:
            raise RuntimeError(f"Source memory audit hash changed: {audit_path}")
        if _sha256(manifest_path) != source["manifest_sha256"]:
            raise RuntimeError(f"Source manifest hash changed: {manifest_path}")
    schedule["schedule_sha256"] = _sha256(schedule_path)
    schedule["verified_preregistration"] = prereg
    return schedule


def normalize_zeta_audit(audit: dict[str, Any], targets: list[int]) -> dict[str, Any]:
    for row in audit.get("pool_trajectory", []):
        t = int(row.get("t", 0))
        target = int(targets[t])
        cumulative_selected = int(row.get("budgeted_append_selected", 0))
        row["budgeted_append_selected_cumulative"] = cumulative_selected
        row["budgeted_append_selected"] = min(cumulative_selected, target)
        row["zeta_target_size"] = target
        row["zeta_target_met"] = row["budgeted_append_selected"] == target
    return audit


def install_exact_yoke(schedule: dict[str, Any]) -> Callable[[], None]:
    from . import maze_alpha, memory

    schedules = {int(seed): [int(value) for value in values] for seed, values in schedule["seeds"].items()}
    original_schedule = memory.GAMMA_BUDGET_SCHEDULES.get(YOKE_SCHEDULE_NAME)
    original_budget_for_round = memory.InsightMemory.budget_for_round
    original_arms_for_phase = maze_alpha._arms_for_phase
    original_run_one = maze_alpha.run_one_maze_alpha
    memory.GAMMA_BUDGET_SCHEDULES[YOKE_SCHEDULE_NAME] = schedules

    def exact_budget_for_round(self, t: int | None) -> int:
        if self.cfg.budget_schedule_name != YOKE_SCHEDULE_NAME:
            return original_budget_for_round(self, t)
        values = schedules.get(int(self.cfg.seed), [])
        if not values:
            return 0
        index = max(0, min(int(t or 0), len(values) - 1))
        return int(values[index])

    def zeta_arms_for_phase(phase: str) -> list[dict[str, Any]]:
        if phase != "gamma_p1_budgeted_append":
            return original_arms_for_phase(phase)
        return [
            {
                "run_id": ZETA_RUN_ID,
                "n_solvers": 4,
                "memory_mode": "shared",
                "maze_write_mode": "reviewer",
                "memory_write_protocol": "append",
                "retrieval_scoring": "ga",
                "ga_lambda": 0.0,
                "ga_recency": 0.0,
                "memory_read_protocol": "budgeted_append",
                "budget_schedule_name": YOKE_SCHEDULE_NAME,
            }
        ]

    async def zeta_run_one(
        cfg: Config,
        train_tasks,
        heldout_tasks,
    ):
        result = await original_run_one(cfg, train_tasks, heldout_tasks)
        run_dir = cfg.output_path() / condition_name(cfg)
        targets = schedules[int(cfg.seed)]
        audit = normalize_zeta_audit(result.get("memory_audit", {}), targets)
        _write_json(run_dir / "result.json", result)
        _write_json(run_dir / "memory_audit.json", audit)
        manifest_path = run_dir / "manifest.json"
        manifest = _load_json(manifest_path)
        manifest["preregistration"] = "prereg_phase_zeta.md"
        manifest["zeta_exact_supply_yoke"] = {
            "schedule_sha256": schedule["schedule_sha256"],
            "source_arm": SOURCE_RUN_ID,
            "target_sizes": targets,
            "target_definition": schedule["target_definition"],
            "preregistration": schedule["verified_preregistration"],
        }
        _write_json(manifest_path, manifest)
        return result

    memory.InsightMemory.budget_for_round = exact_budget_for_round
    maze_alpha._arms_for_phase = zeta_arms_for_phase
    maze_alpha.run_one_maze_alpha = zeta_run_one

    def restore() -> None:
        if original_schedule is None:
            memory.GAMMA_BUDGET_SCHEDULES.pop(YOKE_SCHEDULE_NAME, None)
        else:
            memory.GAMMA_BUDGET_SCHEDULES[YOKE_SCHEDULE_NAME] = original_schedule
        memory.InsightMemory.budget_for_round = original_budget_for_round
        maze_alpha._arms_for_phase = original_arms_for_phase
        maze_alpha.run_one_maze_alpha = original_run_one

    return restore


def run_yoke(*, schedule_path: Path, runner_args: list[str]) -> list[dict[str, Any]]:
    from .maze_alpha import run_cli
    from .run_maze_alpha import _parser

    schedule = verify_schedule(schedule_path)
    args_list = list(runner_args)
    if args_list and args_list[0] == "--":
        args_list = args_list[1:]
    args = _parser().parse_args(["--phase", "gamma_p1_budgeted_append", *args_list])
    expected = {
        "phase": "gamma_p1_budgeted_append",
        "model": "DeepSeek-V3",
        "base_url": "https://api.modelarts-maas.com/v2",
        "api_key_env": "MODELARTS_MAAS_KEY",
        "seeds": "0,1,2,3,4",
        "T": 6,
        "train_batch": 4,
        "train_size": 24,
        "heldout_size": 12,
        "maze_width": 15,
        "maze_height": 15,
        "maze_family": "trap",
        "maze_min_shortest": 30,
        "maze_agent_mode": "state_guided",
        "max_steps": 120,
        "retrieval_k": 6,
        "library_cap": 80,
        "concurrency": 8,
        "solver_temp": 0.7,
        "max_tokens_solver": 256,
        "max_tokens_reviewer": 512,
        "skip_final_train": True,
    }
    for name, value in expected.items():
        if getattr(args, name) != value:
            raise ValueError(f"Frozen Zeta argument {name} must be {value!r}, got {getattr(args, name)!r}.")
    restore = install_exact_yoke(schedule)
    try:
        return run_cli(args)
    finally:
        restore()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract and run the exact Phase Zeta supply yoke.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--controls-dir", default="runs_maze_epsilon_controls")
    extract.add_argument("--out", default="runs_maze_zeta_schedule/zeta_schedule.json")
    run = sub.add_parser("run")
    run.add_argument("--schedule-json", required=True)
    run.add_argument("runner_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> Any:
    args = _parser().parse_args(argv)
    if args.cmd == "extract":
        result = extract_schedule(controls_dir=Path(args.controls_dir), out_path=Path(args.out))
        print(json.dumps(result["seeds"], ensure_ascii=False))
        return result
    if args.cmd == "run":
        return run_yoke(schedule_path=Path(args.schedule_json), runner_args=args.runner_args)
    raise ValueError(args.cmd)


if __name__ == "__main__":
    main()
