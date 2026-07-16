# Phase Zeta preregistration: exact consolidated-supply-yoked append control

Status: written before any Phase Epsilon `epsilon_shared_consolidated`
condition produced a complete `result.json`, and before any Phase Zeta outcome
data.

## 1. Motivation and scope

Phase Epsilon includes `epsilon_shared_append_cap14`, a fixed terminal-capacity
control based on the mean final E2 consolidated pool size. That arm is useful
but does not provide exact seed-by-seed, round-by-round equality. Phase Zeta
adds one separate control requested by the review audit: shared append memory
whose *retrievable candidate supply* is yoked exactly to the corresponding
Phase Epsilon shared-consolidated active-pool trajectory.

This phase does not alter, replace, or tune the frozen Epsilon suite. It adds
one prespecified mechanism contrast after Epsilon controls complete.

## 2. Blinded schedule construction

For each seed in `0,1,2,3,4`, the schedule builder reads only:

- `memory_audit.pool_trajectory[t].active_pool_size` from the completed
  `epsilon_shared_consolidated` result;
- the source result path and its SHA-256 digest.

It does not read route records, endpoint summaries, success, cost, loop,
stagnation, retrieval diversity, or any cross-arm statistic. The six target
values for rounds `t=0,...,5` are written to a frozen schedule JSON together
with source hashes and this document's SHA-256 before any yoke run starts.

## 3. Yoked arm

Run ID: `zeta_shared_append_exact_yoke`.

The arm uses the same maze tasks, model, five seeds, horizon, solver/reviewer
settings, append writer, GA retrieval, `k=6`, storage cap 80, and
`ga_lambda=0` as the Epsilon common protocol. The append storage pool remains
auditable in full. Before retrieval at each round, a deterministic subset of
append items is exposed as the candidate pool:

- subset size equals that seed and round's frozen consolidated active-pool
  target;
- selection is deterministic from seed, round, and stable item keys;
- a shrinking target returns the corresponding prefix of the persistent
  deterministic subset, while a growing target admits additional items;
- downstream GA ranking and top-k injection are unchanged.

This is an exact read-supply-size yoke, matching the reviewer's suggested
random-subsample control. It does not claim equality of text content, votes,
write operations, or the full stored append archive.

## 4. Manipulation check

For every seed and every round:

1. the recorded `budgeted_append_budget` must equal the frozen target;
2. the recorded `budgeted_append_selected` must equal the target.

All 30 checks must pass. If append has too few items or any recorded size
differs, the manipulation is `zeta_supply_yoke_not_evaluable`; behavioral
contrasts are still archived but not used to isolate pool size.

## 5. Analysis

The prespecified contrast is:

`zeta_shared_append_exact_yoke - epsilon_shared_consolidated`

at terminal `t=5`, using the same paired route keys, endpoint family,
seed-clustered paired bootstrap, and per-seed effect table as Phase Epsilon.
The primary endpoint is loop rate. Success, success-only excess steps,
failure-penalized steps, stagnation, final stored pool size, distinct injected
items, and retrieval diversity diagnostics are always reported.

Interpretation is bounded:

- if the manipulation passes and the yoke remains behaviorally separated from
  consolidated, equal candidate-pool size alone is insufficient to explain
  that separation;
- if the manipulation passes and the yoke approaches consolidated, candidate
  supply size remains a plausible explanatory channel;
- neither result by itself identifies strategy-supply compression as a cause,
  because append and reviewer consolidation still differ in item content and
  write dynamics.

No extra seeds, alternative yoke selection, target smoothing, outcome-based
schedule adjustment, or additional Zeta arm is allowed.

## 6. Execution order

1. Complete all frozen Epsilon controls.
2. Extract and freeze the five consolidated supply schedules without reading
   behavioral outcomes.
3. Run the single Zeta arm for seeds `0,1,2,3,4`.
4. Evaluate the manipulation check before interpreting behavioral contrasts.
