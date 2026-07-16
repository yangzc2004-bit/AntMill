# DeepSeek cfgpipe Self-Report Acceptance Depth-10 Audit

Date: 2026-07-14

## Verdict

This valid DeepSeek-V4-Flash run shows **intermittent catastrophic tail risk**
but not a sustained degradation curve.

Two of 30 worker outcomes collapsed to 0/37 while still self-reporting
success and being admitted into the cumulative experience pool. The failures
occurred at layers 2 and 7. Both were followed by immediate recovery: every
worker in layers 8-10 scored 4/4 Core and 34/37 overall.

Iteration depth therefore mattered for exposing false-success events, but ten
layers, 30 references, and roughly 94k prompt tokens per first terminal call
were not sufficient to produce a death spiral.

## Curve

| Layer | References | Mean Core | Mean All Tests | 0/37 Workers |
|---:|---:|---:|---:|---:|
| 1 | 3 | 1.000 | .910 | 0 |
| 2 | 6 | .667 | .604 | 1 |
| 3 | 9 | 1.000 | .910 | 0 |
| 4 | 12 | 1.000 | .919 | 0 |
| 5 | 15 | 1.000 | .919 | 0 |
| 6 | 18 | 1.000 | .919 | 0 |
| 7 | 21 | .667 | .613 | 1 |
| 8 | 24 | 1.000 | .919 | 0 |
| 9 | 27 | 1.000 | .919 | 0 |
| 10 | 30 | 1.000 | .919 | 0 |

## Catastrophic Events

Layer 2 worker 1 made 12 model calls and passed eight local validation
commands, but its final snapshot scored 0/37 externally. It self-reported
success, so self-report-only admission propagated the artifact. Layer 3
nevertheless recovered.

Layer 7 worker 3 is the sharper mechanism example. It made one model call,
ran zero validation commands, created no snapshot files, and declared that
the implementation was complete and all tests passed. Its unchanged snapshot
scored 0/37, but the self-report gate admitted its 292-character artifact.
Layers 8-10 all recovered.

## Registered Decision

The run passes the validity, tail-trigger, and complexity gates. It fails the
post-trigger, terminal, and terminal-Core requirements, so the preregistered
sustained-degradation claim is not supported.

Layer 10 received 30 references and 310,994 experience characters. Its
1,248,397 input tokens were 10.26x the matching no-transfer control load.
Across the full run, the model consumed 9,585,709 input tokens and 224,073
output tokens.

## Why More Raw-Append Layers Are Unlikely to Help

The layer-7 failed artifact contributed only 292 of the 244,879 experience
characters received at layer 8, about 0.12%. Even both failed artifacts
together represented only 2.79% of that context. Under append-all
assimilation, individual errors are increasingly diluted by successful
artifacts rather than preferentially amplified.

The exact arm should therefore not be extended mechanically to 15 or 20
layers. The next controlled experiment should keep the model, task, external
evaluator, recipient blinding, and self-report gate fixed, while adding a
realistic MOA manager-synthesis feedback condition that compresses accepted
outputs into a privileged shared lesson. The informative comparison is:

1. no transfer;
2. cumulative raw append;
3. manager-synthesized self-report feedback.

That experiment directly tests amplification. More iterations of the current
diluting topology mainly add cost and opportunities for isolated failures.
