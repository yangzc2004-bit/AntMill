# Phase Gamma decision log

## 2026-07-11: P1 additive archive rescue

The completed `gamma_p1_shared_consolidated_archive_rescue` used additive active top-6 plus archive top-6 retrieval. It is retained as a negative evaluation of a naive additive archive fix, not as a clean test of equal-dose archive rescue.

Behavioral gate decision: `rescue_inconclusive_or_fail`.

## 2026-07-11: P1b equal-dose archive rescue

P1b used one joint active/archive ranking with a total top-6. All three seeds completed with zero retrieval-dose violations and zero final parse failures.

The frozen manipulation check required cumulative distinct injected items at `t=5` to be at least 1.5 times the corresponding E2 consolidated count in at least 2/3 seeds.

| seed | P1b cumulative distinct | E2 consolidated | ratio | pass |
|---|---:|---:|---:|---|
| 0 | 17 | 12 | 1.417 | no |
| 1 | 17 | 11 | 1.545 | yes |
| 2 | 15 | 14 | 1.071 | no |

Decision: `ranking_inaccessible_not_evaluable`.

Archive items were selected in 896/912 retrieval records where archive candidates existed, so the intervention did not fail because archive items were never retrieved. It failed the preregistered diversity-expansion threshold: fixed-capacity retrieval did not reliably expand the distinct injected supply by 50%.

Per amendment 01:

- do not evaluate the behavioral rescue gate as a confirmatory result;
- do not describe P1b as evidence that equal-dose archive rescue is ineffective;
- do not add seeds, tune ranking, reserve archive slots, or run archive-source ablations;
- do not run compression;
- stop P1 and proceed to P2/P3 phenomenon replication only;
- do not run cross-model or MiniWoB rescue.

The first generated manipulation report treated old E2 results as if they contained the newer `pool_trajectory` field and displayed baseline distinct counts as zero. The compatibility code was corrected to reconstruct cumulative distinct counts from the frozen E2 retrieval records. The corrected counts above leave the decision unchanged.

## 2026-07-12: P3 initial smoke harness invalidated before interpretation

The first P3 smoke launch was stopped after BrowserGym 0.14.3 reported that its synchronous Playwright API was being invoked inside the asyncio event loop. The affected routes failed during browser setup, producing infrastructure-error routes rather than solver behavior. No P3 outcome or gate interpretation is permitted from those artifacts.

The runner was corrected to execute all synchronous BrowserGym reset/step/close operations on one dedicated browser worker thread while retaining asynchronous MaaS solver calls. A four-environment no-MaaS `noop()` integration probe completed with zero infrastructure errors. The invalid smoke artifacts are retained under an `invalid_syncapi` run directory; the clean P3 smoke rerun uses fresh output and cache directories with cache disabled.

## 2026-07-12: P3 formal stopped for semantic action-interface failure

The clean P3 smoke established infrastructure availability but omitted a semantic action-execution calibration. In the first formal family (`click-button`), solver outputs such as `click('No')` passed the action parser but BrowserGym executed them as bid lookups and returned `ValueError: Could not find element with bid "No"`.

The frozen arm was therefore floor-saturated before any shared-memory comparison: completed seed 0 terminal success was `0.021`, failure-penalized cost `0.996`, and loop/stall burden `0.938`; completed seed 1 terminal success was `0.000`, cost `1.000`, and loop/stall burden `0.958`. This is not a memory effect or a valid P3 negative result.

Decision: `p3_not_evaluable_action_interface_failure`.

- stop the in-flight formal P3 run;
- retain completed partial artifacts for audit only;
- do not calculate or report the preregistered P3 outcome gate;
- do not run MiniWoB rescue or compression;
- do not treat this as evidence against cross-task generalization;
- any future browser generalization experiment must freeze a bid-aware action schema and pass semantic action-execution calibration before arm comparisons.

## 2026-07-14: P3c complete smoke stopped for missing local browser bootstrap

P3c was a fresh six-family smoke matrix intended to complete the partial P3b
bid-aware calibration. It was stopped after the first two families because
every route failed before the first solver action. The manifests recorded empty
`MINIWOB_URL` and `MINIWOB_BROWSER_EXECUTABLE` values, while the successful P3b
calibration had used a local MiniWoB++ root and a Chrome executable.

Decision: `p3c_not_evaluable_missing_browser_bootstrap`.

- retain the six completed P3c arm-family artifacts for audit only;
- do not combine P3c with P3b or calculate smoke eligibility from either;
- do not interpret the all-failure routes as agent behavior or a memory result;
- rerun the unchanged complete smoke matrix only in a fresh P3d directory with
  the two previously validated local browser environment variables frozen in
  amendment 03.

## 2026-07-14: P3d complete bid-aware smoke passed

