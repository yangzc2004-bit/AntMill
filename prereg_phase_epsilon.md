# Phase Epsilon Preregistration: Mechanism Separation and Robustness

Status: frozen before any Phase Epsilon outcome data are generated.

Pre-execution amendment 01 (2026-07-14): the original command block omitted
the fixed maze parameters listed in Section 2. No Epsilon run had been started.
The command block below now passes those parameters explicitly; this amendment
does not add, remove, or alter any arm, seed, endpoint, contrast, or decision
rule.

## 1. Objective

Phase Epsilon addresses the remaining mechanism and robustness questions from the
Beta and Gamma studies without changing the paper's bounded claim. The target
claim is conditional: under the tested shared-memory consolidation protocol,
strategy supply can be compressed and looping can be amplified. Phase Epsilon
separates the roles of sharing, consolidation, memory capacity, retrieval
diversity, and selected protocol parameters.

This phase does not claim that all shared memories, all LLMs, or all real-world
agent tasks exhibit this behavior.

## 2. Fixed Environment and Common Protocol

Unless an arm explicitly overrides a setting, all Phase Epsilon runs use:

- the preregistered 15x15 trap-maze microscope;
- four solver agents, six interaction rounds, 24 training mazes, batches of
  four training mazes, and 12 held-out evaluation mazes;
- locally observed state, state-guided reflection, a 120-step route limit, and
  the existing train/evaluation split construction;
- DeepSeek-V3 through the configured provider, solver and reviewer temperature
  0.7, retrieval capacity k=6, GA relevance scoring, GA lambda 0.0, GA recency
  weight 0.0, reviewer budget six operations per review, and merge similarity
  threshold 0.80;
- five fresh seeds (0, 1, 2, 3, 4) for the control suite and three fresh seeds
  (0, 1, 2) for the sensitivity suite;
- a new run directory and new cache namespace for every suite. Existing Beta,
  Gamma, MiniWoB, and SCBench outputs are not reused as Epsilon outcomes.

The append-capacity control fixes the shared append library capacity at 14. This
value is the rounded mean final shared-consolidated pool size observed in Beta
E2 (14.2 across its five seeds). It is a fixed terminal-capacity-matched
control, not a claim of exact round-by-round pool-size equality.

## 3. Control Suite

Run ID prefix: `epsilon_controls`.

All five arms are run for all five seeds:

1. `epsilon_frozen_reviewer`: frozen shared write-only memory with reviewer
   generation enabled but no reviewer writes.
2. `epsilon_private_consolidated`: one independent memory pool per agent, with
   the same reviewer operation protocol applied within that agent's own pool.
   This makes the existing private-memory interpretation explicit: it is
   per-agent consolidation without cross-agent sharing.
3. `epsilon_shared_consolidated`: the shared reviewer-consolidated reference.
4. `epsilon_shared_append_cap14`: shared append-only memory with a hard
   capacity of 14 after every write update.
5. `epsilon_shared_consolidated_mmr`: shared reviewer-consolidated memory with
   greedy MMR reranking over GA-ranked candidates. The fixed relevance weight is
   0.70 and candidate redundancy is text-embedding cosine similarity.

Primary endpoint: held-out loop rate at round 6. Secondary endpoints are
success rate, success-only excess steps, failure-penalized excess steps,
stagnation rate, distinct injected strategy count, final pool size, and
retrieval diversity diagnostics.

The three prespecified mechanism contrasts are:

- shared consolidation minus private consolidation;
- capacity-matched shared append minus shared consolidation;
- diversity-aware shared consolidation minus ordinary shared consolidation.

These contrasts estimate directional effects and uncertainty. A null or
opposite result will be reported as such; no contrast is treated as a required
replication gate for the others.

## 4. Sensitivity Suite

Run ID prefix: `epsilon_sensitivity`.

All arms use shared reviewer consolidation and are compared with the
`epsilon_sens_reference` arm, which has the common protocol above. Each arm is
run for seeds 0, 1, and 2:

