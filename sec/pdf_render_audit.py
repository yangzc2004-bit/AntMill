from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
from PIL import Image, ImageStat
from pypdf import PdfReader


VISUAL_CHECK_NAMES = [
    "all_pages_rendered",
    "no_text_or_table_clipping",
    "no_overlapping_elements",
    "figures_and_tables_legible",
    "captions_match_content",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdftoppm() -> str:
    executable = shutil.which("pdftoppm.exe")
    if executable:
        return executable
    fallback = shutil.which("pdftoppm")
    if fallback and not fallback.lower().endswith(".cmd"):
        return fallback
    raise FileNotFoundError("A working pdftoppm executable was not found.")


def _image_metrics(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        histogram = gray.histogram()
        total = max(sum(histogram), 1)
        nonwhite = sum(histogram[:250]) / total
        stats = ImageStat.Stat(gray)
        mask = gray.point(lambda value: 255 if value < 245 else 0)
        bbox = mask.getbbox()
        if bbox:
            left, top, right, bottom = bbox
            margins = {
                "left": left,
                "top": top,
                "right": rgb.width - right,
                "bottom": rgb.height - bottom,
            }
        else:
            margins = {
                "left": rgb.width,
                "top": rgb.height,
                "right": rgb.width,
                "bottom": rgb.height,
            }
        return {
            "path": str(path),
            "sha256": _sha256(path),
            "width": rgb.width,
            "height": rgb.height,
            "mean_gray": float(stats.mean[0]),
            "stddev_gray": float(stats.stddev[0]),
            "nonwhite_fraction": float(nonwhite),
            "content_bbox": list(bbox) if bbox else None,
            "content_margins_px": margins,
            "nonblank": bool(nonwhite >= 0.0001 and stats.stddev[0] >= 0.5),
            "content_inside_raster": bool(
                bbox
                and min(margins.values()) >= 2
            ),
        }


def _pdf_text_metrics(pdf_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            chars = page.chars
            bounds_pass = all(
                float(char.get("x0", 0.0)) >= -0.5
                and float(char.get("x1", page.width)) <= float(page.width) + 0.5
                and float(char.get("top", 0.0)) >= -0.5
                and float(char.get("bottom", page.height)) <= float(page.height) + 0.5
                for char in chars
            )
            text = page.extract_text() or ""
            rows.append(
                {
                    "page": index,
                    "width_points": float(page.width),
                    "height_points": float(page.height),
                    "character_count": len(chars),
                    "text_length": len(text.strip()),
                    "text_present": bool(text.strip()),
                    "character_bounds_pass": bounds_pass,
                }
            )
    return rows


def render_pdf_audit(
    *,
    pdf_path: Path,
    out_dir: Path,
    dpi: int = 180,
) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    if dpi < 72:
        raise ValueError("DPI must be at least 72.")
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved_out = out_dir.resolve()
    for path in out_dir.glob("page-*.png"):
        if path.resolve().parent != resolved_out:
            raise RuntimeError(f"Refusing to remove image outside output directory: {path}")
        path.unlink()

    page_count = len(PdfReader(str(pdf_path)).pages)
    prefix = out_dir / "page"
    completed = subprocess.run(
        [
            _pdftoppm(),
            "-png",
            "-r",
            str(dpi),
            str(pdf_path),
            str(prefix),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "pdftoppm failed:\n" + completed.stdout[-2000:] + completed.stderr[-4000:]
        )
    images = sorted(
        out_dir.glob("page-*.png"),
        key=lambda path: int(path.stem.rsplit("-", 1)[-1]),
    )
    image_rows = [_image_metrics(path) for path in images]
    text_rows = _pdf_text_metrics(pdf_path)
    dimensions = {(row["width"], row["height"]) for row in image_rows}
    automated_checks = {
        "page_count_positive": page_count > 0,
        "rendered_page_count_matches": len(images) == page_count,
        "all_rendered_pages_nonblank": bool(image_rows)
        and all(bool(row["nonblank"]) for row in image_rows),
        "all_content_inside_raster": bool(image_rows)
        and all(bool(row["content_inside_raster"]) for row in image_rows),
        "consistent_page_dimensions": len(dimensions) == 1,
        "text_page_count_matches": len(text_rows) == page_count,
        "all_pages_have_text": bool(text_rows)
        and all(bool(row["text_present"]) for row in text_rows),
        "all_pdf_characters_in_page_bounds": bool(text_rows)
        and all(bool(row["character_bounds_pass"]) for row in text_rows),
    }
    result = {
        "status": (
            "automated_checks_pass"
            if all(automated_checks.values())
            else "automated_checks_failed"
        ),
        "pdf": str(pdf_path),
        "pdf_sha256": _sha256(pdf_path),
        "dpi": dpi,
        "page_count": page_count,
        "rendered_page_count": len(images),
        "renderer": _pdftoppm(),
        "automated_checks": automated_checks,
        "pages": image_rows,
        "text_pages": text_rows,
        "visual_checks": {name: False for name in VISUAL_CHECK_NAMES},
    }
    draft_path = out_dir / "render_audit_draft.json"
    draft_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def finalize_pdf_audit(
    *,
    draft_path: Path,
    out_path: Path,
    visual_confirmations: dict[str, bool],
) -> dict[str, Any]:
    draft = json.loads(draft_path.read_text(encoding="utf-8-sig"))
    if set(visual_confirmations) != set(VISUAL_CHECK_NAMES):
        raise ValueError("Visual confirmation keys do not match the required checklist.")
    if not all(bool(value) for value in visual_confirmations.values()):
        raise ValueError("Every visual check must be explicitly confirmed.")
    if draft.get("status") != "automated_checks_pass":
        raise RuntimeError("Automated PDF checks have not passed.")
    pdf_path = Path(str(draft.get("pdf", "")))
    if not pdf_path.exists() or _sha256(pdf_path) != draft.get("pdf_sha256"):
        raise RuntimeError("PDF changed after rendering; render it again.")
    pages = draft.get("pages", [])
    if len(pages) != int(draft.get("page_count", -1)):
        raise RuntimeError("Rendered page manifest is incomplete.")
    for page in pages:
        image_path = Path(str(page.get("path", "")))
        if not image_path.exists() or _sha256(image_path) != page.get("sha256"):
            raise RuntimeError(f"Rendered page changed or is missing: {image_path}")

    result = dict(draft)
    result["status"] = "visual_audit_complete"
    result["visual_checks"] = {
        name: bool(visual_confirmations[name])
        for name in VISUAL_CHECK_NAMES
    }
    result["finalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["source_draft"] = str(draft_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a PDF for inspection and freeze a hash-bound visual audit."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render")
    render.add_argument(
        "--pdf",
        default="paper_draft/antmill_memory_aaai27_en.pdf",
    )
    render.add_argument("--out-dir", default="tmp/pdfs/antmill_memory_final")
    render.add_argument("--dpi", type=int, default=180)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument(
        "--draft",
        default="tmp/pdfs/antmill_final/render_audit_draft.json",
    )
    finalize.add_argument(
        "--out",
        default="paper_draft/generated/revision_results/final_render_audit.json",
    )
    for name in VISUAL_CHECK_NAMES:
        finalize.add_argument(
            "--confirm-" + name.replace("_", "-"),
            action="store_true",
            dest=name,
        )
    return parser


def main(argv: list[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    if args.command == "render":
        result = render_pdf_audit(
            pdf_path=Path(args.pdf),
            out_dir=Path(args.out_dir),
            dpi=args.dpi,
        )
    else:
        result = finalize_pdf_audit(
            draft_path=Path(args.draft),
            out_path=Path(args.out),
            visual_confirmations={
                name: bool(getattr(args, name))
                for name in VISUAL_CHECK_NAMES
            },
        )
    print(result["status"])
    return result


if __name__ == "__main__":
    main()
