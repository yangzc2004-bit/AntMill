# Phase Gamma P2 execution appendix

Status: written and frozen after the P1/P1b decisions and before generating any P2 model-smoke or formal data.

This appendix fixes implementation details left open by `prereg_phase_gamma.md`. It does not modify the P2 scientific gate.

## 1. Qwen smoke

Primary model identifier: `qwen3-32b` on the same ModelArts MaaS OpenAI-compatible endpoint.

The first smoke is a single frozen arm with seed 0, `T=1`, no training or writes, heldout 12, four independent solvers, trap maze `15x15`, `maze_min_shortest=30`, `max_steps=120`, `state_guided`, `retrieval_k=6`, and cache disabled. This produces exactly 48 heldout routes.

Thinking is disabled through both:

- request body `enable_thinking=false`;
- the preregistered `/no_think` prompt marker.

The first smoke uses `max_tokens_solver=256`. Smoke passes only if:

- exactly 48 routes are present;
- success is in the inclusive interval [0.25, 0.85];
- action parse rate, defined as `1 - mean(route.parse_failure_rate)`, is at least 0.95;
- exhausted-call LLM error rate, defined as heldout route `llm_error_count / total heldout route steps`, is at most 0.01;
- the run completes without an endpoint/model-identifier failure.

Transient retries and content-filter retries are reported but do not fail the smoke unless they produce exhausted calls above the error-rate threshold.

If the 256-token smoke fails only the parse-rate criterion while the endpoint/model remains usable, repeat the same smoke once with `max_tokens_solver=512` in a new cache/output directory. If 512 passes, all formal Qwen arms use 512. No other Qwen prompt, temperature, parser, or token-limit tuning is allowed.

If the model identifier or thinking control is unsupported, or if the 512-token retry fails, label Qwen `not_evaluable` and run the same smoke protocol with model identifier `glm-5.1`. A smoke failure is not a model-boundary result.

## 2. Formal P2

After a smoke pass, run the selected model with seeds 0-2, `T=4`, heldout 12, train batch 4, train pool 24, and arms frozen / append / consolidated. All arms use the token limit and thinking-control settings that passed smoke. Cache paths and run IDs are isolated from DeepSeek and smoke data.

The primary gate remains `consolidated vs frozen`. Append is secondary. Because P1b did not pass its manipulation check, no P2 rescue arm will be run regardless of the P2 phenomenon result.

