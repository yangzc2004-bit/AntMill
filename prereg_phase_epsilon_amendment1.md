# Phase Epsilon Amendment 01: append semantics and replacement control

Date: 2026-07-16.

Status: frozen on 2026-07-16 before any amendment-arm execution.

This append-only amendment does not modify or replace
`prereg_phase_epsilon.md` or its freeze record. It records an
outcome-independent protocol discovery, cancels a redundant proposed arm,
adds one replacement control, makes the capacity tie rule explicit, corrects
the reviewer-temperature specification, and records one budget decision. All
Phase Epsilon settings, endpoints, contrasts, and reporting rules not
explicitly changed below remain in force.

## 1. Protocol discovery and correction: append merging

On 2026-07-16, a read-only implementation and artifact audit established that
the shared-append writer has performed deterministic lexical near-duplicate
merging since the Beta E2 runtime. The append path calls
`find_pool_duplicate` before admitting each candidate
(`sec/maze_alpha.py:1219-1220`). A same-kind match at the fixed `0.80`
threshold retains the existing pool item, increments its vote count, and does
not admit the proposed text as a new active item. The similarity function is
the maximum of token-set Jaccard and `SequenceMatcher` ratio
(`sec/metrics.py:179-190`; `sec/config.py:18`).

This was a material part of the executed protocol, not a dormant branch.
Across the five frozen Beta E2 `e2_shared_append_ga` seeds, 300 of 800
candidate writes were recorded as `reviewer_append:agree` and therefore
merged, while 500 were admitted as new active items. The per-seed merge
counts were 55, 58, 53, 67, and 67. Evidence is retained in:

- `runs_maze_beta_e2/n4_gt_false_seed{0..4}_e2_shared_append_ga/memory_audit.json`;
- the 600 indexed `expel_ops_reviewer` cache records in
  `cache_maze_beta_e2/`, including replay of the 200 joint four-agent review
  calls against the consolidated memory audits.

The preregistration and manuscript phrase that shared append was "never
merged" is therefore inaccurate. The executed E2 contrast is restated as:

- shared append: mechanical lexical near-duplicate merging, cap 80, and no
  reviewer-selected `EDIT` or `DOWNVOTE` pool evolution;
- shared consolidated: the same mechanical lexical near-duplicate rule plus
  reviewer-selected `ADD`, `EDIT`, `UPVOTE`, and `DOWNVOTE` pool evolution.

Accordingly, the reported `25.4 / 11.0 = 2.31x` distinct-injection
compression is additional compression associated with reviewer selection on
top of the common mechanical lexical deduplication rule. It must not be
described as no merging versus merging.

The manuscript correction ledger must include, at minimum:

- `paper_draft/antmill_full_en.tex:206-207`: replace "shared but never
  merged";
- `README.md:86` and `README.md:334`: replace "shared append-only";
- the E2 mechanism-audit narrative and the interpretation of the `2.31x`
  contrast.

These corrections are recorded in `paper_corrections.md`; this amendment does
not edit manuscript or README text.

## 2. Cancelled arm and replacement

The previously proposed `epsilon_shared_dedup_cap14` arm is cancelled before
execution. It is substantively redundant with
`epsilon_shared_append_cap14`, because the existing append path already uses
the same lexical near-duplicate merge rule and threshold.

The replacement control arm is:

`epsilon_shared_append_raw`: shared raw append-stream memory with no
near-duplicate lookup or merge and a hard active-pool capacity of 80.

For this arm, every sanitized candidate experience that would reach the
append writer is admitted as a distinct new active item with its own insertion
order. The writer must bypass `find_pool_duplicate`; it must not convert a
candidate into agreement, increment an existing item's vote, or archive it as
a similarity merge. No reviewer-operation LLM participates in pool admission,
editing, voting, or deletion. Candidate generation and sanitization otherwise
follow the same append-stream path as the existing shared-append protocol.

After every write update, the active pool is truncated to 80 items using the
oldest-evicted tie rule in Section 3. Based on the Beta candidate yield of
approximately 160 candidates per seed, the pool is expected to reach its
80-item capacity at approximately round 3 and then continue as a rolling pool
under oldest-evicted replacement. This is a design expectation, not an
outcome gate.

The arm uses seeds `0`, `1`, `2`, `3`, and `4`, six interaction rounds
(`T=6`), and all other common Phase Epsilon settings, task splits, cache
isolation, and reporting rules. Its purpose is to provide a true no-merge
same-stage baseline.

This replacement consumes the execution slot released by cancellation of
`epsilon_shared_dedup_cap14`; it does not increase the planned control-suite
budget.

After this amendment, the six Epsilon control-suite arms are
`epsilon_frozen_reviewer`, `epsilon_private_consolidated`,
`epsilon_shared_consolidated`, `epsilon_shared_append_cap14`,
`epsilon_shared_consolidated_mmr`, and `epsilon_shared_append_raw`, each with
five seeds. The completed Beta E2 cap-80 deduplicating append arm remains a
historical mechanism reference and is not a seventh Epsilon arm.

## 3. Capacity tie rule

For `epsilon_shared_append_raw` and `epsilon_shared_append_cap14`, items with
higher vote counts are retained first when a capacity limit is applied. When
vote counts are tied, the oldest item by active-pool insertion order is
evicted first and the most recently admitted items are retained. Text
content, normalized text, hash value, retrieval history, and agent identifier
must not break a capacity tie.

