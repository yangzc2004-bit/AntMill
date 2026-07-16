# MoA AAAI Draft: Reproducibility and QA Record

Date: 2026-07-15

## Frozen Scientific Conclusion

The frozen evidence supports a stability-diversity and verification trade-off:
blinded shared experience in layered parallel agents can repeatedly create an
implementation attractor without sustained score collapse. Exact lock-in recurs
in the frozen main run and two independent retrospective trajectory audits. A
prospectively frozen fixed-three-reference control also reaches exact lock-in,
so cumulative history growth is not necessary in the tested setting. Local
admission blocks the observed zero-command false completions, but its benefit
depends on a threshold that can also reject externally strong solutions.

The manuscript therefore does not claim:

- monotonic degradation with increasing layer depth;
- catastrophic tails unique to experience transfer;
- a universal harmful effect from recursive manager synthesis;
- a generally optimal command-count admission threshold;
- exchangeability of layers, tasks, models, or providers.

## Frozen Evidence

- Main run: Kimi-K2.6 MaaS, `cfgpipe` checkpoint 1, 12 layers, 3 workers,
  3 transfer arms, and 108 hidden external evaluations.
- Main audit:
  `benchmarks/scbench/kimi_maas_cfgpipe_cp1_depth12_three_arm_confirmation_audit_20260715.json`
- Replication and bounded-control audit:
  `benchmarks/scbench/kimi_cfgpipe_lockin_replication_audit_20260715.json`
- Prospective bounded-control freeze:
  `benchmarks/scbench/kimi_maas_cfgpipe_cp1_bounded_context_depth6_config.freeze.json`
- Evidence manifest:
  `paper_draft/generated/moa_paper/evidence_manifest.json`
- Figure source tables:
  `paper_draft/generated/moa_paper/*.csv`
- Claim blueprint:
  `paper_draft/MOA_PAPER_BLUEPRINT_20260715.md`
- Figure contract:
  `paper_draft/FIGURE_CONTRACT_MOA_20260715.md`

The audit's failed preregistered criteria are scientific falsification results,
not software-test failures. The protocol self-test completes successfully.

## Figure QA

Figures were produced only with the selected Python/matplotlib backend:

```powershell
python paper_draft/make_moa_figures.py
```

Each figure is available as editable-text SVG, vector PDF, 600-dpi TIFF, and PNG:

- `paper_draft/figures/moa/figure1_moa_system.*`
- `paper_draft/figures/moa/figure2_depth12_lockin.*`
- `paper_draft/figures/moa/figure3_admission_boundaries.*`

All three manuscript figures were revised under one evidence-first visual
contract: Figure 1 presents the audited architecture, Figure 2 separates the
primary score trajectory from implementation, behavioral, and coordination
evidence, and Figure 3 makes the admission trade-off the hero panel while keeping
cross-run and cross-task boundaries visually subordinate.

The final PDFs were rasterized page by page with Poppler at 120 dpi and
visually inspected. Hash-bound automated and manual audit records are stored in
`paper_draft/generated/moa_paper/*_render_audit.json`. No clipping, overlap,
blank figure, illegible panel label, or detached float page was observed. In the
English submission draft, Figures 1, 2, and 3 appear on pages 3, 5, and 6.

## Build and Validation

English submission draft:

```powershell
cd D:\antmill\paper_draft
latexmk -pdf -interaction=nonstopmode -halt-on-error antmill_aaai27_en.tex
```

Chinese internal-review mirror:

```powershell
cd D:\antmill\paper_draft
latexmk -xelatex -interaction=nonstopmode -halt-on-error antmill_aaai27_zh.tex
```

Validation commands:

```powershell
python -m py_compile sec/scbench_moa.py sec/run_scbench_moa_curve.py sec/resume_scbench_cumulative_arm.py scripts/audit_scbench_lockin_replications.py paper_draft/make_moa_figures.py
python scripts/audit_scbench_lockin_replications.py
python -m sec.selftest_scbench_moa
python paper_draft/make_moa_figures.py
latexmk -pdf -interaction=nonstopmode -halt-on-error antmill_aaai27_supp.tex
```

Final checks:

- English: 7 pages, 30,460 extracted characters.
- Chinese: 7 pages, 14,940 extracted characters.
- Supplement: 3 pages, 11,975 extracted characters.
- No undefined citations, undefined references, overfull boxes, fatal TeX errors,
  or unresolved `??` markers.
- Remaining underfull-box warnings are non-fatal spacing diagnostics.
- English uses the official `aaai2027.sty` submission mode and pdfLaTeX.
- The official AAAI style requires pdfTeX and cannot typeset Chinese directly.
  The Chinese PDF is therefore a two-column XeLaTeX review mirror, not the
  submission source.

## Delivered PDFs

- `output/pdf/antmill_aaai27_en.pdf`
  - SHA-256:
    `A83E7D232CA78A085E8A5D01AAA2F73BEDA69DE7C00ED8640850BC026192757D`
- `output/pdf/antmill_aaai27_zh.pdf`
  - SHA-256:
    `635A4AE1497DD85B0667726A33AED816CE8BF441DC8784D5D5A9F8D2FF864FC4`
- `output/pdf/antmill_aaai27_supp.pdf`
  - SHA-256:
    `063502F9F6E2F2F9ECCD0085B3ECEA1C4BAFCC0AA6DDF2F495D8C3AEC9899887`

## Remaining Submission Work

This deliverable is a complete anonymous first draft grounded in the current
frozen evidence. Before conference submission, replace anonymous author metadata
and confirm the final AAAI-27 policy and checklist. Additional independent seeds
or broader task coverage would strengthen uncertainty estimates, but are not
required to state the present bounded conclusion.
