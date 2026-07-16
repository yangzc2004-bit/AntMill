from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .epsilon_evidence import EPSILON_PREREGISTRATION
from .live_run_health import build_live_run_health
from .selftest_epsilon import _result as epsilon_result
from .selftest_p3 import _fake_manifest as p3_manifest
from .selftest_p3 import _fake_result as p3_result


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-live-health-") as raw:
        root = Path(raw)
        epsilon_dir = root / "epsilon"
        p3_dir = root / "p3"
        epsilon_path = (
            epsilon_dir
            / "n4_gt_false_seed0_epsilon_frozen_reviewer"
            / "result.json"
        )
        epsilon = epsilon_result(
            arm="epsilon_frozen_reviewer",
            seed=0,
            offset=0.0,
        )
        _write(epsilon_path, epsilon)
        _write(
            epsilon_path.parent / "manifest.json",
            {
                "condition": "n4_gt_false_seed0_epsilon_frozen_reviewer",
                "run_id": "epsilon_frozen_reviewer",
                "seed": 0,
                "config": epsilon["config"],
                "preregistration": EPSILON_PREREGISTRATION,
            },
        )
        for condition, suffix in [
            ("frozen", "frozen_reviewer"),
            ("append", "shared_append_ga"),
        ]:
            result = p3_result(
                family="click-button",
                cost=0.4,
                stall=False,
                seed="0",
                condition=condition,
            )
            path = (
                p3_dir
                / f"n4_gt_false_seed0_gamma_p3_click_button_{suffix}"
                / "result.json"
            )
            _write(path, result)
            _write(
                path.parent / "manifest.json",
                p3_manifest(
                    result=result,
                    family="click-button",
                    seed="0",
                    condition=condition,
                ),
            )
        report = build_live_run_health(
            epsilon_dir=epsilon_dir,
            p3_dir=p3_dir,
            out_dir=root / "out",
        )
        assert report["status"] == "completed_artifacts_engineering_clear"
        assert report["epsilon"]["summary"]["completed_results"] == 1
        assert report["p3"]["summary"]["completed_results"] == 2
        assert report["p3"]["summary"]["quality_status_for_completed_results"] == "quality_clear"
        assert report["p3"]["summary"]["complete_families"] == []
        assert (root / "out" / "live_run_health.json").exists()
        assert (root / "out" / "live_run_health.md").exists()

        frozen_path = (
            p3_dir
            / "n4_gt_false_seed0_gamma_p3_click_button_frozen_reviewer"
            / "result.json"
        )
        frozen_warning = json.loads(
            frozen_path.read_text(encoding="utf-8")
        )
        frozen_warning["heldout_records"][0]["episodes"][0]["agents"][0][
            "route"
        ]["llm_error_count"] = 1
        frozen_warning["summary"]["llm"] = {
            "errors": 1,
            "retry_count": 0,
            "content_filter_hits": 0,
        }
        _write(frozen_path, frozen_warning)
        report = build_live_run_health(
            epsilon_dir=epsilon_dir,
            p3_dir=p3_dir,
            out_dir=root / "p3-disclosure",
        )
        assert (
            report["status"]
            == "completed_artifacts_engineering_clear_with_nonterminal_warnings"
        )
        assert report["p3"]["summary"]["total_exhausted_llm_calls"] == 1
        assert (
            report["p3"]["summary"][
                "total_route_llm_errors_all_rounds"
            ]
            == 1
        )
        assert report["p3"]["summary"]["total_route_llm_errors_final"] == 0
        assert len(
            report["p3"]["summary"]["llm_disclosure_warning_runs"]
        ) == 1
        _write(
            frozen_path,
            p3_result(
                family="click-button",
                cost=0.4,
                stall=False,
                seed="0",
                condition="frozen",
            ),
        )

        epsilon["heldout_records"][2]["episodes"][0]["agents"][0]["route"][
            "llm_error_count"
        ] = 1
        epsilon["memory_audit"]["llm_errors"] = [
            {
                "t": 2,
                "task_id": "heldout_0_0",
                "tag": "maze_agent:0",
                "message": "fixture exhausted call",
            }
        ]
        _write(epsilon_path, epsilon)
        report = build_live_run_health(
            epsilon_dir=epsilon_dir,
            p3_dir=p3_dir,
            out_dir=root / "nonterminal-warning",
        )
        assert (
            report["status"]
            == "completed_artifacts_engineering_clear_with_nonterminal_warnings"
        )
        assert report["epsilon"]["summary"]["total_exhausted_llm_calls"] == 1
        assert report["epsilon"]["summary"]["total_all_round_route_llm_errors"] == 1
        assert report["epsilon"]["summary"]["total_terminal_route_llm_errors"] == 0
        assert report["epsilon"]["summary"]["nonterminal_route_quality_warnings"][
            0
        ]["route_llm_error_rounds"] == [2]
        assert report["epsilon"]["summary"]["llm_quality_warnings"][0][
            "exhausted_llm_call_contexts"
        ] == {"heldout_solver": 1}

        broken = p3_result(
            family="click-button",
            cost=0.4,
            stall=False,
            seed="0",
            condition="append",
        )
        broken["heldout_records"][0]["episodes"][0]["agents"][0]["route"][
            "parse_failure_count"
        ] = 20
        _write(
            p3_dir
            / "n4_gt_false_seed0_gamma_p3_click_button_shared_append_ga"
            / "result.json",
            broken,
        )
        report = build_live_run_health(
            epsilon_dir=epsilon_dir,
            p3_dir=p3_dir,
            out_dir=root / "broken",
        )
        assert report["status"] == "completed_artifacts_need_review"
        assert len(report["p3"]["summary"]["failed_completed_results"]) == 1
    print("selftest_live_run_health OK")


if __name__ == "__main__":
    main()
