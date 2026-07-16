# Frozen Claim-Decision Rules

Status: written before any complete
`epsilon_shared_consolidated_mmr`, `epsilon_shared_consolidated`, Phase Zeta,
or complete MiniWoB formal outcome suite was available.

These rules translate complete evidence artifacts into permitted manuscript
language. They do not change an experimental endpoint, statistical analysis,
or preregistered outcome gate.

## Common Interval Classification

For every paired contrast:

- `positive_detected` means the 95% CI lower bound is greater than zero;
- `negative_detected` means the 95% CI upper bound is less than zero;
- `not_detected` means the interval includes zero.

Success is better in the positive direction. Loop rate, stagnation,
failure-penalized steps, and success-only excess steps are better in the
negative direction. Every endpoint is interpreted separately.

## Sharing Versus Consolidation

For shared-consolidated minus private-consolidated loop rate:

- `positive_detected` permits the statement that cross-agent sharing under the
  tested joint-reviewer consolidation protocol is associated with added loop
  burden relative to the per-agent-consolidated protocol;
- `not_detected` requires the statement that the fresh study does not isolate
  a shared-specific loop effect;
- `negative_detected` requires reporting the opposite direction.

No loop result licenses an efficiency or success claim.
The contrast is protocol-level rather than a one-factor causal estimate of
sharing: private consolidation invokes one reviewer call per agent and private
pool, while shared consolidation invokes one joint call over four agent logs
and one shared pool. Thus reviewer prompt composition, reviewer-call count, and
total operation opportunity are not equalized.

The append controls are reported as append/agree protocols. Near-duplicate
additions receive deterministic agreement upvotes, but no joint reviewer issues
`EDIT` or `DOWNVOTE` operations over the shared pool. They must not be described
as "never merged."

## Capacity Controls

The cap-14 append arm is always described as a fixed terminal-capacity control.
Each endpoint is reported, but it cannot establish exact pool-size control.

Zeta behavioral interpretation is allowed only when its decision is
`zeta_supply_yoke_evaluable`. A primary loop CI excluding zero indicates that
the exact-size yoke remains behaviorally separated from consolidation, so
candidate-pool size alone is insufficient for that separation. A loop CI
including zero leaves candidate-supply size plausible. Neither branch
identifies a cause because item content and write dynamics remain unequal.

## MMR Manipulation and Behavior

MMR manipulation diagnostics are paired by seed against ordinary shared
consolidation at the terminal round. A diagnostic has directional support when
its seed-mean change is in the intended direction and at least three of five
seed changes have that direction:

- distinct active injected items: increase;
- distinct total injected items: increase;
- normalized retrieval entropy: increase;
- top-1 retrieval share: decrease;
- retrieval concentration: decrease.

The MMR manipulation is called `direction_observed` when at least one direct
supply or retrieval-diversity diagnostic has directional support. This is a
descriptive manipulation classification, not a significance test.

An endpoint-specific mitigation statement is allowed only when the
manipulation is `direction_observed` and that behavioral endpoint improves
with a 95% CI excluding zero. If the manipulation is not observed, behavior
cannot be used to judge diversity-aware retrieval generally. No MMR outcome
identifies write-side compression as causal.

## Sensitivity Envelope

All eight parameter settings and all five primary endpoints are reported
relative to the frozen reference. No best setting is selected. The report
classifies every CI and lists seed effects, but it does not automatically
promote any collection of settings to a universal robustness claim.

## MiniWoB Task-Family Boundary

The exact preregistered P3 decision controls language:

- `p3_phenomenon_pass` with `quality_clear` permits a scoped replication claim
  over the six tested MiniWoB families;
- `p3_not_detected_or_underpowered` requires "not detected under the frozen
  design and sample size" language;
- any quality warning requires reporting the formal evaluation as not
  behaviorally interpretable until resolved.

Per-family and per-seed effects are always reported. A pooled pass is never
described as uniform across tasks.

## Global Scope

The final abstract and conclusion use the narrowest branch supported by all
completed evidence. They may refer to:

- the tested shared reviewer-consolidation protocol;
- the tested retrieval capacity, writer budget, and merge policy;
- strategy-supply compression as a correlate or candidate channel;
- loop amplification only where the corresponding contrast supports it.

They may not state that shared memory fails generally, that consensus
consolidation is generally harmful, or that strategy compression causes
looping.
