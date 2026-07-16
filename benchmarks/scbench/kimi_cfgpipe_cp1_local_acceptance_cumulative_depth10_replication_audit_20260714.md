# Kimi cfgpipe Local-Acceptance Depth-10 Replication Audit

Date: 2026-07-14

## Verdict

Too few iterations is not the main explanation for the missing degradation
curve. We ran two independent ten-layer Kimi-K2.6 arms. Their layer-10 input
loads reached 9.7x and 12.1x the matching no-transfer control, yet the frozen
terminal degradation criterion failed in the independent confirmation run.

What did replicate was narrower and still important: high accumulated
coordination context repeatedly produced catastrophic individual failures.
The exploratory run collapsed at layers 5 and 10 after layer 4; the independent
run collapsed at layers 6 and 9. Every collapse was followed by recovery.

## Curves

| Run | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9 | L10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Exploratory, Core | .667 | 1.000 | 1.000 | 1.000 | .333 | 1.000 | 1.000 | 1.000 | 1.000 | .667 |
| Exploratory, all | .613 | .919 | .919 | .919 | .306 | .919 | .919 | .919 | .919 | .613 |
| Confirmatory, Core | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | .667 | 1.000 | 1.000 | .667 | 1.000 |
| Confirmatory, all | .919 | .919 | .919 | .919 | .919 | .613 | .919 | .919 | .613 | .919 |

Across layers 5-10, four of twelve layer events contained at least one 0/37
worker. Five of 36 worker-layer outcomes were 0/37. The matching no-transfer
control had no zero worker among its six layer-4 and layer-5 outcomes.

## Why The Curve Recovered

All five post-layer-4 zero workers had:

- zero successful environment commands;
- no output snapshot;
- a textual claim that the task or tests had succeeded.

The frozen local proxy required both a success claim and at least three
successful commands. It therefore rejected every catastrophic output. The
large context could trigger a failure, but the failure was not added to the
shared experience bundle, allowing the next layer to recover.

This is a mechanistic result, not an infrastructure artifact: the benchmark
hash, target size, bootstrap sources, model, worker count, and step limit were
held fixed, and no runner infrastructure failure explains the zero scores.

## Scientific Interpretation

The present evidence supports **complexity-induced intermittent tail
collapse**, not a monotonic death spiral. Increasing depth was useful because
it exposed a one-in-three post-layer-4 collapse-layer rate across two runs,
but iteration count by itself did not make the low state persistent.

The clean next experiment is a verifier-strength ablation. Keep everything
else fixed and accept a source when the agent only self-reports success. This
is realistic for orchestrators that receive a subagent's textual completion
report without executing an independent smoke check. It tests whether
propagating the observed failed trajectories converts intermittent collapse
into sustained degradation.

If that arm degrades, the claim must be phrased as locally accepted or
self-certified experience amplification, not globally correct experience
amplification.
