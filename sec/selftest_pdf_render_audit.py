from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .pdf_render_audit import (
    VISUAL_CHECK_NAMES,
    finalize_pdf_audit,
    render_pdf_audit,
)


def _make_pdf(path: Path, text: str) -> None:
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise FileNotFoundError("pdflatex is required for the PDF audit selftest.")
    tex_path = path.with_suffix(".tex")
    tex_path.write_text(
        "\n".join(
            [
                "\\documentclass{article}",
                "\\begin{document}",
                text,
                "\\begin{center}",
                "\\fbox{PDF render audit fixture}",
                "\\end{center}",
                "\\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            pdflatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-jobname={path.stem}",
            tex_path.name,
        ],
        cwd=path.parent,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout[-4000:] + completed.stderr[-2000:])


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="antmill-pdf-audit-") as raw:
        root = Path(raw)
        pdf_path = root / "paper.pdf"
        _make_pdf(pdf_path, "Submission-grade PDF audit fixture")
        draft = render_pdf_audit(pdf_path=pdf_path, out_dir=root / "render", dpi=120)
        assert draft["status"] == "automated_checks_pass", draft["automated_checks"]
        assert draft["page_count"] == 1
        assert draft["rendered_page_count"] == 1
        finalized = finalize_pdf_audit(
            draft_path=root / "render" / "render_audit_draft.json",
            out_path=root / "final_render_audit.json",
            visual_confirmations={name: True for name in VISUAL_CHECK_NAMES},
        )
        assert finalized["status"] == "visual_audit_complete"

        _make_pdf(pdf_path, "Changed after rendering")
        try:
            finalize_pdf_audit(
                draft_path=root / "render" / "render_audit_draft.json",
                out_path=root / "stale.json",
                visual_confirmations={name: True for name in VISUAL_CHECK_NAMES},
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("A PDF changed after rendering must be rejected.")
    print("selftest_pdf_render_audit OK")


if __name__ == "__main__":
    main()