1. `epsilon_sens_k3`: retrieval capacity k=3.
2. `epsilon_sens_k10`: retrieval capacity k=10.
3. `epsilon_sens_cap40`: shared library capacity 40.
4. `epsilon_sens_ops3`: reviewer budget three operations.
5. `epsilon_sens_ops9`: reviewer budget nine operations.
6. `epsilon_sens_merge07`: merge threshold 0.70.
7. `epsilon_sens_merge09`: merge threshold 0.90.
8. `epsilon_sens_recency1`: GA recency weight 1.0.

The sensitivity suite is descriptive robustness evidence. It reports the same
endpoint family as the control suite and does not turn a parameter sweep into
post-hoc model selection.

## 5. Endpoint Definitions

For a held-out route with path p_0, ..., p_n and goal g:

- A route is a loop if either (a) any position is visited at least ten times, or
  (b) its final segment contains two consecutive copies of a cycle of length
  2 through 8 and the newest copy does not contain a position with Manhattan
  distance to g strictly smaller than the best distance before that copy.
- Route-level stagnation is the fraction of post-start positions p_i for which
  p_i has appeared earlier in the route and its Manhattan distance to g is not
  strictly smaller than the best distance reached before p_i.
- Loop rate and stagnation rate are averages over all held-out routes. Success
  rate is the fraction reaching g. Success-only excess steps is reported only
  among successful routes and is never interpreted without failure-penalized
  excess steps.

## 6. Analysis and Reporting

For each contrast, route observations are paired by seed, round, held-out maze,
and agent where both arms have a valid record. The primary estimate is the
equal-weight mean of per-seed paired route effects.

Uncertainty uses a hierarchical paired bootstrap: resample seed clusters with
replacement, resample paired route observations within each selected seed, then
average seed means. Report 95 percent percentile intervals, the number of
paired routes, the number of seeds, and a compact per-seed effect table for the
primary endpoints. Existing pooled paired-bootstrap summaries remain
supplementary rather than replacements for seed-level reporting.

All arms, seeds, valid routes, invalid routes, cache statistics, and failure
events are reported. We will not drop a seed for an unfavorable outcome. A
technical rerun is allowed only for a documented infrastructure failure that
prevents valid route generation, using the identical frozen configuration.

## 7. Constraints and Deviations

No additional control arm, parameter setting, metric definition, outcome
threshold, or model-selection rule will be added before this phase is reported.
Any implementation correction or unavoidable deviation will be appended to a
Phase Epsilon decision log before inspecting corrected outcome summaries.

## 8. Commands

The formal invocations are:

```powershell
python -m sec.run_maze_alpha --phase epsilon_controls `
  --model DeepSeek-V3 --base-url https://api.modelarts-maas.com/v2 --api-key-env MODELARTS_MAAS_KEY `
  --seeds 0,1,2,3,4 --T 6 --train-batch 4 --train-size 24 --heldout-size 12 `
  --maze-width 15 --maze-height 15 --maze-family trap --maze-min-shortest 30 `
  --maze-agent-mode state_guided --max-steps 120 --retrieval-k 6 --library-cap 80 `
  --concurrency 8 --skip-final-train `
  --out-dir runs_maze_epsilon_controls --cache-dir cache_maze_epsilon_controls

python -m sec.run_maze_alpha --phase epsilon_sensitivity `
  --model DeepSeek-V3 --base-url https://api.modelarts-maas.com/v2 --api-key-env MODELARTS_MAAS_KEY `
  --seeds 0,1,2 --T 6 --train-batch 4 --train-size 24 --heldout-size 12 `
  --maze-width 15 --maze-height 15 --maze-family trap --maze-min-shortest 30 `
  --maze-agent-mode state_guided --max-steps 120 --retrieval-k 6 --library-cap 80 `
  --concurrency 8 --skip-final-train `
  --out-dir runs_maze_epsilon_sensitivity --cache-dir cache_maze_epsilon_sensitivity
```

The exact source revision and this document's SHA-256 digest are recorded in
the generated run manifests and in `prereg_phase_epsilon.freeze.json`.
