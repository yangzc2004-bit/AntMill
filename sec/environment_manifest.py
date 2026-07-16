from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from .miniwob_gamma import browsergym_version_manifest


PACKAGE_NAMES = [
    "browsergym-core",
    "browsergym-miniwob",
    "gymnasium",
    "playwright",
    "openai",
    "httpx",
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "pypdf",
    "pdfplumber",
]
FORMAL_MINIWOB_FIELDS = [
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _total_memory_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.virtual_memory().total)
    except (ImportError, AttributeError):
        pass
    if platform.system() == "Windows":
        try:
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.length = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError):
            pass
    return None


def _cpu_model() -> str:
    if platform.system() == "Windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "ProcessorNameString")
                if str(value).strip():
                    return str(value).strip()
        except (FileNotFoundError, OSError):
            pass
    return (
        os.environ.get("PROCESSOR_IDENTIFIER")
        or platform.processor()
        or "unavailable"
    )


def _git_value(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def formal_browser_environment(runs_dir: Path) -> dict[str, Any]:
    records: list[dict[str, str]] = []
    environments: list[dict[str, Any]] = []
    for manifest_path in sorted(runs_dir.glob("**/manifest.json")):
        result_path = manifest_path.with_name("result.json")
        if not result_path.exists():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if payload.get("phase") != "gamma_p3_formal":
            continue
        miniwob = payload.get("miniwob")
        if not isinstance(miniwob, dict):
            raise ValueError(f"Formal MiniWoB manifest lacks environment: {manifest_path}")
        environment = {field: miniwob.get(field) for field in FORMAL_MINIWOB_FIELDS}
        missing = [
            field
            for field in [
                "miniwob_plusplus_commit",
                "browser_executable",
                "browser_version",
                "browser_executable_sha256",
                "browser_tree_root",
                "browser_tree_sha256",
                "browser_tree_file_count",
                "browser_tree_total_bytes",
                "miniwob_url",
            ]
            if not environment.get(field)
        ]
        if missing:
            raise ValueError(
                f"Formal MiniWoB manifest lacks {missing}: {manifest_path}"
            )
        environments.append(environment)
        records.append(
            {
                "path": str(manifest_path),
                "sha256": _sha256(manifest_path),
            }
        )
    if not environments:
        browser = browsergym_version_manifest()
        browser["provenance"] = {
            "source": "ambient_environment",
            "completed_manifest_count": 0,
            "source_manifests": [],
        }
        return browser
    reference = environments[0]
    inconsistent = [
        index
        for index, environment in enumerate(environments[1:], start=1)
        if environment != reference
    ]
    if inconsistent:
        raise ValueError(
            "Completed formal MiniWoB manifests disagree on the execution "
            f"environment at indexes {inconsistent}"
        )
    reference["provenance"] = {
        "source": "formal_run_manifests",
        "completed_manifest_count": len(records),
        "source_manifests": records,
    }
    return reference


def _latex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _render_tex(manifest: dict[str, Any]) -> str:
    system = manifest["system"]
    browser = manifest["browser_environment"]
    packages = manifest["software_packages"]
    memory_gib = system.get("total_memory_gib")
    rows = [
        ("Operating system", system["platform"]),
        ("CPU", system["cpu_model"]),
        ("Logical CPU count", system["logical_cpu_count"]),
        ("Installed memory", f"{memory_gib:.2f} GiB" if memory_gib else "unavailable"),
        ("Python", system["python_version"]),
        ("Browser executable", browser.get("browser_executable") or "BrowserGym default"),
        ("Browser version", browser.get("browser_version") or "unavailable"),
        (
            "Browser executable SHA-256",
            (
                str(browser.get("browser_executable_sha256"))[:12] + "..."
                if browser.get("browser_executable_sha256")
                else "unavailable"
            ),
        ),
        (
            "Browser runtime tree SHA-256",
            (
                str(browser.get("browser_tree_sha256"))[:12] + "..."
                if browser.get("browser_tree_sha256")
                else "unavailable"
            ),
        ),
        (
            "Browser runtime files",
            browser.get("browser_tree_file_count", "unavailable"),
        ),
        ("MiniWoB++ commit", browser.get("miniwob_plusplus_commit", "unavailable")),
        (
            "Formal MiniWoB manifests",
            browser.get("provenance", {}).get("completed_manifest_count", 0),
        ),
        (
            "Registered MiniWoB tasks",
            browser.get("task_validation", {}).get("n_registered", "unavailable"),
        ),
        (
            "Independent environments per task",
            browser.get("independent_envs_per_task", "unavailable"),
        ),
        ("Git revision", manifest["code_provenance"]["git_head"]),
    ]
    for name in PACKAGE_NAMES:
        rows.append((name, packages[name]))
    lines = [
        "% Generated by sec.environment_manifest.",
        "\\begin{table*}[t]",
        "\\centering",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\caption{Local execution environment for maze analysis and BrowserGym MiniWoB "
        "task execution. LLM inference used hosted model APIs; provider-side CPU/GPU "
        "models and memory were not exposed and therefore cannot be reported.}",
        "\\label{tab:execution-environment}",
        "\\begin{tabular}{@{}p{0.27\\textwidth}p{0.68\\textwidth}@{}}",
        "\\toprule",
        "Item & Recorded value \\\\",
        "\\midrule",
    ]
    for label, value in rows:
        lines.append(f"{_latex_escape(label)} & {_latex_escape(value)} \\\\")
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def build_environment_manifest(
    *,
    json_path: Path,
    tex_path: Path,
    markdown_path: Path,
    p3_runs_dir: Path = Path("runs_miniwob_gamma_p3e"),
) -> dict[str, Any]:
    total_memory = _total_memory_bytes()
    browser = formal_browser_environment(p3_runs_dir)
    manifest = {
        "status": "environment_manifest_ready",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "cpu_model": _cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "total_memory_bytes": total_memory,
            "total_memory_gib": (
                total_memory / (1024**3) if total_memory is not None else None
            ),
            "python_version": sys.version.replace("\n", " "),
            "python_executable": Path(sys.executable).name,
        },
        "software_packages": _package_versions(),
        "browser_environment": browser,
        "hosted_llm_environment": {
            "models": ["DeepSeek-V3", "Qwen3-32B"],
            "execution": "hosted API",
            "provider_hardware": "not disclosed by the hosted service",
            "local_accelerator_requirement": (
                "No local accelerator is used for hosted LLM inference."
            ),
        },
        "code_provenance": {
            "git_head": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("rev-parse", "--abbrev-ref", "HEAD"),
        },
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(_render_tex(manifest), encoding="utf-8")
    manifest["tex"] = {
        "path": str(tex_path),
        "size_bytes": tex_path.stat().st_size,
        "sha256": _sha256(tex_path),
    }
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Execution Environment",
        "",
        "Status: **environment_manifest_ready**",
        "",
        f"- Platform: `{manifest['system']['platform']}`",
        f"- CPU: `{manifest['system']['cpu_model']}`",
        f"- Logical CPUs: `{manifest['system']['logical_cpu_count']}`",
        f"- Memory: `{manifest['system']['total_memory_gib']}` GiB",
        f"- Python: `{manifest['system']['python_version']}`",
        f"- MiniWoB++ commit: `{browser.get('miniwob_plusplus_commit', 'unavailable')}`",
        f"- Browser: `{browser.get('browser_executable') or 'unavailable'}`",
        f"- Browser version: `{browser.get('browser_version') or 'unavailable'}`",
        "- Browser executable SHA-256: "
        f"`{browser.get('browser_executable_sha256') or 'unavailable'}`",
        "- Browser runtime tree SHA-256: "
        f"`{browser.get('browser_tree_sha256') or 'unavailable'}`",
        "- Browser runtime files/bytes: "
        f"`{browser.get('browser_tree_file_count', 'unavailable')}` / "
        f"`{browser.get('browser_tree_total_bytes', 'unavailable')}`",
        "- Completed formal MiniWoB manifests: "
        f"`{browser.get('provenance', {}).get('completed_manifest_count', 0)}`",
        "- Registered MiniWoB tasks: "
        f"`{browser.get('task_validation', {}).get('n_registered', 'unavailable')}`",
        "- Independent environments per task: "
        f"`{browser.get('independent_envs_per_task', 'unavailable')}`",
        f"- Git HEAD: `{manifest['code_provenance']['git_head']}`",
        "",
        "Hosted LLM provider-side hardware is not exposed by the API and is "
        "reported as unavailable rather than inferred.",
        "",
    ]
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record the local and hosted execution environment for the paper artifact."
    )
    parser.add_argument(
        "--json",
        default="paper_draft/generated/revision_results/environment_manifest.json",
    )
    parser.add_argument(
        "--tex",
        default="paper_draft/generated/revision_results/environment_manifest.tex",
    )
    parser.add_argument(
        "--markdown",
        default="paper_draft/generated/revision_results/environment_manifest.md",
    )
    parser.add_argument("--p3-runs-dir", default="runs_miniwob_gamma_p3e")
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_environment_manifest(
        json_path=Path(args.json),
        tex_path=Path(args.tex),
        markdown_path=Path(args.markdown),
        p3_runs_dir=Path(args.p3_runs_dir),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
