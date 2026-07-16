# Phase Delta decision log

## 2026-07-12: Grok-4.5 smoke stopped before outcome generation

The supplied `grok.txt` contained an API URL and key for an OpenAI-compatible gateway. The URL
required the `/v1` suffix; after normalization, its model catalog exposed both `grok-4.5` and
`grok-4.5-latest`.

Before interpreting any maze route, an engineering-only direct `grok-4.5` Chat Completions request
returned HTTP 502 from the gateway. The formal 48-route frozen-arm smoke had already started but
had not written a route result; it was stopped while the runner was retrying failed requests.

Decision: `delta_grok45_not_evaluable_gateway_502`.

- Retain `runs_maze_delta_grok45_smoke/` for manifest-level audit only.
- Do not run the Delta smoke gate, formal triangle, or statistical gate on this artifact.
- Do not treat this as a negative Grok result or as evidence about the shared-memory phenomenon.
- Resume only with a gateway that returns valid Chat Completions responses for the exact
  `grok-4.5` identifier, or with an explicitly preregistered endpoint/model amendment.

## 2026-07-12: GPT-5.6-terra smoke restarted with higher concurrency

The first `gpt-5.6-terra` smoke launch used concurrency 4. An engineering-only direct request
had established a roughly six-second completion latency, making that setting too slow for the
time-bounded 48-route smoke. The launch was stopped before any `result.json` was written and
restarted in fresh output/cache directories at concurrency 12.

This changes only request scheduling. Model, endpoint, seed, arm, task set, prompts, token limits,
and all smoke eligibility criteria remain unchanged. The stopped low-concurrency artifact is not
eligible for any analysis.

## 2026-07-12: GPT-5.6-terra smoke stopped for time budget before outcome generation

The restarted concurrency-12 smoke also did not write a completed `result.json` within the
available time budget. The gateway had passed a single-request Chat Completions health check, so
this is not an endpoint-availability failure. It is a throughput limitation under the
step-by-step maze workload.

Decision: `delta_gpt56terra_smoke_stopped_time_budget`.

- Retain both GPT smoke output directories for manifest/deviation audit only.
- Do not run the smoke gate, formal triangle, or statistical gate on either artifact.
- Do not call this a GPT non-replication or a GPT not-evaluable scientific result.
- Resume only with more wall-clock budget, a faster gateway for the same exact model identifier,
  or an explicitly preregistered reduced-cost screening protocol.

## 2026-07-12: GPT-5.6-terra capacity smoke authorized

At the user's request, the same 48-route frozen-arm smoke will be restarted in a fresh
output/cache directory at concurrency 24. This is a request-scheduling change only: model,
endpoint, arm, seed, tasks, prompts, token limits, and all smoke eligibility criteria remain as
frozen in `prereg_phase_delta.md`.

The two earlier stopped GPT artifacts contain no completed `result.json`; this capacity-smoke
attempt is the only GPT smoke artifact eligible for the preregistered smoke gate.

## 2026-07-12: GPT-5.6-terra capacity smoke exceeded the execution budget

The concurrency-24 capacity smoke started at 14:01:33 +08:00 and was stopped after 19.2 minutes
without writing a completed `result.json`. This is more than three times the approximately
six-minute optimistic lower bound implied by 48 routes, a 30-step minimum path, 24-way request
scheduling, and the observed single-request latency.

Decision: `delta_gpt56terra_capacity_smoke_not_completed_within_budget`.

- The capacity-smoke artifact is not eligible for the smoke gate or scientific analysis.
- The gateway remains usable for individual Chat Completions requests but is not suitable for a
  time-bounded, step-by-step maze replication at this model and endpoint.
- Do not start the formal Delta triangle on this gateway.

## 2026-07-12: Plan-endpoint roster replacement and parallel smoke

Before replacement-model outcomes, the project froze
`antmill_submission_blueprint_v1_amendment_01.md` and
`prereg_phase_delta_amendment_01.md`. The final planned Phase Delta roster is
`deepseek-v4-flash`, `glm-5`, and `kimi-k2.6` through the ModelArts Plan endpoint.

One frozen-arm smoke per model is authorized in parallel at concurrency 8 per process, with
aggregate scheduled concurrency 24. The prior Grok/GPT artifacts remain infrastructure-only
non-results.

## 2026-07-12: Plan-endpoint parallel smoke exceeded the execution budget

The three replacement-model frozen-arm smokes were launched concurrently at aggregate scheduled
concurrency 24. After approximately 35.3 minutes, none had written a completed `result.json`.
All three processes were stopped together.

Decision: `delta_plan_parallel_smoke_not_completed_within_budget`.

- The DeepSeek-V4-Flash, GLM-5, and Kimi-K2.6 Plan smoke artifacts are not eligible for smoke
  gates, formal analyses, or model comparisons.
- This does not contradict their successful single-request compatibility checks. It establishes
  only that the current step-by-step runner, token settings, and endpoint throughput cannot
  complete the 48-route smoke in the available execution budget.
- Do not start the formal Delta triangle under this configuration.
- A future attempt requires a separately preregistered reduced-cost protocol or a runner-level
  change that reduces model calls per route; it must not reuse these incomplete artifacts.
