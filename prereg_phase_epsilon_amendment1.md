# Phase Epsilon Amendment 01: deterministic write-side deduplication

Date: 2026-07-16.

Status: frozen before any amendment-arm execution.

This append-only amendment does not modify or replace
`prereg_phase_epsilon.md` or its freeze record. It adds one control arm,
explicitly freezes the capacity tie rule, and records one outcome-independent
budget decision. All Phase Epsilon settings, endpoints, contrasts, and
reporting rules not explicitly changed below remain in force.

## 1. Added control arm

The Epsilon control suite adds:

`epsilon_shared_dedup_cap14`: shared append-stream memory with deterministic
write-side near-duplicate merging and a hard active-pool capacity of 14.

Each candidate `ADD` is checked immediately against the active shared pool.
The implementation must reuse the existing operation-application skeleton in
`sec/expel_ops.py`; it must not introduce a second similarity definition or an
embedding-based gate.

Duplicate similarity is exactly the lexical similarity used by the
shared-consolidated arm: normalize both texts, compute token-set Jaccard and
`SequenceMatcher` ratio, and use their maximum
(`sec/metrics.py:179-190`). The fixed merge threshold is `0.80`
(`sec/config.py:18`).

When an `ADD` meets or exceeds the threshold against an existing same-kind
item, the existing pool item is retained, the proposed new item is written to
the read-only archive with source `similarity_merge`, and the existing item's
vote count is incremented by one. The proposed text never replaces the
existing text.

No reviewer-operation LLM call may participate in pool admission,
consolidation, editing, voting, or deletion in this arm. In particular, there
is no six-operation reviewer budget and no selective `ADD`, `EDIT`,
`UPVOTE`, or `DOWNVOTE` policy. Candidate experience items otherwise follow
the same append-stream generation and sanitization path as
`epsilon_shared_append_cap14`. Relative to
`epsilon_shared_consolidated`, replacing reviewer-selected pool evolution with
this deterministic write-side rule is the only protocol intervention; the
environment, model, candidate-experience source, retrieval protocol, and
evaluation endpoints remain fixed.

## 2. Capacity and deterministic tie rule

After every write update, `epsilon_shared_dedup_cap14` is truncated to at most
14 active items using the same capacity rule as
`epsilon_shared_append_cap14`.

For both `epsilon_shared_append_cap14` and
`epsilon_shared_dedup_cap14`, items with higher vote counts are retained
first. When vote counts are tied, retention is first-in, first-out: the item
that entered the active pool earlier is retained. Text content, normalized
text, hash value, retrieval history, and agent identifier must not break a
capacity tie.

This rule replaces the current implicit reverse lexical tie-breaking behavior
in `sec/expel_ops.py:173-175`. The corresponding append-capacity truncation
must use the same FIFO rule. Any pre-amendment append-capacity artifact
generated with lexical tie-breaking is retained for audit only and is not
eligible for the amended FIFO comparison without an identical-configuration
rerun.

## 3. Execution

The amended control arm uses seeds `0`, `1`, `2`, `3`, and `4`, six
interaction rounds (`T=6`), and all fixed environment and common-protocol
settings in Section 2 of `prereg_phase_epsilon.md`.

It is run as part of the `epsilon_controls` suite alongside the other Epsilon
control arms, with the same task splits, seed pairing, cache policy, and
reporting schedule. The control suite therefore contains six arms after this
amendment.

## 4. Manipulation check and interpretation

Behavioral interpretation is permitted only if the deterministic-compression
manipulation is active. At the terminal round, both conditions must hold:

1. the final active pool contains at most 20 items in every seed; and
2. distinct injected strategy count is significantly lower than the
   append-only capacity-80 reference, defined as a compression-favoring
   paired 95 percent hierarchical-bootstrap interval that excludes zero.

The capacity-80 append reference is used for this manipulation check only; it
is not reclassified as a new Epsilon outcome.

Conditional on passing the manipulation check, interpretation is frozen as:

- Interpretation A: if `epsilon_shared_dedup_cap14` reproduces loop
  amplification of the same order as `epsilon_shared_consolidated`, relative
  to `epsilon_frozen_reviewer`, mechanical compression is sufficient under
  the tested protocol.
- Interpretation B: if `epsilon_shared_dedup_cap14` is comparable to
  `epsilon_shared_append_cap14` and significantly better than
  `epsilon_shared_consolidated`, the harmful effect is attributed to the
  reviewer's selective pool-evolution behavior rather than compression alone.
- Interpretation C: any intermediate, mixed, or imprecise pattern is reported
  without forcing either mechanistic conclusion.

All comparisons retain the Phase Epsilon analysis rule in
`prereg_phase_epsilon.md:119-128`: routes are paired by seed, round, held-out
maze, and agent; the estimate is the equal-weight mean of per-seed paired
effects; uncertainty uses the hierarchical paired bootstrap with seed
clusters as the outer resampling unit.

## 5. Sensitivity-suite budget decision

The complete nine-arm `epsilon_sens_*` suite, comprising the reference arm and
all eight parameter variants, will not be executed in the present phase. It is
moved to future work.

This is a budget and scheduling decision, not a result-driven stopping rule.
No sensitivity arm will be selectively restored, substituted, or reported as
confirmatory evidence in the current Phase Epsilon control analysis.

## 6. Freeze record

Document SHA-256: `<TO_BE_RECORDED_AT_FREEZE>`

