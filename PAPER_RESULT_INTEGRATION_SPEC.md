# Paper Result Integration Specification

Status: fixed before completion of the Epsilon controls, Epsilon sensitivity,
Zeta exact-yoke, and MiniWoB P3 formal evaluations.

This document specifies how fresh evidence will enter the manuscript. It does
not add an outcome gate, change a preregistered analysis, or authorize a claim
before the unified evidence gate reports `ready_for_paper_revision`.

## Page Budget

`PAPER_PAGE_BUDGET.md` is the binding layout constraint. After
outcome-independent compaction, the pre-table baseline occupies approximately
5.4 of the seven permitted technical pages, leaving about 1.6 pages before the
generated result surfaces and a planned 0.10-page safety reserve. Fresh
evidence must still replace or merge with existing material rather than
accumulate as independent tables and subsections.

In particular:

- the mechanism controls are the highest-priority main-text result surface;
- the full sensitivity envelope is supplementary, with only its bounded
  conclusion in the main text;
- the MiniWoB pooled result and task-family heterogeneity must use a compact
  display that replaces or extends an existing boundary display;
- Zeta and MMR do not receive standalone main-text subsections;
- pages 8--9 may contain only references;
- the AuthorKit reproducibility checklist is compiled and uploaded separately
  from the main paper.

The anonymous supplement entry point is
`paper_draft/antmill_memory_aaai27_supp.tex`. It must input the generated sensitivity,
heterogeneity, exact-yoke, data-quality, and provenance material and compile to
`paper_draft/antmill_memory_aaai27_supp.pdf`. Main-paper and supplement PDFs receive
separate hash-bound visual audits.

The reproducibility checklist is generated from the unmodified AuthorKit
template and the isolated
`reproducibility_checklist_responses_memory.json` answer/evidence map. It compiles as a third,
standalone PDF and receives its own hash-bound visual audit for the separate
OpenReview checklist field.

`sec.environment_manifest` records the local OS, CPU, installed memory, Python,
BrowserGym, Playwright, MiniWoB++, and analysis-library versions. The supplement
reports hosted-LLM provider hardware as unavailable when the API does not expose
it; no provider accelerator is inferred.

## Evidence Gate

Paper integration starts only after all of the following artifacts exist and
`runs_revision_evidence/revision_evidence.json` reports complete evidence:

- `runs_maze_epsilon_controls_stats/evidence_manifest.json`
- `runs_maze_epsilon_sensitivity_stats/evidence_manifest.json`
- `runs_maze_zeta_exact_yoke_stats/evidence_manifest.json`
- `runs_miniwob_gamma_p3e_stats/p3_gate_report.json`
- `runs_miniwob_gamma_p3e_stats/append_secondary/p3_gate_report.json`

Before behavioral interpretation:

- all expected run and terminal-route counts must be present;
- all preregistration and frozen-source hashes must match;
- maze-suite quality diagnostics must separately report API failed attempts,
  retries, content-filter hits, calls exhausted after all retries, held-out
  route LLM errors as all-round/terminal counts, and parse failures as
  all-round/terminal counts; exhausted calls must also be classified as
  held-out solver, train solver, reviewer, or other, and do not license
  post-hoc route or run exclusion;
- the P3e launch script and every Python runtime module listed in
  `p3e_runtime_source.freeze.json` must retain its pre-launch SHA-256 digest;
  any mismatch withholds MiniWoB behavioral estimates;
- MiniWoB quality diagnostics must report API failed attempts, retries,
  content-filter hits, exhausted calls, held-out route LLM errors as
  all-round/terminal counts, non-held-out exhausted calls, and reviewer/setup
  audit errors. Any terminal held-out LLM error withholds the evaluation.
  For append or consolidated memory, any all-round held-out LLM error,
  non-held-out exhausted call, or reviewer/setup audit error also withholds
  behavioral estimates because it can alter the learned memory path. A
  nonterminal error in the frozen write-only arm is disclosed but does not
  fail the terminal behavioral-path gate because that arm never injects its
  written memory and each terminal browser episode is independent;
- Zeta must pass all 30 seed-by-round size-yoke checks; every row verifies
  target budget, normalized selected supply, and the actual
  `active_candidate_count` on every recorded retrieval in that round;
