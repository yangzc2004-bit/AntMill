from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .reproducibility_checklist import build_reproducibility_checklist


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-checklist-") as raw:
        root = Path(raw)
        template = root / "template.tex"
        template.write_text(
            "\n".join(
                [
                    "\\question{Question one}{(yes/no)}",
                    "Type your response here",
                    "\\question{Question two}{(yes/partial/no/NA)}",
                    "Type your response here",
                ]
            ),
            encoding="utf-8",
        )
        responses = root / "responses.json"
        _write_json(
            responses,
            {
                "status": "finalized",
                "template_sha256": _sha256(template),
                "responses": [
                    {
                        "question": "Question one",
                        "answer": "yes",
                        "evidence": "fixture",
                    },
                    {
                        "question": "Question two",
                        "answer": "NA",
                        "evidence": "fixture",
                    },
                ],
            },
        )
        result = build_reproducibility_checklist(
            template_path=template,
            responses_path=responses,
            output_tex_path=root / "out.tex",
            report_path=root / "report.json",
        )
        assert result["status"] == "checklist_ready"
        assert result["question_count"] == 2
        assert "Type your response here" not in (root / "out.tex").read_text(
            encoding="utf-8"
        )

        broken = json.loads(responses.read_text(encoding="utf-8"))
        broken["responses"][0]["answer"] = "partial"
        _write_json(responses, broken)
        try:
            build_reproducibility_checklist(
                template_path=template,
                responses_path=responses,
                output_tex_path=root / "broken.tex",
                report_path=root / "broken.json",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid checklist answer should be rejected.")
    print("selftest_reproducibility_checklist OK")


if __name__ == "__main__":
    main()