The fresh P3d six-family smoke matrix completed all 18 arm-family results and
passed every frozen check: 144 held-out routes, action parse rate 1.0,
infrastructure-error route rate 0.0, state-hash agreement 1.0 over 99 compared
hashes, valid reviewer summaries, and all six task families eligible. The
largest per-run bid-error rate was 0.025, below the 0.10 amendment-01 limit.

Decision: `p3d_smoke_pass_formal_authorized`.

The frozen P3 formal matrix is now technically authorized. This smoke outcome
is engineering-only and is excluded from the formal phenomenon analysis.

## 2026-07-15: P3 formal stopped for browser-version drift

An outcome-blind provenance refresh after 16 of 54 P3 formal results found two
browser versions within the matrix. Eleven completed manifests recorded Chrome
`150.0.7871.115`; five recorded `150.0.7871.124`. The executable path was the
same system-managed Chrome path, which had auto-updated during execution. The
MiniWoB++ commit, package versions, local task URL, task validation, and
independent-environment count remained unchanged.

Decision: `p3_formal_not_evaluable_browser_version_drift`.

- stop the in-flight P3b formal matrix and retain its partial artifacts for
  infrastructure audit only;
- do not calculate or report any pooled, arm-comparative, per-family, or
  per-seed behavioral result from P3b;
- exclude P3b from the manuscript and all confirmatory evidence;
- make exact cross-run environment consistency a hard formal-quality gate;
- copy Chrome `150.0.7871.124` to an immutable workspace-local runtime and
  freeze its executable and full-tree hashes;
- rerun the unchanged complete smoke matrix in fresh P3e directories, then
  authorize a fresh 54-result formal matrix only if every smoke check passes.

The pinned runtime passed two pre-freeze engineering probes totaling eight
independent `click-button` resets and one `noop()` step per environment, with
no LLM calls and no infrastructure errors. Chrome installed one dictionary
during the first probe; after rehashing the complete runtime, the second probe
left all 273 files byte-for-byte unchanged. Amendment 04 records the immutable
runtime and P3e execution sequence. No behavioral rule or interpretation was
changed.

## 2026-07-15: P3e immutable-runtime smoke passed

The fresh P3e six-family smoke matrix completed all 18 arm-family results under
the workspace-local Chrome `150.0.7871.124` runtime. Every frozen engineering
and provenance check passed:

- 144/144 expected held-out routes;
- action parse rate `1.000`;
- infrastructure-error route rate `0.000`;
- state-hash agreement `1.000` over 99 compared hashes;
- worst per-run bid-error rate `0.000`;
- valid reviewer summaries and at least one successful route in every family;
- 18/18 configuration checks and 18/18 sibling-manifest checks;
- one exact browser/Python/package/task environment signature across all runs;
- all five preregistration document hashes and all 36 smoke source hashes
  matched.

Decision: `p3e_smoke_pass_formal_authorized`.

The smoke is engineering-only and excluded from formal behavioral analysis.
The fresh P3e 54-result formal matrix started at
`2026-07-15T10:31:49+08:00` with the unchanged preregistered arms, tasks,
seeds, metrics, and outcome gate.
## 2026-07-15: Outcome-blind descriptive weighting clarification

Before the P3e formal matrix completed and before any cross-arm P3e behavioral
contrast was computed or inspected, the descriptive per-task-family effect
implementation was aligned with the frozen hierarchical analysis. Each
task-family effect now averages seed-level paired-route means equally instead
of pooling all paired routes across seeds. This matters only if valid pair
counts differ by seed. It changes no task, arm, metric, primary pooled
bootstrap, gate threshold, per-seed requirement, stopping rule, or formal
quality check.

## 2026-07-15: P3e runtime-source provenance sidecar

After 13 of 54 P3e formal results had completed, and before any cross-arm P3e
behavioral contrast was computed or inspected, an outcome-blind provenance
audit found that the five preregistration documents and browser runtime were
hash-frozen but the Python source loaded by the formal process was not listed
in a source sidecar.

The formal Python process started at `2026-07-15T10:31:49+08:00`. The launch
script and every Python module imported by the MiniWoB runner had a filesystem
modification time earlier than that process start. Their paths, SHA-256
digests, modification times, exact command line, process identifiers, and Git
HEAD are recorded in `p3e_runtime_source.freeze.json`. Offline analysis,
selftest, and paper files are excluded because they are not loaded by the
running agent process.

The P3 evidence exporter and unified evidence gate now require every recorded
runtime-source digest to match. A mismatch withholds behavioral estimates in
the same manner as a preregistration or formal-environment provenance failure.
This is a metadata-only correction: no running process, source module loaded by
that process, arm, task, seed, endpoint, threshold, or stopping rule changed,
and no completed artifact was rewritten.

## 2026-07-15: Outcome-blind P3e finalizer guard

