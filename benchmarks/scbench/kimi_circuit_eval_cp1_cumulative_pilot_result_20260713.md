# Kimi Circuit Eval Checkpoint-1 Pilot

Date: 2026-07-13

## Decision

The pilot is invalid for a treatment-effect interpretation because experience
transfer never activated. It was stopped immediately after layer 1 to avoid
spending the remaining treatment and control budget.

## Completed Evidence

| Worker | Checkpoint-1 Core | Functionality | Error |
|---|---:|---:|---:|
| 1 | 8/9 | 15/15 | 12/12 |
| 2 | 8/9 | 15/15 | 12/12 |
| 3 | 8/9 | 15/15 | 12/12 |

All three evaluations used test hash
`46a898e5ca98098b14725e27e2cb0eb70ab9b68c25e9efe8829bf5984471e8a9`.
There were no infrastructure failures, completed-layer stderr files were empty,
and assistant trajectories contained no prohibited benchmark access.

## Gate Audit

| Frozen gate | Result | Evidence |
|---|---|---|
| Source activation | Fail | No worker passed all 9 Core tests |
| Target consistency | Pass | Every result was checkpoint-1 Core total 9 |
| Completed-layer integrity | Pass | One hash, no infrastructure failure, no access violation |
| Treatment direction | Not evaluated | No experience source existed |

The three layer-2 runners had just started when the experiment was cancelled.
Their cancellation stderr is orchestration output, not a benchmark failure.
No layer-2 score and no no-transfer arm is used in analysis.

## Interpretation

This run is neither positive nor negative evidence about experience-induced
degradation. Without a strict source, `cumulative_success` would be identical
to `no_transfer`; continuing would only manufacture an empty treatment
contrast. The candidate is therefore closed under the pre-registered
source-activation rule.

