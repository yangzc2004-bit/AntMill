# Phase Gamma P3 execution appendix: MiniWoB++ task-family generalization

Status: written and frozen before generating any P3 smoke or formal outcome data.

This appendix operationalizes the P3 section of `prereg_phase_gamma.md`. It is additive to the Gamma preregistration and the P1/P1b decision log. It does not reopen the P1 mechanism interventions or the completed P2 model replication.

## 1. Scope and environment

P3 is a task-family generalization check using `DeepSeek-V3` through the ModelArts MaaS OpenAI-compatible endpoint. It tests the E2 phenomenon only. Because P1b did not pass its preregistered equal-dose manipulation check, P3 will not run archive rescue, compression, or any other MiniWoB mechanism variant regardless of the P3 outcome.

MiniWoB++ is pinned to commit `7fd85d71a4b60325c6585396ec4f48377d049838`. Before smoke, the runner records installed `browsergym`, `browsergym-core`, `browsergym-miniwob`, `gymnasium`, Python, browser runtime, and `MINIWOB_URL` in every manifest. The package/browser configuration is not changed between smoke and formal data.

Primary task families, in fixed order:

1. `click-button`
2. `choose-list`
3. `enter-text`
4. `click-checkboxes`
5. `login-user`
6. `use-autocomplete-nodelay`

Replacement task families, in fixed order:

1. `click-menu`
2. `choose-date-nodelay`
3. `form-sequence`

The formal matrix contains exactly six task families. Replacement tasks are not additional formal families. A primary task that fails its technical smoke eligibility is replaced by the earliest unused replacement task. More than three failed primaries, or any selected replacement that fails smoke, yields `p3_not_evaluable`; no extra task selection or tuning is permitted.

## 2. Architecture and fixed summaries

For every task instance, four solver agents run in four independent BrowserGym environments using the identical MiniWoB task name and reset seed. They share only the arm-specific memory library. There is no majority-action execution and no cross-browser state sharing.

Each `(arm, experimental seed, task family)` has a separate memory pool. P3 uses the E2/P2 arm definitions unchanged:

- `frozen`: ExpeL reviewer writes to a frozen pool that is never injected;
- `append`: shared append writes with GA retrieval and `ga_lambda=0`;
- `consolidated`: shared ExpeL ADD/EDIT/UPVOTE/DOWNVOTE writes with GA retrieval and `ga_lambda=0`.

All arms use `retrieval_k=6`, `library_cap=80`, four solvers, solver temperature `0.7`, `max_tokens_solver=256`, and `max_tokens_reviewer=512`.

Reviewer input is the deterministic compact summary only: goal, success, steps, invalid/error count, repeated-state count, first three actions, last eight `(action, normalized_state_hash, visible_text_delta, error)` records, and final normalized AXTree truncated to 1200 characters. Full per-step AXTree is forbidden.

State hashes remove volatile BrowserGym ids, focus/hover state, coordinates, and dynamic node ids; retain text and form values; normalize whitespace; and include URL/path plus last-action error. `repeated-action-on-same-state` is the same normalized action proposed from a state hash seen earlier in that route.

## 3. Smoke and selection gate

Smoke runs all six primary task families with frozen, append, and consolidated arms; one seed (`0`), `T=1`, two heldout instances per family, two train instances per family, four solvers, `max_steps=15`, and cache disabled. This produces eight heldout routes per arm-task result and 144 heldout routes across the primary smoke matrix. Smoke is engineering-only and excluded from formal analyses.

Smoke passes only when all selected task results satisfy:

- task registration and reset work;
- action parse rate is at least `0.95`;
- browser/environment infrastructure-error route rate is at most `0.02`;
- same reset and replayed action sequence yields state-hash agreement at least `0.95`;
- every reviewer summary has all fixed fields and final normalized AXTree length at most 1200 characters.

Task replacement is based on per-task route-count, parse, and infrastructure checks across all three arms. Hash stability and reviewer-summary schema are global guardrails: failure stops P3 instead of selectively replacing a task.

## 4. Formal matrix and analysis

After smoke authorization, formal runs selected task families with `T=4`, `heldout=12` per family, train pool `16`, train batch `4`, seeds `0,1,2`, arms frozen / append / consolidated, `max_steps=15`, and no final-round write. Heldout instances are fixed across rounds within a `(task family, seed)` and matched across arms; train instances are deterministic and arm-matched. At six task families this is 10,368 heldout solver routes.

Per route, record success, steps, failure-penalized steps, failure-penalized cost, repeated-action-on-same-state, nontermination, combined loop/stall burden, parse and infrastructure failures, action trace, state hashes, reviewer summary, retrieved memory, and memory audit.

Failure-penalized cost is `steps / max_steps` for successes and `1.0` for failures. Combined loop/stall burden is `repeated-action-on-same-state OR nontermination`. The two components are reported separately but never treated as independent significant wins because the step cap can move probability mass between them.

The primary comparison is `consolidated - frozen` at terminal `t=3`. `append` is secondary. Paired routes align on `(task family, experimental seed, heldout instance, solver slot)`. The bootstrap resamples seed clusters within task family, resamples paired routes inside each cluster, and averages task-family means equally.

P3 is called `p3_phenomenon_pass` only if:

1. failure-penalized cost is worse for consolidated, with 95% bootstrap CI entirely above zero;
2. combined loop/stall burden is worse for consolidated, with 95% bootstrap CI entirely above zero;
3. each primary metric has a positive consolidated-minus-frozen effect in at least two of three seeds.

Success, raw steps, per-family effects, and per-seed signs are always reported. Success decline is not an additional gate. If success clearly improves while both burden metrics pass, the conclusion is limited to behavioral-burden replication with mixed success evidence. Any other gate outcome is reported as `p3_not_detected_or_underpowered`, not as a task boundary or evidence against shared-memory risk.

## 5. Stopping and reporting

P3 stops after the formal gate, or earlier as `p3_not_evaluable` under the smoke rules. No MiniWoB rescue, compression, task substitution beyond the three fixed replacements, parameter tuning, or extra seeds are allowed. P4 tau2-bench remains a non-blocking post-submission or surplus-budget stretch item.

Every smoke/formal condition writes `manifest.json`, `memory_audit.json`, `result.json` with per-route records, bootstrap and gate reports, per-family effects, per-seed signs, latency/token summaries, and `prereg_deviation_log.md`.
