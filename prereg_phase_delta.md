# Phase Delta preregistration: three-model maze replication triangle

**Status:** Frozen before any Phase Delta smoke or formal outcome data.  
**Purpose:** A time-bounded cross-model replication attempt for the controlled maze phenomenon
described in `antmill_submission_blueprint_v1.md`.

## 1. Scope

Phase Delta does not rerun the V3 five-arm factor-decomposition matrix. It tests the minimal
three-arm triangle:

- `frozen`: reviewer writes, but solvers never retrieve the pool;
- `shared_append`: shared append-and-retrieve memory without LLM consolidation;
- `shared_consolidated`: shared LLM-issued `ADD`/`EDIT`/`UPVOTE`/`DOWNVOTE` consolidation.

The model roster, evaluated independently, is:

1. `deepseek-v4-flash`
2. `grok-4.5`
3. `gpt-5.6-terra`

Each model requires its own OpenAI-compatible endpoint and API-key environment variable. A missing
endpoint/model identifier/key, or a failed semantic smoke, yields `not_evaluable`; no substitute
model is permitted.

## 2. Common maze protocol

All model conditions use:

- `15x15` trap mazes with `maze_min_shortest=30`;
- local observations and `state_guided` action execution;
- four independent solvers, coupled only by the arm-specific memory pool;
- `max_steps=120`, `retrieval_k=6`, `library_cap=80`;
- relevance-only Generative-Agents-style retrieval with `ga_lambda=0` and `ga_recency=0`;
- identical sanitizer, prompt family, cache-salt discipline, route tracing, and memory audit schema
  as the V3 implementation;
- solver temperature `0.7`, reviewer maximum output `512` tokens, solver maximum output `256`
  tokens unless the one permitted parse-only retry below is invoked;
- cache disabled for smoke; isolated cache directories for formal runs.

The exact endpoint, API version, request-body settings, date, model identifier, and price-accounting
source are written into every formal run manifest before the first request.

## 3. Engineering smoke

For each candidate model, run only the frozen arm with:

- seed `0`;
- `T=1`;
- heldout size `12`;
- train size and train batch `0`;
- `skip_final_train=true`;
- four solvers, yielding exactly 48 heldout routes;
- cache disabled.

Smoke eligibility:

1. exactly 48 heldout solver routes are written;
2. task success is within `[0.25, 0.85]`;
3. action parse rate is at least `0.95`;
4. exhausted LLM-error rate, measured as `llm_error_count / total_route_steps`, is at most `0.01`;
5. the model identifier and request settings are accepted by the provider.

If only the parse criterion fails at 256 solver tokens, repeat the same smoke exactly once at 512
solver tokens in a fresh output/cache directory. No other prompt, parser, temperature, or action
schema tuning is allowed. If the retry fails, the model is `not_evaluable`.

Smoke artifacts are engineering evidence only and do not enter the formal statistics.

## 4. Formal matrix

After a model passes smoke, run:

| Item | Fixed value |
|---|---|
| Arms | `frozen`, `shared_append`, `shared_consolidated` |
| Seeds | `0, 1, 2` |
| Rounds | `T=4` |
| Heldout mazes | `12` per round and solver |
| Training mazes | `4` per round and solver |
| Final round | Evaluation only; no final-round write |
| Cache | Isolated from smoke, V3, and all other model runs |
| Pairing | Same maze, seed, round, and solver slot across arms |

No rescue, archive, compression, private-memory, or no-memory Delta arm will be run.

## 5. Primary gate and statistics

The primary contrast is `shared_consolidated - frozen` at terminal round `t=3`.

Primary endpoints:

1. `failure_penalized_steps`;
2. `looped` (the maze loop/stall burden).

Success, success-only excess steps, route diversity, pool size, distinct injected experiences,
retrieval entropy, effective memory size, and latency/token statistics are secondary or
mechanism-audit outcomes.

For each endpoint, use same-maze, same-solver paired differences with a seed-clustered paired
bootstrap. Report pooled 95% intervals, paired-route count, and the three per-seed signs. Do not
treat routes as independent model replications.

The model is `delta_maze_phenomenon_positive` only if both primary endpoint intervals are entirely
above zero and both endpoint effects are harmful in at least two of three seeds. Any valid outcome
that does not meet this condition is `delta_not_detected_or_underpowered`.

## 6. Stop rule

- If two or three models are positive, workflow transfer may use the first two positive models
  under fixed priority `deepseek-v4-flash`, `grok-4.5`, `gpt-5.6-terra`.
- If exactly one model is positive, workflow transfer may use only that model and all transfer
  claims are model-conditioned.
- If no model is positive, stop workflow expansion and retain a bounded V3-plus-nonreplication
  submission.
- A provider/access failure is reported separately as `not_evaluable`; it is not a negative
  scientific result.