- the generated MiniWoB environment summary must be backed by exactly the 54
  current `runs_miniwob_gamma_p3e` formal manifests; every source hash, sibling
  result, formal-phase label, and frozen browser/package/task field must match
  the summary;
- any MiniWoB formal quality warning must be resolved or explicitly reported
  as making that evaluation non-evaluable.

A complete 54-run quality-warning report may satisfy artifact completeness
only when its behavioral payload is withheld and its source/provenance matrix
is intact. It sets `p3_quality_clear` to false, cannot satisfy the Goal's
real-task boundary requirement, and licenses only the non-evaluable manuscript
branch.

Likewise, a completed Zeta suite with a failed size-yoke manipulation may be
reported as non-evaluable, but the Goal's exact-pool-size requirement is
complete only when all 30 seed-by-round manipulation checks pass.

## Main-Text Results

### Table A: Mechanism-Separating Controls

Place after the existing write-side compression audit in
`paper_draft/antmill_memory_aaai27_en.tex`. It must replace or merge with an existing
result table so that its net main-text cost remains within the fixed page
budget.

Rows:

1. shared-consolidated minus private-consolidated;
2. cap-14 append minus shared-consolidated;
3. MMR consolidated minus standard shared-consolidated;
4. exact-size-yoked append minus shared-consolidated.

Columns:

- success;
- success-only excess steps;
- failure-penalized steps;
- loop rate;
- stagnation rate.

Each cell reports mean paired difference and seed-clustered 95% CI. The caption
must define the subtraction direction, indicate which sign is worse for each
endpoint, state the terminal round, and report the number of seeds. Zeta is
shown only when its manipulation decision is `zeta_supply_yoke_evaluable`.

Interpretation order:

1. private consolidation compares a shared joint-reviewer protocol with
   per-agent consolidation; the text must retain that the private arm uses
   four per-agent reviewer calls per training maze while the shared arm uses
   one joint call, so the contrast removes cross-agent memory access but does
   not identify sharing alone;
2. cap-14 and exact yoke bound pool-size explanations;
3. MMR is interpreted first as a manipulation check and only then as a
   behavioral intervention.

No row licenses a joint "performance" claim. Success, efficiency, looping, and
stagnation are interpreted endpoint by endpoint.

The fixed-capacity and exact-yoke append controls use the frozen
append/agree writer: per-agent reflections enter a shared pool and
near-duplicate additions receive a deterministic agreement upvote. They are
not described as "never merged" or as a literal no-deduplication append log;
their separating property is the absence of joint reviewer-issued
`EDIT`/`DOWNVOTE` pool consolidation.

### Table B: Sensitivity Envelope

Place the full table in the supplement. The Mechanism Interventions and
Boundaries section receives only a compact outcome-bounded summary.

Rows:

- retrieval `k=3`;
- retrieval `k=10`;
- pool cap `40`;
- reviewer operation budget `3`;
- reviewer operation budget `9`;
- merge threshold `0.7`;
- merge threshold `0.9`;
- recency weight `1`.

Columns use the same five primary endpoints as Table A. Every row is the
prespecified arm minus `epsilon_sens_reference` at the terminal round, with
mean paired difference and seed-clustered 95% CI.

All settings are reported. No "best" setting is selected. Main-text robustness
language requires directional agreement across multiple settings and seeds;
isolated reversals define the boundary of the tested protocol.
The main text must also classify all eight settings for the primary loop-rate
contrast as positive detected, negative detected, or not detected relative to
the reference. The setting lists are generated as LaTeX macros from the frozen
statistics rather than transcribed manually.

### Table C: MiniWoB Task-Family Boundary

Place before Design Implications as a compact pooled statement plus explicit
task-family heterogeneity. Its table or visual must replace or extend an
existing boundary display rather than consume an unconstrained new float.

The first block reports consolidated minus frozen at terminal `t=3`, with:

- failure-penalized cost;
- loop/stall burden;
- success;
- excess action cost;
- stall rate and loop-related auxiliary endpoints already present in
  `P3_METRICS`.

The second, clearly labeled secondary block reports append minus frozen.

For each primary contrast, report:

- equal-family mean paired difference;
- seed-clustered 95% CI;
- paired route count;
- preregistered gate decision;
- formal quality status.

