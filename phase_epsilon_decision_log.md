# Phase Epsilon Decision Log

## 2026-07-14 - Controls paused before a complete condition

The `epsilon_controls` command began under the frozen protocol in
`prereg_phase_epsilon.md` and `prereg_phase_epsilon.freeze.json`. The first
condition (`n4_gt_false_seed0_epsilon_frozen_reviewer`) wrote a resumable
partial artifact and cache entries, but no condition produced `result.json`.

Execution was intentionally stopped before the full 25-condition control
matrix because the first configuration consumed a high API-token budget. This
is a resource pause, not an outcome, failure, or exclusion decision. No
partial Epsilon artifact may be analyzed or reported as evidence. The frozen
protocol, its digest, command, cache directory, and finalization scripts are
retained so that a later authorized run can be resumed or restarted and
reported transparently.

## 2026-07-14 - Budget confirmed; frozen controls resumed

The budget was explicitly confirmed after the pause. Controls were restarted
with the same frozen command and cache directory. Two initial launcher
attempts terminated during PowerShell startup before Python constructed an LLM
client; they wrote no complete result and are not part of the experiment.
The working launcher loads the API key from the local `.env` only inside its
hidden child process and uses an encoded PowerShell command to preserve the
frozen CLI exactly. A supervisor will start the frozen sensitivity suite only
after controls complete and their evidence manifest is successfully written.

## 2026-07-14 - Provenance sidecar added

After the first complete frozen-control condition and before any cross-arm
contrast existed, an audit found that each run's `manifest.json` recorded the
preregistration path but omitted the document digest and source content
digests promised by the preregistration. No configuration or outcome field was
missing.

The runtime modules already loaded by the controls process were frozen in
`epsilon_runtime_source.freeze.json`, together with the preregistration
SHA-256 and Git HEAD. Final Epsilon evidence manifests verify those hashes and
record the result. This is a metadata-only correction: no runner behavior,
arm, endpoint, contrast, threshold, seed, or outcome analysis changed, and
completed run artifacts are not rewritten.

## 2026-07-14 - Separate exact supply-yoke phase frozen

The review audit identified that `epsilon_shared_append_cap14` is only a fixed
terminal-capacity match, not exact seed-by-seed and round-by-round equality.
Before any `epsilon_shared_consolidated` condition produced a complete
`result.json`, the independent Phase Zeta protocol was frozen in
`prereg_phase_zeta.md` and `prereg_phase_zeta.freeze.json`.

Zeta does not reopen or alter the Epsilon matrix. After Epsilon controls and
sensitivity complete, it extracts only consolidated active-pool-size metadata,
freezes source hashes, and runs one exact retrievable-supply-yoked append arm.
Its manipulation check precedes any pool-size interpretation.

## 2026-07-14 - Non-fatal HTTP client cleanup warning

After the first controls condition completed and wrote all 288 held-out route
records, `httpx` emitted an asynchronous client-close warning because a
connection cleanup task reached an event loop that `asyncio.run` had already
closed. The controls process continued into `epsilon_private_consolidated`,
and cache files continued to be written.

This warning occurs after the completed condition artifact is durable. It is
not a route, parse, browser, model-call, or outcome failure and does not
justify rerunning or excluding the condition. Core runtime code remains
unchanged during the frozen controls and sensitivity suites; completeness and
LLM-error fields are audited in the final evidence report.

## 2026-07-14 - Incremental engineering-quality audit

After the first complete Epsilon condition and the first complete MiniWoB
task-family matrix were available, an engineering-only audit was run without
computing or interpreting cross-arm behavioral contrasts.

The Epsilon frozen seed-0 result contains all 48 expected terminal routes,
zero terminal parse failures, and zero terminal route-level LLM errors. Its
global LLM summary records two content-filter errors and two retries across
7,089 network calls; both calls recovered, so these are reported separately
from route-level failures. The preregistration and frozen runtime-source hashes
match. The evidence exporter now records API errors, retries, content-filter
hits, and terminal route-level LLM errors in separate columns; this reporting
change adds no exclusion rule or outcome gate.

The first complete MiniWoB family contains all nine arm-by-seed results and
1,728 routes. Its partial formal-quality audit has parse rate 1.0, zero
infrastructure-error routes, zero bid errors, passing reviewer-summary schema,
and no failed run-level check. This audit is not a P3 outcome analysis and does
not authorize a generalization claim before the complete 54-condition gate.

## 2026-07-15 - Outcome-blind protocol-semantics clarification

An implementation-to-manuscript audit was performed without reading any
cross-arm behavioral contrast. Two frozen runtime details are now made
explicit in the reporting contract.

First, private consolidation invokes the same reviewer-operation grammar once
for each agent's single trajectory and private pool, whereas shared
consolidation invokes it once over the four agent trajectories and the shared
pool. With a six-operation cap per call, this intervention removes cross-agent
memory access but does not equalize reviewer-call count, prompt composition,
or total operation opportunity. The shared-versus-private result will
therefore be reported as a protocol-level contrast, not as a one-factor causal
estimate of sharing alone.

Second, the frozen append writer deterministically treats a near-duplicate
addition as agreement with an existing item and increments its vote. It does
not run the joint reviewer-issued `EDIT`/`DOWNVOTE` pool update used by
consolidation, but it is not a literal no-deduplication append log. The paper
will call this the append/agree protocol and will not say that entries are
"never merged."

This clarification changes no runtime source, arm, seed, endpoint, analysis,
quality gate, or stopping rule. Completed and partial run artifacts are not
rewritten.

## 2026-07-15 - All-round LLM-failure disclosure

After eight Epsilon control conditions had completed, an engineering-only
audit inspected error and completeness fields without computing any
cross-arm behavioral contrast. The previously reported terminal-only route
error column was insufficiently explicit about recovered and nonterminal
failures.

Across those eight artifacts, the API client recorded 809 failed attempts,
688 retries, and 65 content-filter hits. There were 121 calls that remained
failed after all retries:

- one content-filtered train-solver call in
  `epsilon_private_consolidated`, seed 0, round 3;
- 120 held-out solver calls during one connection-error window in
  `epsilon_shared_consolidated`, seed 1, round 2.

The same completed artifacts contain one held-out parse failure in
`epsilon_shared_consolidated`, seed 0, round 2. All completed conditions have
zero terminal-round route LLM errors and zero terminal-round parse failures.
The round-2 held-out outage does not enter the training writer, whereas the
single train-solver failure is retained as an auditable one-step no-op under
the frozen runtime policy.

The evidence exporter and manuscript diagnostics now report API errors,
retries, content-filter hits, exhausted calls by context, held-out route LLM
errors as all-round/terminal counts, and parse failures as
all-round/terminal counts. This disclosure creates no post-hoc exclusion,
rerun, endpoint change, or behavioral gate.
