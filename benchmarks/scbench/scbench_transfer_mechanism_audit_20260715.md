# SCBench Transfer Mechanism Audit

Generated from frozen manifests and local snapshots on 2026-07-15.

## Experience and admission

- Artifact body: worker/layer header, the trailing part of the final four assistant steps, and a source-snapshot excerpt.
- Per-artifact and per-recipient-source cap: 12,000 characters.
- Self-report regex: `\b(pass|passes|passed|works|working|success|successful|correct|verify|verified)\b` with `re.IGNORECASE`.
- The self-report gate scans all assistant text. It does not read the external SCBench evaluator.
- The stricter local proxy additionally requires at least three successful environment commands.

## Summary sizes

| Run | Summary chars (median, range) | Received chars (median, range) | Input tokens (median, range) |
|---|---:|---:|---:|
| cfgpipe-cumulative-main | 10479 (6449-12000) | 193858 (25934-367725) | 380926 (89269-703436) |
| cfgpipe-bounded-control | 10611 (7604-12000) | 31706 (25934-32082) | 76006 (61953-121479) |

## Alignment

| Run | Exact primary match after L1 | Mean max source-line Jaccard | Mean summary-line recall | First single primary impl. |
|---|---:|---:|---:|---:|
| cfgpipe-cumulative-main | 0.879 | 0.965 | 0.976 | L5 |
| cfgpipe-bounded-control | 1.000 | 1.000 | 1.000 | L2 |

## Layer-4 bounded-context audit

- Whole-workspace snapshots: 2 unique.
- Primary `cfgpipe.py` implementations: 1 unique.
- Therefore the apparent layer-4 workspace re-diversification is not a primary-implementation re-diversification; it is caused by an extra non-entrypoint workspace file.

## Files

- JSON audit: `benchmarks\scbench\scbench_transfer_mechanism_audit_20260715.json`
- Size table: `paper_draft\generated\moa_paper\experience_summary_sizes.csv`
- Alignment table: `paper_draft\generated\moa_paper\experience_copy_alignment.csv`
- Layer table: `paper_draft\generated\moa_paper\implementation_alignment_layers.csv`
