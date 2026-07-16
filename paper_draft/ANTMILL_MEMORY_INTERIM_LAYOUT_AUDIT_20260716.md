# AntMill Memory Paper Interim Layout Audit

This is an outcome-neutral layout stress test, not a final submission audit.
It uses the complete generated-table fixture retained from the revision
pipeline and the current isolated memory-paper sources.

## Artifact

- Source: `paper_draft/antmill_memory_aaai27_en.tex`
- Fixture workspace:
  `tmp/revision_layout_contributions_20260715_2355`
- PDF:
  `tmp/revision_layout_contributions_20260715_2355/paper_draft/antmill_memory_aaai27_en.pdf`
- PDF SHA-256:
  `43236bd08bcda152594f1c6bf2f676458efaa2982ec1cd9aca6b8ac40f2d26f6`

## Checks

- Compile sequence: `pdflatex`, `bibtex`, `pdflatex`, `pdflatex`
- Page count: 8
- Overfull boxes: 0
- Underfull boxes: 14
- References begin on page 7 and continue on page 8.
- Automated raster and PDF-character bounds checks passed on all 8 pages.
- All 8 rendered pages were visually inspected at 150 DPI.
- No clipping, incoherent overlap, illegible figure or table, or
  caption-content mismatch was observed.
- Hash-bound visual audit:
  `tmp/revision_layout_contributions_20260715_2355/main_render_current3/render_audit_complete.json`

This fixture contains synthetic placeholder contrasts and is excluded from
behavioral interpretation. The final paper, supplement, and checklist must be
recompiled and audited again after the formal evidence and claim decisions are
complete.