Retaining the earliest items would cause the raw arm, which has no mechanism
for incrementing votes, to freeze its pool in mid-run through a founder effect
and would confound that artifact with the collapse phenomenon under study.

This rule replaces the current implicit reverse lexical tie-breaking behavior
in `sec/expel_ops.py:173-175`. Both raw-append cap-80 truncation and
append-cap-14 truncation must use the same explicit insertion-order field and
oldest-evicted, recency-retaining rule.

The completed pre-amendment `epsilon_shared_append_cap14` seed 0 and seed 1
artifacts were produced under the implicit lexical tie rule. They are retained
unchanged for audit, but are not eligible for the amended oldest-evicted
comparison. Both seeds must be rerun under the frozen amended implementation,
together with seeds 2-4.

## 4. Reviewer temperature correction

The original common-settings text states that both solver and reviewer
temperature are `0.7` (`prereg_phase_epsilon.md:32-35`). The executed reviewer
implementation instead uses a hard-coded temperature of `0.2` in both
reviewer paths:

- operation reviewer: `sec/expel_ops.py:101-106`;
- append-stream experience distiller: `sec/expel.py:145-150`.

This discrepancy was discovered by configuration-to-code audit on
2026-07-16, after `epsilon_private_consolidated` seeds 0 and 1 had completed,
but before any amendment-arm execution and before any cross-arm Epsilon
behavioral contrast was computed or interpreted. The correction is therefore
protocol-driven rather than result-driven.

The amended common setting is:

- solver temperature remains `0.7`;
- reviewer and append-stream experience-distillation temperature is `0.2`.

Temperature `0.2` preserves the historical Beta/Gamma implementation and the
runtime actually used by the completed Epsilon private-consolidated seeds.
Those seed 0 and seed 1 artifacts remain eligible; they are not rerun solely
because the prose specification incorrectly coupled reviewer temperature to
solver temperature.

Before further Epsilon execution, the implementation tasks are:

a. add an explicit reviewer-temperature configuration, CLI, and manifest
field, frozen at `0.2` independently of `solver_temp=0.7`;
b. route both maze reviewer call sites through that configuration instead of
hard-coded literals;
c. update Epsilon expected-configuration validation and tests to assert
solver `0.7` and reviewer `0.2`, preventing silent coupling or drift.
d. record an explicit `tie_rule` field in each run manifest.

No implementation task in this section is authorized until this amendment is
reviewed and frozen.

## 5. Manipulation check and interpretation

The deterministic-compression control is
`epsilon_shared_append_cap14`; no separate dedup-cap-14 arm will be run.
Behavioral interpretation is permitted only if both manipulation checks hold:

1. its terminal active pool contains at most 20 items in every seed; and
2. its distinct injected strategy count is significantly lower than the
   same-stage `epsilon_shared_append_raw` arm. Because distinct injected
   count is one scalar per arm per seed, this check uses seed-level pairing:
   compute the five per-seed paired differences (cap14 minus raw), resample
   seeds with replacement (10k resamples), and require the 95 percent
   percentile interval to exclude zero in the compression-favoring direction.
   The route-level pairing rule below applies to behavioral endpoints, not to
   this per-seed scalar check.

Conditional on passing the manipulation check, interpretation is frozen as:

- Interpretation A: if `epsilon_shared_append_cap14` reproduces loop
  amplification of the same order as `epsilon_shared_consolidated`, relative
  to `epsilon_frozen_reviewer`, mechanical compression is sufficient under
  the tested protocol.
- Interpretation B: if `epsilon_shared_append_cap14` has no significant loop
  amplification relative to `epsilon_frozen_reviewer`, while
  `epsilon_shared_consolidated` has significant loop amplification relative
  to the same frozen arm, the harmful effect is attributed to the reviewer's
  selective pool-evolution behavior rather than compression alone.
- Interpretation C: any intermediate, mixed, or imprecise result is reported
  without forcing either mechanistic conclusion.

The completed Beta E2 cap-80 deduplicating append arm is reported only as a
supplementary descriptive reference. It is not paired with Epsilon results,
does not participate in either manipulation check or any interpretation gate,
and is not treated as a new Epsilon outcome. Cross-phase comparison is limited
by model drift and different task splits.

All inferential comparisons retain the Phase Epsilon rule in
`prereg_phase_epsilon.md:119-128`: routes are paired by seed, round, held-out
maze, and agent; the estimate is the equal-weight mean of per-seed paired
effects; uncertainty uses the hierarchical paired bootstrap with seed
clusters as the outer resampling unit.

## 6. Sensitivity-suite budget decision

The complete nine-arm `epsilon_sens_*` suite, comprising the reference arm and
all eight parameter variants, will not be executed in the present phase. It
is moved to future work.

This is a budget and scheduling decision, not a result-driven stopping rule.
No sensitivity arm will be selectively restored, substituted, or reported as
confirmatory evidence in the current Phase Epsilon control analysis.

## 7. Freeze record

Document SHA-256: `16639e28ac53e156aaea5aa9806d2b20aaa15018e9fcc599875b0d513ea31621`

Hash rule: SHA-256 over the UTF-8 file bytes after replacing only the digest
value on the preceding line with the literal
`<TO_BE_RECORDED_AT_FREEZE>`. The external freeze record stores the SHA-256
of the final file bytes after this digest is inserted.
