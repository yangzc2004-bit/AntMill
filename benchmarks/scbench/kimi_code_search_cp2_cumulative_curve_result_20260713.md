# Kimi Code Search Cumulative-Feedback Result

## Bottom Line

The fixed-topology cumulative verified-experience stress policy activated
exactly as frozen, but it did not produce a performance-degradation curve.

All three arms retained a mean Core score of 1.0 and 3/3 full-Core workers at
every layer. The result is a clean negative finding: accumulated verified
experience substantially increased inference context, but `code_search`
checkpoint 2 was too easy for that pressure to reduce correctness.

## Layer Results

| Mode | L1 Core | L2 Core | L3 Core | L4 Core | Received results L2/L3/L4 |
|---|---:|---:|---:|---:|---:|
| `no_transfer` | 1.000 | 1.000 | 1.000 | 1.000 | 0 / 0 / 0 |
| `source_success` | 1.000 | 1.000 | 1.000 | 1.000 | 3 / 3 / 3 |
| `cumulative_success` | 1.000 | 1.000 | 1.000 | 1.000 | 3 / 6 / 9 |

The cumulative arm's received experience grew from 28,916 characters at layer
2 to 51,977 at layer 3 and 75,154 at layer 4.

## Complexity Effects

| Layer | Source-success input tokens | Cumulative input tokens | Ratio |
|---:|---:|---:|---:|
| 2 | 727,777 | 847,629 | 1.165x |
| 3 | 639,366 | 1,243,810 | 1.945x |
| 4 | 670,511 | 1,469,892 | 2.192x |

At layer 4, cumulative-success used 4.696x the input tokens of no-transfer
(1,469,892 versus 313,009) while producing the same Core score.

## Frozen-Criteria Audit

| Criterion | Result | Evidence |
|---|---|---|
| Control headroom | Pass | Both controls retained 1.0 mean Core at layer 4 |
| Cumulative activation | Pass | Mean sources grew 3 to 6 to 9 |
| Integrity | Pass | One checkpoint-2 test hash, no infrastructure failures or prohibited access |
| Primary degradation | Fail | Cumulative L4 was 0.0 below either control, not at least 0.20 |
| Within-arm decline | Fail | Cumulative Core remained 1.0 |
| Curve shape | Fail | No transition was strictly decreasing |
| Complexity support | Pass | L4 cumulative input exceeded source-success by 119.2% |

Because the primary, within-arm, and curve-shape criteria failed, this run must
not be described as a degradation curve.

## Integrity Audit

- 36 checkpoint-2 evaluations used test collection hash
  `6e4457d36d30cf9405ff2006c59ebc9a2c58b9e109af3f1d49ca3addb3c4d719`.
- All 36 checkpoint-2 evaluations passed 5/5 Core tests with exit code 0.
- No worker output reported an infrastructure failure.
- All runner stderr files were empty.
- No assistant action in the cumulative arm referenced prohibited benchmark
  or evaluation paths.

## Research Decision

Retain this run as evidence of coordination-cost amplification without an
accuracy effect. Do not add more layers to this easy task merely to reach a
context-window failure. The next stress run should use a calibrated task whose
independent control performance is non-zero but below ceiling.
