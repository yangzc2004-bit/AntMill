# AAAI-27 Paper Page Budget

Status: confirmed on 2026-07-14, before completion of the Epsilon controls,
Epsilon sensitivity, Zeta exact-yoke, and MiniWoB P3 formal evaluations.

## Official Constraint

The AAAI-27 main technical track permits seven pages of technical content and
a maximum total length of nine pages. Pages 8--9 are reserved exclusively for
references. The required reproducibility checklist is uploaded separately in
its designated submission field. Supplementary material is also submitted
separately, and reviewers are not required to read it.

Official sources checked on 2026-07-14:

- https://aaai.org/conference/aaai/aaai-27/main-technical-track-call/
- https://aaai.org/conference/aaai/aaai-27/submission-instructions/

The working rule for this manuscript is therefore:

- pages 1--7: title, abstract, all technical text, figures, tables, captions,
  acknowledgments if any, and reproducibility statement;
- pages 8--9: references only;
- separate checklist PDF: completed AuthorKit reproducibility checklist;
- separate supplement: full diagnostic, sensitivity, heterogeneity,
  provenance, and artifact material.

No result is allowed into pages 8--9 merely because the references currently
leave white space there.

## Current Measurement

After the outcome-independent layout compaction on 2026-07-15, the current
`paper_draft/antmill_memory_aaai27_en.pdf` has seven total pages, with page 7
containing references only. The old shared-versus-private and Qwen result
figures were removed from the main paper, and the E4, archive-intervention,
and cross-model prose was condensed without dropping its principal estimates
or limitations. `pdfplumber` places the `References` heading on page 6 at
approximately 324.4 points on a 792-point US-letter page.

This is the pre-integration baseline: the generated mechanism-control and
MiniWoB tables are still absent. Allowing for the normal top and bottom text
margins, the current technical content occupies approximately 5.4 pages.

Budget at the current revision:

- approximate technical-content headroom before generated tables: 1.6 pages;
- planned safety reserve: at least 0.10 page;
- maximum provisional net growth before further compression: 1.5 pages;
- reference headroom: pages 7--9, but references only.

This is a layout estimate, not a license to shrink fonts, margins, line
spacing, captions, or bibliography styling.

## Full-Table Layout Probe

On 2026-07-15, a temporary full-layout probe compiled the current manuscript
with representative generated mechanism-control and MiniWoB tables. The
MiniWoB surface included both pooled consolidated/append contrasts and the six
task-family primary-effect block required by the integration specification.

The probe remained eight pages. The `References` heading began on page 7 at
approximately 643.46 points, page 8 contained references only, and the LaTeX
log contained no overfull box, undefined-control-sequence, or compilation
error. A rendered page-7 inspection found no clipping or overlap and the
tables remained legible.

This probe demonstrates that the required result surfaces can fit, but it uses
nearly the full seven-page technical allowance. Final outcome prose must
replace stale claims and limitations rather than add new paragraphs without
removing existing material.

## Integration Allocation

Fresh evidence must mostly replace or merge with existing material.

1. Mechanism-separating controls are the highest-priority main-text addition.
   Their compact table must replace or merge with an existing result table,
   not appear as an unconstrained extra table.
2. The MiniWoB formal result receives one compact pooled statement plus
   explicit task-family heterogeneity. Its visual or table should replace or
   extend the current cross-model boundary presentation when that gives a
   smaller and clearer result surface.
3. The full eight-row sensitivity envelope goes to the supplement. The main
   text receives only the preregistered envelope conclusion and the settings
   that define a material boundary.
4. Zeta exact-yoke and MMR results enter the same mechanism-control surface.
   They do not receive standalone main-text subsections.
5. Per-seed values, all 30 Zeta yoke checks, all MiniWoB family-by-seed
   effects, quality diagnostics, and provenance hashes remain in the
   supplement.
6. Abstract, contributions, limitations, and conclusion are rewritten by
   substitution. They receive no separate page allocation.

Target net additions:

| Main-text item | Net page target |
| --- | ---: |
| Mechanism controls, after replacing/merging prior material | <= 0.18 |
| MiniWoB boundary statement and compact heterogeneity display | <= 0.15 |
| Sensitivity envelope summary | <= 0.05 |
| Safety reserve | >= 0.10 |

If the evidence requires more space, the response is to remove lower-value
detail from the main text or move it to the supplement. The response is not
to exceed seven technical pages.

## Final Gates

The paper is ready for submission only when:

- the compiled PDF has no more than nine total pages;
- all technical content ends by the bottom of page 7;
- pages 8--9 contain only references;
- the standalone reproducibility checklist is complete, compiled, and ready
  for its separate OpenReview upload field;
- no font, margin, spacing, caption, or bibliography-format workaround was
  introduced;
- every generated table and figure is legible at 100% zoom;
- `sec.pdf_render_audit` and `sec.manuscript_revision_audit` pass against the
  final PDF.
