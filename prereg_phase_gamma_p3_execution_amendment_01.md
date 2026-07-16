# Phase Gamma P3 execution amendment 01: bid-aware action schema and semantic calibration

Status: written and frozen on 2026-07-12, before generating any post-amendment P3 smoke or formal outcome data.

Trigger: decision-log entry 2026-07-12 `p3_not_evaluable_action_interface_failure`. The stopped formal run showed that the solver observation hid BrowserGym element bids (`hide_all_bids=True` in the shared AXTree normalizer), so element-targeted actions such as `click('No')` could never resolve. That run is retained for audit only and is excluded from all analyses. Per the decision log, any future browser experiment must freeze a bid-aware action schema and pass a semantic action-execution calibration before arm comparisons. This amendment does exactly that and nothing else.

## 1. Observation and prompt changes (interface repair, applied identically to all arms)

1. The solver prompt AXTree is now produced by a bid-preserving path (`solver_axtree_text`, BrowserGym `hide_all_bids=False`). Element lines therefore expose bracketed bids such as `[12] button "No"`.
2. State hashes, visible-text deltas, and reviewer summaries continue to use the bid-free normalized path unchanged. Hash-stability semantics from the base appendix (§2) are untouched; the selftest asserts that renumbering bids does not change a state hash and that reviewer summaries stay bid-free.
3. The tools documentation appends one fixed instruction block explaining that the bracketed bid string is the element argument (`click("12")`, `fill("a5", "john")`) and that label text is not a bid. The solver system prompt, temperature, and token limits are unchanged.

## 2. New audit fields (no execution-semantics change)

Every executed action is classified for bid validity: the referenced bid (first string argument of bid-taking high-level actions) must appear in the current solver observation, and BrowserGym `Could not find element with bid` errors are classified the same way. Invalid actions are still executed exactly as before (they fail inside BrowserGym and surface via `last_action_error`); the amendment adds only counting: per-route `bid_error_count`, `executed_action_count`, `bid_error_rate`.

## 3. Semantic action-execution calibration (added smoke criteria)

The smoke gate of the base appendix (§3) gains two criteria, both computed from the same smoke matrix:

1. every `(arm, family)` smoke result has `bid_error_rate <= 0.10`;
2. every family has at least one successful route across the three arms.

Both are required for per-family eligibility and jointly reported as the global `semantic_action_calibration` check. All previous smoke criteria (route counts, parse rate >= 0.95, infrastructure-error route rate <= 0.02, hash agreement >= 0.95, reviewer-summary schema) are unchanged. Task replacement continues to follow the fixed replacement order of the base appendix.

## 4. Runs and directories

Post-amendment smoke uses fresh directories `runs_miniwob_gamma_p3b_smoke` / `cache_miniwob_gamma_p3b_smoke` with cache disabled; a passing smoke authorizes the formal matrix in `runs_miniwob_gamma_p3b` / `cache_miniwob_gamma_p3b`. Manifests cite this amendment.

## 5. What is not reopened

The formal matrix, arms, metrics, paired bootstrap, outcome gate, per-seed requirements, stopping rules, and the prohibition on MiniWoB rescue/compression (base appendix §§4-5 and the P1b decision log) are unchanged. This amendment repairs the action interface and adds calibration; it grants no new analysis or tuning freedom.
