from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_report(results: list[dict[str, Any]], out_dir: Path, *, notes: list[str] | None = None) -> Path:
    lines = [
        "# SEC HotpotQA Run Report",
        "",
        "This report uses only observed run data. It does not reshape curves to match the expected mechanism.",
        "",
        "## Conditions",
        "",
        "| condition | t* | A peak | A final | A drop | total tokens | cache hit rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        summary = result["summary"]
        llm = summary["llm"]
        lines.append(
            "| {condition} | {t_star} | {A_peak} | {A_final} | {A_drop} | {tokens} | {hit} |".format(
                condition=summary["condition"],
                t_star=_fmt(summary["t_star"]),
                A_peak=_fmt(summary["A_peak"]),
                A_final=_fmt(summary["A_final"]),
                A_drop=_fmt(summary["A_drop"]),
                tokens=llm.get("trace_total_tokens", llm["total_tokens"]),
                hit=_fmt(llm["cache_hit_rate"]),
            )
        )
    lines.extend(["", "## Artifacts", ""])
    for result in results:
        condition = result["summary"]["condition"]
        lines.append(f"- `{condition}`: `{out_dir.name}/{condition}/result.json`, `{out_dir.name}/{condition}/curves.png`")
    if len(results) > 1:
        lines.append(f"- Comparison: `{out_dir.name}/compare_A_t.png`")
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Expected SEC signal would be N=4 showing rising or high consensus while held-out accuracy later drops. "
            "If this run does not show that pattern, treat it as an empirical result and use stress sweeps only as follow-up.",
        ]
    )
    path = out_dir / "REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
