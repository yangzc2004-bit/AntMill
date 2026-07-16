# Paper Correction Ledger

This append-only ledger records manuscript and public-document corrections
identified by evidence audits. Entries remain open until the corresponding
text is changed, checked against frozen artifacts, and cited to an immutable
evidence record.

## 2026-07-16 - Shared-append protocol semantics

Status: open; no manuscript text changed in this audit step.

Evidence:

- `sec/maze_alpha.py:1219-1235` performs same-kind lexical duplicate lookup,
  retains the existing item, and increments its vote.
- `sec/expel_ops.py:178-190` applies the fixed `0.80` threshold.
- Beta E2 append memory audits record 300
  `reviewer_append:agree` merges among 800 candidate writes across five seeds:
  `runs_maze_beta_e2/n4_gt_false_seed{0..4}_e2_shared_append_ga/memory_audit.json`.
- The frozen mechanism values remain 25.4 distinct injected for append and
  11.0 for consolidated, or `25.4 / 11.0 = 2.31x`.

Required corrections:

- `paper_draft/antmill_full_en.tex:206-207`: replace "shared but never
  merged" with a definition that states mechanical lexical near-duplicate
  agreement without reviewer-selected pool evolution.
- `README.md:86` and `README.md:334`: replace "shared append-only" with
  "shared append/agree" or equivalent precise wording.
- `paper_draft/antmill_full_en.tex:292-302`: restate the `2.31x` result as
  additional compression under reviewer-selected evolution on top of the
  duplicate rule shared by both arms.
- `paper_draft/antmill_memory_aaai27_en.tex:410-420`,
  `paper_draft/beta_results_en.tex:118-126`, and
  `paper_draft/beta_results_zh.tex:104-106`: align the E2 mechanism narrative
  with the corrected arm semantics.
- `prereg_phase_beta.md:294-297`,
  `runs_maze_beta_e2_evidence/e2_verdict.md:29`, and
  `runs_maze_beta_e2_evidence/memory_audit_findings.md:6`: preserve the
  historical record but add an explicit correction note wherever these files
  are quoted or promoted as current protocol descriptions.

Target interpretation:

The corrected E2 contrast is mechanical lexical deduplication at cap 80
versus the same mechanical rule plus reviewer-selected `ADD`, `EDIT`,
`UPVOTE`, and `DOWNVOTE` pool evolution. The `2.31x` ratio is not evidence for
no merging versus merging; it is evidence for incremental strategy-supply
compression associated with reviewer selection under the executed protocol.
