from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


QUESTION_PATTERN = re.compile(
    r"(?P<prefix>\\question\{(?P<question>[^{}]+)\}\{\((?P<options>[^()]*)\)\}"
    r"[ \t]*\r?\n)(?P<indent>[ \t]*)(?P<placeholder>Type your response here)"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize(text: str) -> str:
    text = re.sub(r"\ufffd+", "'", text)
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    return " ".join(text.split())


def build_reproducibility_checklist(
    *,
    template_path: Path,
    responses_path: Path,
    output_tex_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    template_hash = _sha256(template_path)
    specification = json.loads(responses_path.read_text(encoding="utf-8-sig"))
    expected_hash = str(specification.get("template_sha256", "")).lower()
    if template_hash != expected_hash:
        raise ValueError(
            "AuthorKit checklist template hash mismatch: "
            f"expected {expected_hash}, found {template_hash}"
        )

    response_rows = list(specification.get("responses", []))
    response_index: dict[str, dict[str, Any]] = {}
    for row in response_rows:
        question = _normalize(str(row.get("question", "")))
        if not question or question in response_index:
            raise ValueError(f"Missing or duplicate checklist question: {question!r}")
        response_index[question] = dict(row)

    template = template_path.read_text(encoding="utf-8-sig")
    matched_questions: list[str] = []
    emitted_rows: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        question = _normalize(match.group("question"))
        options = [item.strip() for item in match.group("options").split("/")]
        row = response_index.get(question)
        if row is None:
            raise ValueError(f"No response supplied for checklist question: {question}")
        answer = str(row.get("answer", "")).strip()
        if answer not in options:
            raise ValueError(
                f"Invalid answer {answer!r} for {question!r}; allowed={options}"
            )
        matched_questions.append(question)
        emitted_rows.append(
            {
                "question": question,
                "options": options,
                "answer": answer,
                "evidence": str(row.get("evidence", "")).strip(),
            }
        )
        return match.group("prefix") + match.group("indent") + answer

    output = QUESTION_PATTERN.sub(replace, template)
    if QUESTION_PATTERN.search(output):
        raise ValueError("Checklist still contains unresolved question responses.")
    if len(matched_questions) != len(response_rows):
        extra = sorted(set(response_index) - set(matched_questions))
        raise ValueError(
            "Checklist response count mismatch: "
            f"template={len(matched_questions)}, responses={len(response_rows)}, "
            f"unmatched={extra}"
        )
    if len(set(matched_questions)) != len(matched_questions):
        raise ValueError("Checklist template contains duplicate question text.")

    output_tex_path.parent.mkdir(parents=True, exist_ok=True)
    output_tex_path.write_text(output, encoding="utf-8")
    spec_status = str(specification.get("status", "provisional"))
    status = (
        "checklist_ready"
        if spec_status == "finalized"
        else "checklist_provisional"
    )
    result = {
        "status": status,
        "specification_status": spec_status,
        "question_count": len(emitted_rows),
        "template": {
            "path": str(template_path),
            "sha256": template_hash,
        },
        "responses": {
            "path": str(responses_path),
            "sha256": _sha256(responses_path),
        },
        "output": {
            "path": str(output_tex_path),
            "sha256": _sha256(output_tex_path),
        },
        "answers": emitted_rows,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path = report_path.with_suffix(".md")
    lines = [
        "# Reproducibility Checklist Evidence",
        "",
        f"Status: **{status}**",
        f"Questions: **{len(emitted_rows)}**",
        "",
        "| question | answer | evidence |",
        "|---|---|---|",
    ]
    for row in emitted_rows:
        question = row["question"].replace("|", "\\|")
        evidence = row["evidence"].replace("|", "\\|")
        lines.append(f"| {question} | {row['answer']} | {evidence} |")
    lines.append("")
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and audit the standalone AAAI reproducibility checklist."
    )
    parser.add_argument(
        "--template",
        default=(
            "paper_draft/aaai27kit/AuthorKit27/"
            "ReproducibilityChecklist.tex"
        ),
    )
    parser.add_argument(
        "--responses",
        default="reproducibility_checklist_responses_memory.json",
    )
    parser.add_argument(
        "--out",
        default="paper_draft/antmill_memory_reproducibility_checklist.tex",
    )
    parser.add_argument(
        "--report",
        default=(
            "paper_draft/generated/revision_results/"
            "reproducibility_checklist_report.json"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    result = build_reproducibility_checklist(
        template_path=Path(args.template),
        responses_path=Path(args.responses),
        output_tex_path=Path(args.out),
        report_path=Path(args.report),
    )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
