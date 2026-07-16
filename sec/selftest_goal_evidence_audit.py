from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from .epsilon_evidence import CONTROL_ARMS, SENSITIVITY_ARMS
from .goal_evidence_audit import build_goal_evidence_audit


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _complete_fixture(root: Path) -> None:
    runtime_source = root / "sec" / "p3_runtime_fixture.py"
    _touch(runtime_source, "# frozen P3 runtime fixture\n")
    _write_json(
        root / "p3e_runtime_source.freeze.json",
        {
            "status": "fixture",
            "files": [
                {
                    "path": "sec/p3_runtime_fixture.py",
                    "sha256": _sha256(runtime_source),
                }
            ],
        },
    )
    for arm in CONTROL_ARMS:
        for seed in range(5):
            _write_json(
                root
                / "runs_maze_epsilon_controls"
                / f"n4_gt_false_seed{seed}_{arm}"
                / "result.json",
                {},
            )
    for arm in SENSITIVITY_ARMS:
        for seed in range(3):
            _write_json(
                root
                / "runs_maze_epsilon_sensitivity"
                / f"n4_gt_false_seed{seed}_{arm}"
                / "result.json",
                {},
            )
    for seed in range(5):
        _write_json(
            root
            / "runs_maze_zeta_exact_yoke"
            / f"n4_gt_false_seed{seed}_zeta_shared_append_exact_yoke"
            / "result.json",
            {},
        )
    p3_environment = {
        "miniwob_plusplus_commit": "fixture",
        "primary_tasks": ["fixture-task"],
        "replacement_tasks": [],
        "python_version": "3.fixture",
        "browser_executable": "fixture-browser",
        "browser_version": "1.2.3",
        "browser_executable_sha256": "fixture-executable-sha256",
        "browser_tree_root": "fixture-browser-root",
        "browser_tree_sha256": "fixture-tree-sha256",
        "browser_tree_file_count": 273,
        "browser_tree_total_bytes": 501388593,
        "versions": {"playwright": "fixture"},
        "miniwob_url": "http://fixture.invalid",
        "task_validation": {
            "ok": True,
            "missing": [],
            "n_registered": 189,
        },
        "independent_envs_per_task": 4,
    }
    p3_manifest_paths: list[Path] = []
    for index in range(54):
        run_dir = root / "runs_miniwob_gamma_p3e" / f"condition_{index}"
        _write_json(run_dir / "result.json", {})
        manifest_path = run_dir / "manifest.json"
        _write_json(
            manifest_path,
            {
                "phase": "gamma_p3_formal",
                "miniwob": p3_environment,
            },
        )
        p3_manifest_paths.append(manifest_path)

    sections = {
        "epsilon_controls": {"status": "complete"},
        "epsilon_sensitivity": {"status": "complete"},
        "zeta_exact_supply_yoke": {"status": "complete"},
        "p3_primary": {
            "status": "complete",
            "checks": {"runtime_source_hashes": True},
        },
        "p3_append_secondary": {
            "status": "complete",
            "checks": {"runtime_source_hashes": True},
        },
    }
    _write_json(
        root / "runs_revision_evidence" / "revision_evidence.json",
        {
            "status": "ready_for_paper_revision",
            "p3_reports_same_quality": True,
            "p3_quality_clear": True,
            "sections": sections,
        },
    )
    for path in [
        root / "runs_maze_epsilon_controls_stats" / "evidence_manifest.json",
        root / "runs_maze_epsilon_sensitivity_stats" / "evidence_manifest.json",
        root / "runs_maze_zeta_exact_yoke_stats" / "evidence_manifest.json",
    ]:
        value = {
            "analysis_method": "seed_clustered_paired_bootstrap",
            "per_seed_effects": [{"seed": 0}],
        }
        if "zeta" in str(path):
            value["decision"] = "zeta_supply_yoke_evaluable"
            value["manipulation_checks"] = [
                {
                    "seed": seed,
                    "t": t,
                    "target": 4,
                    "retrieval_record_count": 48,
                    "retrieval_candidate_min": 4,
                    "retrieval_candidate_max": 4,
                    "retrieval_candidate_match": True,
                    "passed": True,
                }
                for seed in range(5)
                for t in range(6)
            ]
        _write_json(path, value)
    generated = root / "paper_draft" / "generated" / "revision_results"
    _write_json(
        generated / "claim_decisions.json",
        {
            "status": "claim_decisions_ready",
            "mmr_vs_consolidated": {},
            "p3": {"interpretation": "not_detected_under_frozen_design"},
        },
    )
    _write_json(
        generated / "paper_results_manifest.json",
        {"status": "paper_results_generated"},
    )
    _touch(generated / "appendix_heterogeneity.tex", "% generated\n")
    _write_json(
        generated / "final_render_audit.json",
        {"status": "visual_audit_complete"},
    )
    _write_json(
        generated / "final_supplement_render_audit.json",
        {"status": "visual_audit_complete"},
    )
    _write_json(
        generated / "reproducibility_checklist_report.json",
        {"status": "checklist_ready"},
    )
    _write_json(
        generated / "final_checklist_render_audit.json",
        {"status": "visual_audit_complete"},
    )
    _write_json(
        generated / "environment_manifest.json",
        {
            "status": "environment_manifest_ready",
            "browser_environment": {
                **p3_environment,
                "provenance": {
                    "source": "formal_run_manifests",
                    "completed_manifest_count": 54,
                    "source_manifests": [
                        {"path": str(path), "sha256": _sha256(path)}
                        for path in p3_manifest_paths
                    ],
                },
            },
        },
    )
    _write_json(
        root
        / "runs_manuscript_revision_audit"
        / "manuscript_revision_audit.json",
        {"status": "complete"},
    )
    tex = "\n".join(
        [
            "\\paragraph{Operational loop metrics.} cycle length.",
            "Route-level stagnation is",
            "\\[\\mathbf{1}\\{x\\}\\]",
            "\\paragraph{Applicability and governance controls.}",
            "\\citep{lu2026tag,kumar2026memarchitect,cai2026proactagent,"
            "he2026memoryarena,kagaya2024rap}",
            "MiniWoB boundary.",
        ]
    )
    _touch(root / "paper_draft" / "antmill_memory_aaai27_en.tex", tex)
    _touch(
        root / "paper_draft" / "antmill_memory_aaai27_supp.tex",
        "\\section{Sensitivity Envelope}\n",
    )
    _touch(
        root / "paper_draft" / "antmill_memory_reproducibility_checklist.tex",
        "\\section*{Reproducibility Checklist}\n",
    )
    bib = "\n".join(
        [
            "@misc{lu2026tag,title={TAG}}",
            "@misc{kumar2026memarchitect,title={MemArchitect}}",
            "@misc{cai2026proactagent,title={ProactAgent}}",
            "@misc{he2026memoryarena,title={MemoryArena}}",
            "@misc{kagaya2024rap,title={RAP}}",
        ]
    )
    _touch(root / "paper_draft" / "antmill_memory.bib", bib)
    _touch(root / "paper_draft" / "antmill_memory_aaai27_en.pdf", "%PDF fixture")
    _touch(root / "paper_draft" / "antmill_memory_aaai27_supp.pdf", "%PDF fixture")
    _touch(
        root / "paper_draft" / "antmill_memory_reproducibility_checklist.pdf",
        "%PDF fixture",
    )
    _touch(root / "sec" / "maze_stats.py")
    _touch(root / "sec" / "epsilon_evidence.py")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-goal-audit-") as raw:
        root = Path(raw)
        _complete_fixture(root)
        result = build_goal_evidence_audit(root=root, out_dir=root / "audit")
        assert result["status"] == "complete", result
        assert result["complete_count"] == result["requirement_count"]

        revision_path = (
            root / "runs_revision_evidence" / "revision_evidence.json"
        )
        revision = json.loads(revision_path.read_text(encoding="utf-8"))
        revision["sections"]["p3_append_secondary"]["checks"][
            "runtime_source_hashes"
        ] = False
        _write_json(revision_path, revision)
        result = build_goal_evidence_audit(
            root=root,
            out_dir=root / "runtime-source-mismatch",
        )
        p3 = next(
            row
            for row in result["requirements"]
            if row["name"] == "realistic_tool_or_web_task_boundary"
        )
        assert result["status"] == "incomplete"
        assert p3["status"] == "in_progress"
        assert (
            p3["evidence"]["runtime_source_hashes_recorded_in_final_gate"]
            is False
        )
        assert p3["evidence"]["current_runtime_source_hashes_match"] is True
        revision["sections"]["p3_append_secondary"]["checks"][
            "runtime_source_hashes"
        ] = True
        _write_json(revision_path, revision)

        runtime_source = root / "sec" / "p3_runtime_fixture.py"
        runtime_source.write_text("# changed after freeze\n", encoding="utf-8")
        result = build_goal_evidence_audit(
            root=root,
            out_dir=root / "current-runtime-source-mismatch",
        )
        p3 = next(
            row
            for row in result["requirements"]
            if row["name"] == "realistic_tool_or_web_task_boundary"
        )
        assert result["status"] == "incomplete"
        assert p3["status"] == "in_progress"
        assert p3["evidence"]["current_runtime_source_hashes_match"] is False
        assert p3["evidence"]["current_runtime_source_hashes"] == "0/1"
        runtime_source.write_text("# frozen P3 runtime fixture\n", encoding="utf-8")

        environment_path = (
            root
            / "paper_draft"
            / "generated"
            / "revision_results"
            / "environment_manifest.json"
        )
        environment = json.loads(environment_path.read_text(encoding="utf-8"))
        environment["browser_environment"]["browser_version"] = "stale-version"
        _write_json(environment_path, environment)
        result = build_goal_evidence_audit(
            root=root,
            out_dir=root / "stale-environment",
        )
        p3 = next(
            row
            for row in result["requirements"]
            if row["name"] == "realistic_tool_or_web_task_boundary"
        )
        assert result["status"] == "incomplete"
        assert p3["status"] == "in_progress"
        assert p3["evidence"]["generated_environment_matches_current"] is False
        environment["browser_environment"]["browser_version"] = "1.2.3"
        _write_json(environment_path, environment)

        zeta_path = (
            root
            / "runs_maze_zeta_exact_yoke_stats"
            / "evidence_manifest.json"
        )
        zeta = json.loads(zeta_path.read_text(encoding="utf-8"))
        zeta["decision"] = "zeta_supply_yoke_not_evaluable"
        zeta["manipulation_checks"][0]["passed"] = False
        _write_json(zeta_path, zeta)
        result = build_goal_evidence_audit(
            root=root,
            out_dir=root / "failed-exact-yoke",
        )
        yoke = next(
            row
            for row in result["requirements"]
            if row["name"] == "fixed_and_exact_pool_size_controls"
        )
        assert result["status"] == "incomplete"
        assert yoke["status"] == "in_progress"
        assert yoke["evidence"]["zeta_manipulation_checks"] == "29/30"
        zeta["decision"] = "zeta_supply_yoke_evaluable"
        zeta["manipulation_checks"][0]["passed"] = True
        _write_json(zeta_path, zeta)

        revision = json.loads(revision_path.read_text(encoding="utf-8"))
        revision["p3_quality_clear"] = False
        _write_json(revision_path, revision)
        claims_path = (
            root
            / "paper_draft"
            / "generated"
            / "revision_results"
            / "claim_decisions.json"
        )
        claims = json.loads(claims_path.read_text(encoding="utf-8"))
        claims["p3"]["interpretation"] = (
            "not_behaviorally_interpretable_quality_warning"
        )
        _write_json(claims_path, claims)
        result = build_goal_evidence_audit(
            root=root,
            out_dir=root / "quality-warning",
        )
        p3 = next(
            row
            for row in result["requirements"]
            if row["name"] == "realistic_tool_or_web_task_boundary"
        )
        assert result["status"] == "incomplete"
        assert p3["status"] == "in_progress"

        revision["p3_quality_clear"] = True
        _write_json(revision_path, revision)
        claims["p3"]["interpretation"] = "not_detected_under_frozen_design"
        _write_json(claims_path, claims)
        (root / "runs_miniwob_gamma_p3e" / "condition_53" / "result.json").unlink()
        result = build_goal_evidence_audit(root=root, out_dir=root / "broken")
        assert result["status"] == "incomplete"
        p3 = next(
            row
            for row in result["requirements"]
            if row["name"] == "realistic_tool_or_web_task_boundary"
        )
        assert p3["status"] == "in_progress"
    print("selftest_goal_evidence_audit OK")


if __name__ == "__main__":
    main()
