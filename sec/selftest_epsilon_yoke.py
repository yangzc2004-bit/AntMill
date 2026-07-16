from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .config import Config
from .epsilon_evidence import (
    EPSILON_PREREGISTRATION,
    _expected_epsilon_config,
)
from .epsilon_yoke import (
    ROUNDS,
    SEEDS,
    YOKE_SCHEDULE_NAME,
    ZETA_RUN_ID,
    extract_schedule,
    install_exact_yoke,
    normalize_zeta_audit,
    verify_schedule,
)
from .memory import InsightMemory


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    targets = [0, 3, 2, 4, 1, 5]
    with tempfile.TemporaryDirectory(prefix="antmill-zeta-yoke-") as raw:
        root = Path(raw)
        controls = root / "controls"
        for seed in SEEDS:
            run_dir = controls / f"n4_gt_false_seed{seed}_epsilon_shared_consolidated"
            config = _expected_epsilon_config(
                suite="controls",
                arm="epsilon_shared_consolidated",
                seed=seed,
            )
            _write(
                run_dir / "result.json",
                {"config": config},
            )
            _write(
                run_dir / "memory_audit.json",
                {
                    "pool_trajectory": [
                        {"t": t, "active_pool_size": value}
                        for t, value in enumerate(targets)
                    ]
                },
            )
            _write(
                run_dir / "manifest.json",
                {
                    "condition": f"n4_gt_false_seed{seed}_epsilon_shared_consolidated",
                    "run_id": "epsilon_shared_consolidated",
                    "seed": seed,
                    "reviewer_temp": config["reviewer_temp"],
                    "tie_rule": config["tie_rule"],
                    "append_dedup": config["append_dedup"],
                    "config": config,
                    "preregistration": EPSILON_PREREGISTRATION,
                },
            )
        schedule_path = root / "schedule.json"
        schedule = extract_schedule(controls_dir=controls, out_path=schedule_path)
        assert schedule["behavioral_fields_read"] == []
        assert schedule["seeds"]["0"] == targets
        verified = verify_schedule(schedule_path)
        bad_schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
        bad_schedule["sources"] = bad_schedule["sources"][:-1]
        bad_schedule_path = root / "bad_schedule.json"
        _write(bad_schedule_path, bad_schedule)
        try:
            verify_schedule(bad_schedule_path)
        except ValueError as exc:
            assert "exactly one source record" in str(exc)
        else:
            raise AssertionError("incomplete Zeta source schedule must be rejected")
        audit = normalize_zeta_audit(
            {
                "pool_trajectory": [
                    {"t": 1, "budgeted_append_selected": 3},
                    {"t": 2, "budgeted_append_selected": 3},
                ]
            },
            targets,
        )
        assert audit["pool_trajectory"][0]["budgeted_append_selected"] == 3
        assert audit["pool_trajectory"][1]["budgeted_append_selected"] == 2
        assert audit["pool_trajectory"][1]["budgeted_append_selected_cumulative"] == 3
        restore = install_exact_yoke(verified)
        try:
            cfg = Config(
                seed=0,
                memory_mode="shared",
                memory_read_protocol="budgeted_append",
                budget_schedule_name=YOKE_SCHEDULE_NAME,
                retrieval_k=6,
            )
            memory = InsightMemory(cfg)
            assert [memory.budget_for_round(t) for t in range(ROUNDS)] == targets
            memory.shared = [
                {"id": f"item-{index}", "kind": "do", "text": f"strategy {index}", "votes": 2}
                for index in range(8)
            ]
            assert len(memory._budgeted_pool(memory.shared, t=1)) == 3
            assert len(memory._budgeted_pool(memory.shared, t=2)) == 2
            assert len(memory._budgeted_pool(memory.shared, t=3)) == 4
            from . import maze_alpha

            arms = maze_alpha._arms_for_phase("gamma_p1_budgeted_append")
            assert len(arms) == 1 and arms[0]["run_id"] == ZETA_RUN_ID
        finally:
            restore()
    print("selftest_epsilon_yoke OK")


if __name__ == "__main__":
    main()