The pooled result is accompanied by a six-family effect strip or compact
per-family table. Within each family, descriptive effects average seed-level
paired-route means equally; pooled estimates then average family means
equally. A pooled pass must not be described as uniform across task families.
The main text reports the sign of all three seed-level primary effects; full
values go in the appendix.
Both primary seed-sign sequences are generated as `seed 0/1/2` LaTeX macros
and must be referenced in the main paper.

## Appendix Results

The appendix contains:

- all Epsilon per-seed primary effects for every control contrast;
- all Epsilon sensitivity rows and per-seed effects;
- the 30 Zeta manipulation checks and exact target trajectory by seed;
- all MiniWoB per-family effects;
- all MiniWoB per-seed primary effects;
- Epsilon and Zeta memory summaries;
- Epsilon, Zeta, and MiniWoB data-quality tables;
- maze-suite all-round/terminal route-error and parse-failure counts plus
  exhausted-call contexts, including nonterminal warnings rather than only
  terminal summaries;
- MiniWoB API/retry/filter/exhausted counts, all-round/terminal route LLM
  errors, non-held-out exhausted calls, reviewer/setup audit errors, and the
  arm-aware terminal behavioral-path gate;
- provenance hashes and the unified evidence-gate summary.

Per-seed values are descriptive heterogeneity evidence. They are not treated as
independent confirmatory replications.

## Claim Selection

Fresh claims are selected by applying the frozen
`CLAIM_DECISION_RULES.md` and `REVISION_CLAIM_MAP.md` to the complete
artifacts. `sec.claim_decisions` records the resulting branches in
`paper_draft/generated/revision_results/claim_decisions.json`. The manuscript
must use the following order:

1. report the preregistered decision or CI;
2. report seed and task-family heterogeneity;
3. verify the intended manipulation;
4. state the narrowest supported protocol-level interpretation;
5. state the remaining alternative explanations.

The abstract and conclusion may use real-task generalization language only if
the MiniWoB primary gate passes with clear formal data quality. Otherwise they
state that the task-family replication was not detected or was not evaluable
under the frozen design.

The causal wording remains bounded even if all behavioral contrasts are
significant. Equal candidate-pool size does not equal equal content, and MMR
does not isolate write-side compression unless its diversity manipulation
succeeds.

## Figure Policy

No figure is selected or styled before the full evidence suite is complete.
The final figure must display uncertainty and heterogeneity rather than only
pooled point estimates. Candidate layouts are:

- a mechanism-control forest plot plus seed-level sign markers; or
- a two-panel boundary figure with maze controls and MiniWoB family effects.

The figure source data must be generated directly from the frozen CSV or JSON
evidence artifacts, with no manually transcribed values.

## Numerical Provenance

`sec.paper_results` generates `revision_macros.tex` and
`macro_manifest.json`. Every fresh narrative mean and confidence-interval
bound used outside a generated table must reference one of these LaTeX macros;
fresh values are not transcribed manually into the manuscript. The macro
manifest records the source artifact, contrast, metric, field, and rendered
value. `sec.manuscript_revision_audit` verifies that the manifest and macro
definitions match exactly.

## Manuscript Revision Order

1. Preserve the current formal loop and stagnation definitions.
2. Insert the mechanism-separating controls and sensitivity envelope.
3. Insert the MiniWoB boundary result and its quality statement.
4. Rewrite the abstract, contributions, design implications, limitations, and
   conclusion using the outcome-to-claim map.
5. Check every numerical manuscript claim against a generated evidence
   artifact.
6. Compile the PDF, run `sec.pdf_render_audit render`, and inspect every
   rendered page for overflow, illegible tables, overlap, and figure-caption
   mismatch.
7. Finalize the hash-bound visual audit only after all five visual checks are
   explicitly confirmed. Any later PDF or rendered-page change invalidates the
   audit.
8. Run `sec.manuscript_revision_audit`. The revision is complete only when it
   verifies the unified evidence gate, source and generated hashes, manuscript
   table inputs, every frozen claim branch, bounded claim language, PDF
   freshness relative to the claim-decision report, and the finalized visual
   audit.

The final compile entry point is `scripts/compile_revision_manuscript.ps1`.
It first rebuilds the unified evidence gate from the current source artifacts,
refuses to run unless that gate is complete and internally consistent, and
deterministically regenerates the result tables, numerical macros, claim
decisions, checklist, and environment manifest before compiling the main
paper, anonymous supplement, and checklist in their required pass order.
