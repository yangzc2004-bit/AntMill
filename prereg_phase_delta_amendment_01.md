# Phase Delta Amendment 01: Plan-endpoint model roster and parallel smoke

**Status:** Frozen before any replacement-model smoke outcome data.

This amendment supersedes only the Phase Delta roster and smoke scheduling in
`prereg_phase_delta.md`. All task settings, arms, endpoints, statistical gates, and stop rules
not explicitly changed here remain in force.

## 1. Replacement roster and endpoint

The models are:

1. `deepseek-v4-flash`
2. `glm-5`
3. `kimi-k2.6`

All use:

- base URL: `https://api.modelarts-maas.com/plan/v2`;
- credential environment variable: `MODELARTS_MAAS_KEY`;
- OpenAI-compatible Chat Completions API;
- solver temperature `0.7`;
- solver maximum output `256` tokens;
- reviewer maximum output `512` tokens;
- default reasoning/thinking behavior, with no `disable_thinking` request flag.

## 2. Parallel smoke scheduling

Launch one frozen-arm smoke for each model concurrently. Each smoke uses fresh, model-specific
output and cache directories and the original Delta smoke settings:

- seed `0`;
- `T=1`;
- heldout size `12`;
- train size and train batch `0`;
- four solvers, yielding exactly 48 heldout routes per model;
- `15x15` trap maze, `maze_min_shortest=30`, `max_steps=120`, `state_guided`;
- `retrieval_k=6`, `library_cap=80`, relevance-only GA retrieval with lambda and recency both
  equal to zero;
- cache disabled and `skip_final_train=true`.

Set each process to concurrency `8`, for an aggregate scheduled concurrency of `24`. This is a
request-scheduling choice only; no task, model, prompt, arm, or analysis setting changes.

## 3. Interpretation

Run `model-smoke` independently for each completed result. A model that fails its own smoke gate
is `not_evaluable`; its failure does not affect the other two model smokes. Only a completed
result with a passing smoke report may enter the original Phase Delta formal triangle.

The earlier Grok/GPT gateway artifacts remain ineligible for all smoke and formal analyses.
