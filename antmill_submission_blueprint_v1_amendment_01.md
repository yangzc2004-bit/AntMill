# AntMill Submission Blueprint v1 Amendment 01

**Date:** 2026-07-12  
**Scope:** Replace the planned three-model maze replication roster only. All mechanism claims,
benchmark choices, endpoint definitions, and stop rules in `antmill_submission_blueprint_v1.md`
remain unchanged.

## Decision

The Phase Delta cross-model maze roster is:

1. `deepseek-v4-flash`
2. `glm-5`
3. `kimi-k2.6`

All three models are accessed through the same ModelArts Plan OpenAI-compatible endpoint:

```text
https://api.modelarts-maas.com/plan/v2
```

and use the existing `MODELARTS_MAAS_KEY` credential.

## Rationale

The originally named Grok/GPT routes did not produce any completed smoke outcome: the supplied
Grok gateway returned HTTP 502 for Chat Completions and the supplied GPT gateway could not finish
the step-by-step smoke within the capacity budget. Those artifacts remain non-results.

By contrast, the Plan endpoint returned valid Chat Completions responses for all three replacement
identifiers. A 24-request DeepSeek microburst completed without errors. These compatibility checks
are engineering evidence only; they do not enter the maze analysis.

## Claim impact

- The manuscript may name only the final three-model roster above as the planned Phase Delta
  replication set.
- Grok and GPT gateway attempts are described, if at all, only as infrastructure exclusions in
  the supplement or audit trail.
- No completed formal outcome is reinterpreted or removed by this amendment.
