# GLM-5 cfgpipe Self-Report Acceptance Depth-10 Audit

Date: 2026-07-14

## Verdict

This is a clean negative result. GLM-5 stayed perfectly flat for all ten
layers under the same `cfgpipe` task, three-worker MOA topology, frozen
bootstrap sources, and self-report-only admission rule.

Every one of the 30 worker outcomes scored 4/4 Core and 34/37 overall. There
were no runner stderr files and no model-query guard failures. Layer 10
received 30 references, 242,255 experience characters, and 1,394,163 input
tokens, which is 11.46x the matching no-transfer control input load.

## Curve

| Layer | References | Mean Core | Mean All Tests |
|---:|---:|---:|---:|
| 1 | 3 | 1.000 | .919 |
| 2 | 6 | 1.000 | .919 |
| 3 | 9 | 1.000 | .919 |
| 4 | 12 | 1.000 | .919 |
| 5 | 15 | 1.000 | .919 |
| 6 | 18 | 1.000 | .919 |
| 7 | 21 | 1.000 | .919 |
| 8 | 24 | 1.000 | .919 |
| 9 | 27 | 1.000 | .919 |
| 10 | 30 | 1.000 | .919 |

## Interpretation

This falsifies the broad version of the iteration hypothesis. More layers and
more accumulated context are not sufficient by themselves to force degradation.

The valid Kimi result remains a late-tail-risk signal: Kimi was stable through
layer 7 and produced a real 0/37 self-reported failure at layer 8. But GLM-5
shows that the effect is model-dependent and not a universal consequence of
the MOA/self-report mechanism on this task.

The paper line should therefore be narrowed to verifier strength and
model-dependent tail risk, unless a clean Kimi or deepseek depth-10 run later
shows post-trigger persistence without quota or API contamination.
