from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .environment_manifest import build_environment_manifest


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-environment-") as raw:
        root = Path(raw)
        runs = root / "runs"
        run = runs / "formal_run"
        run.mkdir(parents=True)
        (run / "result.json").write_text("{}", encoding="utf-8")
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "phase": "gamma_p3_formal",
                    "miniwob": {
                        "miniwob_plusplus_commit": "pinned-commit",
                        "primary_tasks": ["task-a"],
                        "replacement_tasks": ["task-b"],
                        "python_version": "3.12",
                        "browser_executable": "C:/Browser/browser.exe",
                        "browser_version": "1.2.3.4",
                        "browser_executable_sha256": "fixture-executable-sha256",
                        "browser_tree_root": "C:/Browser",
                        "browser_tree_sha256": "fixture-tree-sha256",
                        "browser_tree_file_count": 273,
                        "browser_tree_total_bytes": 501388593,
                        "versions": {
                            "browsergym-core": "1",
                            "browsergym-miniwob": "1",
                            "gymnasium": "1",
                            "playwright": "1",
                        },
                        "miniwob_url": "file:///miniwob/",
                        "task_validation": {
                            "ok": True,
                            "missing": [],
                            "n_registered": 189,
                        },
                        "independent_envs_per_task": 4,
                    },
                }
            ),
            encoding="utf-8",
        )
        active = runs / "active_run"
        active.mkdir()
        (active / "manifest.json").write_text(
            json.dumps(
                {
                    "phase": "gamma_p3_formal",
                    "miniwob": {
                        "browser_version": "must-be-ignored-without-result"
                    },
                }
            ),
            encoding="utf-8",
        )
        result = build_environment_manifest(
            json_path=root / "environment.json",
            tex_path=root / "environment.tex",
            markdown_path=root / "environment.md",
            p3_runs_dir=runs,
        )
        assert result["status"] == "environment_manifest_ready"
        assert result["system"]["logical_cpu_count"]
        assert result["system"]["python_version"]
        assert result["system"]["python_executable"] == Path(
            result["system"]["python_executable"]
        ).name
        assert "browsergym-miniwob" in result["software_packages"]
        assert result["browser_environment"]["browser_version"] == "1.2.3.4"
        assert (
            result["browser_environment"]["browser_executable_sha256"]
            == "fixture-executable-sha256"
        )
        assert (
            result["browser_environment"]["browser_tree_sha256"]
            == "fixture-tree-sha256"
        )
        assert (
            result["browser_environment"]["provenance"]["source"]
            == "formal_run_manifests"
        )
        assert (
            result["browser_environment"]["provenance"]["completed_manifest_count"]
            == 1
        )
        assert (
            result["browser_environment"]["task_validation"]["n_registered"]
            == 189
        )
        assert result["browser_environment"]["independent_envs_per_task"] == 4
        assert (root / "environment.json").exists()
        tex = (root / "environment.tex").read_text(encoding="utf-8")
        assert "\\begin{table*}" in tex
        assert "Browser version" in tex
        assert "Formal MiniWoB manifests" in tex
        assert "Registered MiniWoB tasks" in tex
        assert "Independent environments per task" in tex

        conflicting = runs / "conflicting_completed_run"
        conflicting.mkdir()
        (conflicting / "result.json").write_text("{}", encoding="utf-8")
        conflict_manifest = json.loads(
            (run / "manifest.json").read_text(encoding="utf-8")
        )
        conflict_manifest["miniwob"]["browser_version"] = "9.9.9"
        (conflicting / "manifest.json").write_text(
            json.dumps(conflict_manifest),
            encoding="utf-8",
        )
        try:
            build_environment_manifest(
                json_path=root / "conflict.json",
                tex_path=root / "conflict.tex",
                markdown_path=root / "conflict.md",
                p3_runs_dir=runs,
            )
        except ValueError as exc:
            assert "disagree" in str(exc)
        else:
            raise AssertionError(
                "Conflicting completed MiniWoB environments must be rejected"
            )
    print("selftest_environment_manifest OK")


if __name__ == "__main__":
    main()
