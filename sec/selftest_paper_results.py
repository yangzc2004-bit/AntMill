from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .epsilon_evidence import CONTROL_CONTRASTS, PRIMARY_METRICS, SENSITIVITY_ARMS
from .miniwob_stats import P3_METRICS
from .paper_results import (
    MEMORY_FIELDS,
    P3_FAMILY_LABELS,
    ZETA_CONTRAST,
    build_paper_results,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _stat(*, contrast: str, metric: str, value: float) -> dict:
    return {
        "contrast": contrast,
        "metric": metric,
        "mean_diff": value,
        "ci_lo": value - 0.01,
        "ci_hi": value + 0.01,
        "n_pairs": 240,
        "n_seeds": 5,
    }


def _memory(condition: str, seed: int, offset: float) -> dict:
    row = {"condition": condition, "seed": seed}
    row.update({field: float(seed) + offset for field in MEMORY_FIELDS})
    return row


def _quality(condition: str, seed: int) -> dict:
    return {
        "condition": condition,
        "seed": seed,
        "route_count_final": 48,
        "expected_route_count_final": 48,
        "llm_error_count": 1,
        "llm_retry_count": 1,
        "content_filter_hits": 0,
        "exhausted_llm_call_count": 1,
        "route_llm_error_count_all_rounds": 2,
        "route_llm_error_count_final": 0,
        "parse_failure_count_all_rounds": 1,
        "parse_failure_count_final": 0,
        "configuration_pass": True,
        "manifest_pass": True,
    }


def _provenance() -> dict:
    expected = "a" * 64
    return {
        "preregistration": {
            "expected_sha256": expected,
            "actual_sha256": expected,
            "match": True,
        },
        "runtime_source": {
            "all_match": True,
            "files": [
                {
                    "path": "sec/runtime.py",
                    "expected_sha256": "b" * 64,
                    "actual_sha256": "b" * 64,
                    "match": True,
                }
            ],
        },
    }


def _controls() -> dict:
    stats = []
    effects = []
    for contrast, _intervention, _baseline in CONTROL_CONTRASTS:
        for index, metric in enumerate(PRIMARY_METRICS):
            stats.append(_stat(contrast=contrast, metric=metric, value=0.02 + index * 0.01))
            for seed in range(5):
                effects.append(
                    {
                        "contrast": contrast,
                        "metric": metric,
                        "seed": seed,
                        "mean_diff": 0.01 * (seed + 1),
                    }
                )
    memory = []
    for condition, offset in [
        ("epsilon_shared_consolidated", 1.0),
        ("epsilon_shared_consolidated_mmr", 2.0),
        ("epsilon_shared_append_cap14", 3.0),
    ]:
        memory.extend(_memory(condition, seed, offset) for seed in range(5))
    return {
        "stats": stats,
        "per_seed_effects": effects,
        "memory_summary": memory,
        "data_quality": [
            _quality(condition, seed)
            for condition in [
                "epsilon_frozen_reviewer",
                "epsilon_private_consolidated",
                "epsilon_shared_consolidated",
                "epsilon_shared_append_cap14",
                "epsilon_shared_consolidated_mmr",
            ]
            for seed in range(5)
        ],
        "provenance": _provenance(),
    }


def _sensitivity() -> dict:
    stats = []
    effects = []
    for arm in SENSITIVITY_ARMS:
        if arm == "epsilon_sens_reference":
            continue
        contrast = f"{arm}_minus_epsilon_sens_reference"
        for index, metric in enumerate(PRIMARY_METRICS):
            stats.append(_stat(contrast=contrast, metric=metric, value=-0.02 - index * 0.01))
            for seed in range(3):
                effects.append(
                    {
                        "contrast": contrast,
                        "metric": metric,
                        "seed": seed,
                        "mean_diff": -0.01 * (seed + 1),
                    }
                )
    return {
        "stats": stats,
        "per_seed_effects": effects,
        "memory_summary": [
            _memory(condition, seed, 4.0)
            for condition in SENSITIVITY_ARMS
            for seed in range(3)
        ],
        "data_quality": [
            _quality(condition, seed)
            for condition in SENSITIVITY_ARMS
            for seed in range(3)
        ],
    }


def _zeta(*, evaluable: bool = True) -> dict:
    decision = "zeta_supply_yoke_evaluable" if evaluable else "zeta_supply_yoke_not_evaluable"
    return {
        "decision": decision,
        "stats": [
            _stat(contrast=ZETA_CONTRAST, metric=metric, value=0.03)
            for metric in PRIMARY_METRICS
        ],
        "per_seed_effects": [
            {
                "contrast": ZETA_CONTRAST,
                "metric": metric,
                "seed": seed,
                "mean_diff": 0.01 * (seed + 1),
            }
            for metric in PRIMARY_METRICS
            for seed in range(5)
        ],
        "manipulation_checks": [
            {
                "seed": seed,
                "t": t,
                "target": seed + t,
                "budget": seed + t,
                "selected": seed + t,
                "passed": evaluable,
            }
            for seed in range(5)
            for t in range(6)
        ],
        "memory_summary": [
            _memory(condition, seed, 5.0)
            for condition in [
                "epsilon_shared_consolidated",
                "zeta_shared_append_exact_yoke",
            ]
            for seed in range(5)
        ],
        "data_quality": [
            _quality(condition, seed)
            for condition in [
                "epsilon_shared_consolidated",
                "zeta_shared_append_exact_yoke",
            ]
            for seed in range(5)
        ],
        "schedule": {
            "sha256": "c" * 64,
            "preregistration": {
                "expected_sha256": "d" * 64,
                "actual_sha256": "d" * 64,
                "match": True,
            },
        },
    }


def _p3(intervention: str, *, quality: str = "quality_clear") -> dict:
    return {
        "intervention": intervention,
        "decision": "p3_not_detected_or_underpowered",
        "paired_stats": {
            metric: {
                "metric": metric,
                "mean_diff": 0.02,
                "ci_lo": 0.01,
                "ci_hi": 0.03,
                "n_pairs": 576,
            }
            for metric in P3_METRICS
        },
        "checks": {
            f"{metric}_same_sign_seeds": {
                "diffs": {"0": 0.01, "1": 0.02, "2": 0.03}
            }
            for metric in ["failure_penalized_cost", "loop_stall_burden"]
        },
        "per_family_effects": [
            {"family": family, "metric": metric, "mean_diff": 0.01}
            for family in P3_FAMILY_LABELS
            for metric in P3_METRICS
        ],
        "formal_data_quality": {
            "status": quality,
            "aggregate": {
                "run_count": 54,
                "route_count": 10_368,
                "parse_rate": 1.0,
                "api_error_count": 12,
                "retry_count": 9,
                "content_filter_hits": 1,
                "exhausted_llm_call_count": 3,
                "route_llm_error_count_all_rounds": 2,
                "route_llm_error_count_final": 0,
                "nonheldout_exhausted_llm_call_count": 1,
                "infrastructure_error_route_rate": 0.0,
                "bid_error_rate": 0.0,
            },
            "checks": {
                "complete_matrix": True,
                "all_llm_behavioral_paths": True,
                "all_configurations": True,
                "all_manifests": True,
                "all_environments_consistent": True,
            },
        },
        "preregistration_provenance": {
            "all_match": True,
            "files": [
                {
                    "document": "prereg_phase_gamma_p3_execution.md",
                    "expected_sha256": "e" * 64,
                    "actual_sha256": "e" * 64,
                    "match": True,
                }
            ],
            "runtime_source": {
                "all_match": True,
                "files": [
                    {
                        "path": "sec/miniwob_runner.py",
                        "expected_sha256": "f" * 64,
                        "actual_sha256": "f" * 64,
                        "match": True,
                    }
                ],
            },
        },
    }


def _build(root: Path, *, quality: str = "quality_clear", zeta_evaluable: bool = True) -> dict:
    paths = {
        "gate": root / "gate.json",
        "controls": root / "controls.json",
        "sensitivity": root / "sensitivity.json",
        "zeta": root / "zeta.json",
        "primary": root / "primary.json",
        "append": root / "append.json",
    }
    _write(paths["gate"], {"status": "ready_for_paper_revision"})
    _write(paths["controls"], _controls())
    _write(paths["sensitivity"], _sensitivity())
    _write(paths["zeta"], _zeta(evaluable=zeta_evaluable))
    _write(paths["primary"], _p3("consolidated", quality=quality))
    _write(paths["append"], _p3("append", quality=quality))
    return build_paper_results(
        revision_gate_path=paths["gate"],
        controls_path=paths["controls"],
        sensitivity_path=paths["sensitivity"],
        zeta_path=paths["zeta"],
        p3_primary_path=paths["primary"],
        p3_append_path=paths["append"],
        out_dir=root / "out",
    )


def _compile_tables(root: Path) -> None:
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return
    generated = root / "out"
    document = root / "table_test.tex"
    document.write_text(
        "\n".join(
            [
                "\\documentclass[twocolumn]{article}",
                "\\usepackage{booktabs}",
                "\\begin{document}",
                f"\\input{{{(generated / 'revision_macros.tex').as_posix()}}}",
                f"\\input{{{(generated / 'mechanism_controls.tex').as_posix()}}}",
                f"\\input{{{(generated / 'sensitivity_envelope.tex').as_posix()}}}",
                f"\\input{{{(generated / 'miniwob_boundary.tex').as_posix()}}}",
                f"\\input{{{(generated / 'appendix_heterogeneity.tex').as_posix()}}}",
                f"\\input{{{(generated / 'appendix_diagnostics.tex').as_posix()}}}",
                "\\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [pdflatex, "-interaction=nonstopmode", "-halt-on-error", document.name],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout[-4000:] + completed.stderr[-2000:])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-paper-results-") as raw:
        root = Path(raw)
        result = _build(root)
        assert result["gates"]["zeta_evaluable"]
        assert result["gates"]["p3_quality_clear"]
        assert (root / "out" / "mechanism_controls.tex").exists()
        mechanism_tex = (root / "out" / "mechanism_controls.tex").read_text()
        assert "Exact-size append yoke" in mechanism_tex
        assert "Terminal round $t=5$; five seeds per contrast" in mechanism_tex
        assert "not multiplicity-adjusted" in mechanism_tex
        p3_tex = (root / "out" / "miniwob_boundary.tex").read_text()
        assert "Consolidated $-$ frozen" in p3_tex
        assert "Consolidated family" in p3_tex
        assert "quality clear" in p3_tex
        assert "$n=576$" in p3_tex
        assert "Only failure-penalized cost" in p3_tex
        assert "MiniWoB per-family" in (root / "out" / "appendix_heterogeneity.tex").read_text()
        diagnostics = (root / "out" / "appendix_diagnostics.tex").read_text()
        assert "All 30 exact supply-yoke" in diagnostics
        assert "25/25" in diagnostics
        assert "27/27" in diagnostics
        assert "10/10" in diagnostics
        assert "Config & Manifest" in diagnostics
        assert "Exhausted" in diagnostics
        assert "Route LLM all/final" in diagnostics
        assert "Parse all/final" in diagnostics
        assert "API e/r/f/x" in diagnostics
        assert "Non-HO x" in diagnostics
        assert "LLM path" in diagnostics
        assert "12/9/1/3" in diagnostics
        assert "2/0" in diagnostics
        assert "pass & pass" in diagnostics
        assert (root / "out" / "paper_results_manifest.json").exists()
        assert len(result["generated_hashes"]) == 8
        assert result["revision_macro_count"] > 0
        macro_manifest = json.loads(
            (root / "out" / "macro_manifest.json").read_text(encoding="utf-8")
        )
        assert macro_manifest["macro_count"] == result["revision_macro_count"]
        assert any(
            row["macro"] == "RevSharedPrivateLoopRateMean"
            for row in macro_manifest["records"]
        )
        seed_sign_records = {
            row["macro"]: row["value"]
            for row in macro_manifest["records"]
            if row.get("field") == "SeedSigns"
        }
        assert seed_sign_records == {
            "RevPThreeConsolidatedFailurePenalizedCostSeedSigns": "+,+,+",
            "RevPThreeConsolidatedLoopStallBurdenSeedSigns": "+,+,+",
        }
        sensitivity_setting_records = {
            row["macro"]: row["value"]
            for row in macro_manifest["records"]
            if row.get("contrast") == "epsilon_sensitivity_envelope"
        }
        assert sensitivity_setting_records == {
            "RevSensitivityLoopRatePositiveDetectedSettings": "none",
            "RevSensitivityLoopRateNegativeDetectedSettings": (
                "k=3, k=10, cap=40, operations=3, operations=9, "
                "merge=0.7, merge=0.9, recency=1"
            ),
            "RevSensitivityLoopRateNotDetectedSettings": "none",
        }
        assert all(
            Path(record["path"]).exists()
            for record in result["generated_hashes"].values()
        )
        _compile_tables(root)

    with tempfile.TemporaryDirectory(prefix="antmill-paper-results-warning-") as raw:
        root = Path(raw)
        result = _build(root, quality="quality_warning_review_required", zeta_evaluable=False)
        assert not result["gates"]["zeta_evaluable"]
        assert not result["gates"]["p3_quality_clear"]
        assert "Exact-size append yoke" not in (root / "out" / "mechanism_controls.tex").read_text()
        assert "withheld" in (root / "out" / "miniwob_boundary.tex").read_text()

    with tempfile.TemporaryDirectory(prefix="antmill-paper-results-gate-") as raw:
        root = Path(raw)
        paths = {
            name: root / f"{name}.json"
            for name in ["gate", "controls", "sensitivity", "zeta", "primary", "append"]
        }
        _write(paths["gate"], {"status": "evidence_incomplete"})
        for name in ["controls", "sensitivity", "zeta", "primary", "append"]:
            _write(paths[name], {})
        try:
            build_paper_results(
                revision_gate_path=paths["gate"],
                controls_path=paths["controls"],
                sensitivity_path=paths["sensitivity"],
                zeta_path=paths["zeta"],
                p3_primary_path=paths["primary"],
                p3_append_path=paths["append"],
                out_dir=root / "out",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("Incomplete evidence gate should refuse paper table generation.")
    print("selftest_paper_results OK")


if __name__ == "__main__":
    main()