Before the P3e formal matrix completed and without computing or inspecting any
cross-arm behavioral contrast, an orchestration audit found that
`scripts/run_gamma_p3e_pipeline.ps1` invokes the existing formal finalizer
without its mandatory `RunProcessId` argument. Editing that pipeline while the
formal run is active would invalidate the frozen runtime-source sidecar, so the
pipeline is left unchanged.

An independent hidden finalizer is therefore launched with the actual formal
Python process identifier. It only waits for that process to exit, requires
exactly 54 formal result files, and then invokes the existing preregistered
consolidated, append-secondary, and latency gates. This changes no task, model,
cache, arm, seed, endpoint, threshold, stopping rule, runtime module, or
completed artifact.

## 2026-07-15: Outcome-blind P3e LLM-path quality disclosure

After 16 of 54 P3e formal results had completed, and before any cross-arm
behavioral contrast was computed or inspected, an engineering-only audit found
that the formal quality table reported parse, browser, bid, manifest, and
environment checks but omitted LLM-call failures already present in the result
artifacts.

Across the 16 completed results, one frozen write-only run
(`choose-list`, seed 1) recorded 332 failed API attempts, 280 retries, and 52
calls exhausted after all retries. Forty exhausted calls affected held-out
routes at round `t=0`; the remaining 12 were outside held-out evaluation.
Rounds `t=1,2,3`, including the terminal round, recorded zero route-level LLM
errors. The frozen arm never injects its written memory, and terminal browser
episodes are independent, so this nonterminal event is disclosed but lies
outside the terminal behavioral path.

The offline P3 evidence exporter and unified quality gate now report failed
attempts, retries, content-filter hits, exhausted calls, all-round/terminal
held-out route LLM errors, non-held-out exhausted calls, and reviewer/setup
audit errors. Any terminal held-out LLM error fails formal quality. For append
or consolidated memory, any all-round held-out LLM error, non-held-out
exhausted call, or reviewer/setup audit error also fails quality because it can
alter the learned-memory path. Recovered attempts remain disclosures only.

This adds no exclusion, rerun, endpoint, arm, task, seed, threshold, prompt, or
runtime change. No completed or partial result is rewritten.

## 2026-07-15: Formal suites paused for provider resource freeze

At approximately `2026-07-15 22:49 +08:00`, successful cache writes stopped
in both active formal processes. The in-progress P3e choose-list seed-2
consolidated condition subsequently recorded eight reviewer calls in rounds
0--1 that exhausted all retries with HTTP 403 `ModelArts.81006` ("The
resource is frozen"). This is an active-memory path, so the condition cannot
be completed or interpreted from that partial execution. The concurrent
Epsilon seed-1 MMR condition had not serialized an exhausted LLM event, but
was paused prophylactically under the same provider outage.

Decision: `formal_runs_paused_provider_resource_frozen_81006`.

- stop the Epsilon and P3e formal runners before either interrupted condition
  writes `result.json`;
- retain the 9 completed Epsilon and 17 completed P3e results byte-for-byte;
- preserve the two interrupted directories under
  `runs_provider_freeze_audit/20260715_81006`;
- compute no cross-arm behavioral contrast from partial or completed formal
  artifacts while the matrix is incomplete;
- require a successful no-cache provider probe before resumption;
- rerun each interrupted or remaining condition individually from round zero,
  probing before each condition and validating its engineering quality before
  proceeding;
- verify the pre-outage completed-artifact hashes after resumption;
- retain the unchanged preregistered configurations, caches, arms, tasks,
  seeds, endpoints, thresholds, and claim rules.

The recovery launcher is external to the frozen agent runtime. It selects only
the 16 unfinished Epsilon conditions and 37 unfinished P3e conditions; the
completed 9+17 condition directories are never passed to a runner.

At `2026-07-15T23:46:16+08:00`, a one-attempt, no-cache provider probe still
failed with `ModelArts.81006` in 0.797 seconds. Recovery therefore remains
unlaunched. The completed-artifact checkpoint verified 202 hashed files, both
runtime-source freeze records and all embedded source hashes with zero
failures.

## 2026-07-16: Provider resource remains frozen

At `2026-07-16T00:16:32+08:00`, a second one-attempt, no-cache provider probe
failed with the same HTTP 403 `ModelArts.81006` response in 0.656 seconds.
The recovery launcher verified the completed-artifact checkpoint before the
probe and did not start any Epsilon, P3e, sensitivity, Zeta, or finalizer
worker.

Decision remains `formal_runs_paused_provider_resource_frozen_81006`.

At `2026-07-16T01:23:26+08:00`, a later one-attempt, no-cache probe again
failed with `ModelArts.81006` in 0.734 seconds. The checkpoint verified first,
and no formal or finalizer process was launched.

At `2026-07-16T01:35:32+08:00`, the next one-attempt, no-cache probe failed
with the same code in 0.703 seconds. The formal matrix remains unchanged at
9/25 Epsilon controls and 17/54 P3e conditions, with sensitivity and Zeta
unstarted. No worker was launched.
