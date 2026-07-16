# Kimi Database Migration Three-Replicate Result

## Bottom Line

All three planned engineering replicates completed. Two replicates activated
strict verified-success transfer; the third produced no successful source and
therefore delivered no treatment.

The experiment supports a token-cost increase, but it does not support a
performance-degradation claim.

## Replicate Results

| Replicate | Treatment active | Source-success L2 | No-transfer L2 | L2 difference |
|---:|---|---:|---:|---:|
| 1 | Yes | 0.000 | 0.000 | 0.000 |
| 2 | Yes | 0.500 | 0.000 | +0.500 |
| 3 | No | 0.000 | 0.000 | Excluded |

Replicate 3 is excluded from treatment-effect interpretation because no
source-success layer-1 worker passed all Core tests. Its layer-2 workers
received zero prior results and zero experience characters.

Across the two active replicates:

- mean layer-2 Core difference: +0.250;
- mean difference-in-differences: +0.4167;
- mean full-Core-worker difference: +0.500;
- negative performance differences: 0 of 2.

The observed performance direction is non-negative and is positive in one
replicate. This setting therefore contradicts, rather than supports, the
proposed degradation mechanism.

## Cost Effects

Across the two active replicates, source-success transfer changed layer-2
resource usage by:

- input tokens: mean paired increase of 19.08%;
- output tokens: mean paired increase of 17.46%;
- mean duration: mean paired increase of 8.60%.

Input and output tokens increased in both active replicates. Duration increased
in replicate 1 and decreased slightly in replicate 2. The defensible finding is
therefore token-cost amplification, not a stable latency increase.

## Verification Scope

The two transferred sources passed 3/3 Core tests but were not globally
full-pass solutions:

- replicate 1 source: 59/62 total tests;
- replicate 2 source: 60/62 total tests.

They should be described as locally Core-verified experiences.

## Integrity Audit

All 24 checkpoint-2 evaluations used the same test collection hash:

`068b8d049eaac830fd92be1fb6110a93d421ef46ae5101d1d538ca370f759c32`

There were no infrastructure failures, non-empty runner stderr logs, or agent
actions accessing prohibited benchmark paths.

## Research Decision

Do not present this experiment as a degradation curve. It is valid evidence
that verified-experience transfer adds inference-context cost without a
reliable accuracy gain. Demonstrating a death-spiral mechanism requires a new,
pre-frozen stress condition rather than extending or selectively reporting
this result.
