# Kimi Database Migration Strict Pilot

## Decision

The two-layer go/no-go pilot completed. Strict verified-success transfer
activated, but the frozen directional performance gate did not pass. Do not
expand this exact run to layer 3 or additional repeats.

The first launch attempt is excluded because the Docker Desktop Linux engine
was not running. It failed before model inference. The official run is:

`runs_scbench_moa_kimi_database_migration_cp2_strict_pilot_20260713_rerun1`

## Results

| Arm | Layer | Worker Core scores | Mean Core | Full-Core workers |
|---|---:|---|---:|---:|
| source_success | 1 | 0/3, 3/3 | 0.500 | 1 |
| source_success | 2 | 0/3, 0/3 | 0.000 | 0 |
| no_transfer | 1 | 2/3, 3/3 | 0.833 | 1 |
| no_transfer | 2 | 0/3, 0/3 | 0.000 | 0 |

The source-success treatment was active: both layer-2 workers received one
prior result containing 4,000 experience characters from a layer-1 worker
with 3/3 Core.

## Layer-2 Cost Effect

Compared with no transfer, source-success transfer produced:

- 94,141 more input tokens, or +26.87%;
- 8,279 more output tokens, or +27.18%;
- 79.77 more mean worker seconds, or +19.10%;
- no Core-score difference and no full-Core-worker difference.

This is a clean signal of coordination-cost amplification, but not a
performance-degradation signal because both layer-2 arms scored 0/3.

## Source Qualification

The transferred source passed all 3 Core tests but had pytest exit code 1. It
failed three non-Core tests:

- `test_column_missing_for_drop`;
- `test_backfill_with_numeric_constant`;
- `test_migration_rolls_back_on_failure`.

The source must therefore be described as locally Core-verified, not globally
correct or full-pass.

## Integrity Audit

All eight checkpoint-2 evaluations used the same test collection hash:

`068b8d049eaac830fd92be1fb6110a93d421ef46ae5101d1d538ca370f759c32`

The official run had no infrastructure failures, no non-empty runner stderr
logs, and no agent actions that accessed prohibited benchmark paths.

## Interpretation

The frozen gate required treatment activation and a non-zero layer-2
performance difference before expansion. Activation succeeded, but the
performance difference was zero. This run should be retained as systems-cost
evidence and should not be used alone to claim accuracy degradation.
