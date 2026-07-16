# Kimi cfgpipe Self-Report Acceptance Depth-8 Audit

Date: 2026-07-14

## Verdict

For Kimi-K2.6 on `cfgpipe`, the valid run now supports a sharper answer:
iteration depth mattered for exposing **late tail collapse**, but it still does
not yet confirm a sustained death spiral.

Layers 1-7 were perfectly flat: every worker scored 34/37 tests and 4/4 Core.
At layer 8, one worker dropped to 0/37, so the layer mean fell from .919 to
.613. This was a real agent run with model calls and no infrastructure failure.
The failed worker self-reported success, issued zero successful commands, and
would be admitted by self-report-only acceptance while being rejected by the
stronger completion-and-smoke local proxy.

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
| 8 | 24 | .667 | .613 |

Layer 8 received 245,511 experience characters and used 5.53x the matching
no-transfer control input-token load.

## Invalid Extension

The exact-arm extension to layers 9 and 10 is invalid for scientific
interpretation. Kimi coding quota was exhausted at layer 9. The logs show a
403 usage-limit/quota error, zero model steps, zero input/output tokens, and
an empty snapshot that evaluated as 0/37.

This is not semantic failure propagation. I added a wrapper-level guard in
`sec/scbench_miniswe.py` so future runs detect zero-step model-query failures
with API/quota/rate-limit logs and stop instead of silently recording 0/37.

## Interpretation

The strongest valid statement is:

Self-report-only experience admission can remain stable for many layers and
then produce a late catastrophic tail failure once the shared context becomes
large. The failed layer-8 trajectory is exactly the kind of source that weaker
MAS admission rules would propagate.

The sustained death-spiral claim still needs a clean post-trigger observation:
either restore Kimi quota and run a fresh preregistered depth-10 replication,
or run the same frozen mechanism on an available endpoint/model such as GLM-5
or deepseek-v4-flash.
