# Outcome-to-Claim Map

Status: written while Epsilon controls and MiniWoB formal evaluation were
still incomplete, before any Epsilon shared-consolidated result or cross-arm
Epsilon contrast existed.

This document constrains manuscript language after the fresh evidence arrives.
It does not add an outcome gate or change any preregistered analysis.

## Shared consolidation versus private consolidation

- If shared-consolidated minus private-consolidated loop rate has a
  seed-clustered 95% CI above zero with broadly consistent seed effects, the
  paper may state that the tested shared joint-reviewer protocol adds loop
  burden relative to the per-agent-consolidated protocol.
- If the interval includes zero, the paper must state that the fresh study
  does not isolate a shared-specific loop effect. It may still report broad
  active-memory or consolidation effects against frozen controls.
- Efficiency and success claims are made endpoint by endpoint. A loop result
  never licenses a broad shared-over-private performance claim.
- Every branch retains that the private arm uses four per-agent reviewer calls
  per training maze while the shared arm uses one joint call. The contrast
  removes cross-agent memory access but does not isolate sharing from reviewer
  prompt composition, call count, or total operation opportunity.

## Fixed cap-14 append control

- This arm is described only as fixed terminal-capacity-matched.
- It is an append/agree writer: near-duplicate additions receive deterministic
  agreement upvotes, while no joint reviewer issues `EDIT` or `DOWNVOTE`
  operations. It is not described as "never merged."
- If it remains separated from shared consolidation, final mean capacity alone
  is insufficient to explain the separation, but trajectory-level pool size
  remains open until Zeta.
- If it approaches shared consolidation, capacity remains plausible; the arm
  does not identify capacity as causal because text content and write dynamics
  differ.

## Diversity-aware MMR retrieval

- A mitigation claim requires both a successful diversity manipulation
  (increased distinct injected supply or retrieval diversity in the intended
  direction) and improved behavior on the prespecified endpoints.
- If diversity changes but behavior does not, the paper states that this MMR
  intervention is insufficient at the tested weight.
- If diversity does not change, behavioral results cannot be used to judge
  diversity-preserving retrieval generally.
- No MMR result identifies write-side compression as causal.

## Exact Zeta supply yoke

- Behavioral interpretation is allowed only if all 30 exact-size manipulation
  checks pass.
- A separated yoke and consolidated arm shows that equal candidate-pool size
  alone is insufficient for that separation.
- A similar yoke and consolidated arm keeps candidate-supply size plausible.
- Neither outcome identifies a cause because item content and write dynamics
  remain different.

## Sensitivity suite

- All k, pool-cap, reviewer-operation-budget, merge-threshold, and recency
  points are descriptive robustness checks against the frozen reference.
- The paper reports all points and does not select a best setting.
- A single reversed point bounds the protocol; it is not a tuned mitigation.
- Broad robustness language requires directionally consistent effects across
  several settings and seeds, not one significant comparison.

## MiniWoB task-family evaluation

- `p3_phenomenon_pass` with clear formal data quality permits a scoped claim
  that the combined cost and loop/stall burden replicates across the six tested
  MiniWoB families.
- `p3_not_detected_or_underpowered` is reported as no detected task-family
  replication at this design and sample size. It is not evidence that the maze
  phenomenon is impossible in real tasks.
- Any formal quality warning is resolved or reported as not evaluable before
  behavioral interpretation.
- Per-family and per-seed effects are always shown; a pooled pass cannot be
  described as uniform across tasks.

## Global manuscript language

Allowed:

- "the tested shared reviewer-consolidation protocol";
- "under the tested retrieval capacity, writer budget, and merge policy";
- "compresses strategy supply and, in specified conditions, amplifies loops";
- "candidate mechanism", "plausible channel", or "bounded mechanism account".

Disallowed:

- "shared memory fails";
- "consensus consolidation is generally harmful";
- "strategy compression causes looping" without a successful isolating
  intervention;
- "generalizes to web agents" unless the P3 gate and quality audit pass;
- treating a null or underpowered result as evidence of absence.
