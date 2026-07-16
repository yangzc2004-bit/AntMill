# Phase Gamma P3 execution amendment 02: complete primary-family smoke matrix

Status: frozen on 2026-07-14 before generating any P3c smoke outcome data.

## Trigger

The bid-aware P3b smoke directory contains valid engineering smoke results for
`click-button` and `choose-list` only. Those two families establish that the
repaired action interface can execute bid-addressed actions, but they do not
constitute the six-family smoke matrix required by
`prereg_phase_gamma_p3_execution.md`. They cannot authorize the P3 formal
matrix and are retained as partial calibration artifacts only.

## Frozen P3c smoke execution

Run a fresh, complete smoke matrix in:

- `runs_miniwob_gamma_p3c_smoke`
- `cache_miniwob_gamma_p3c_smoke`

The matrix contains all six original primary families, in the fixed order:

1. `click-button`
2. `choose-list`
3. `enter-text`
4. `click-checkboxes`
5. `login-user`
6. `use-autocomplete-nodelay`

For every family, run frozen, append, and consolidated arms at seed 0 with
`T=1`, two held-out instances, two train instances, four solver agents,
`max_steps=15`, and cache disabled. This yields eight held-out routes per
arm-family result and 144 held-out routes total.

All base-appendix smoke requirements and amendment-01 semantic calibration
requirements apply unchanged: route count, parse rate, infrastructure error
rate, hash agreement, reviewer-summary schema, bid error rate, and at least
one successful route per family across arms. The smoke report must use only
the P3c directory. P3b outcomes are not merged with P3c outcomes.

## What remains unchanged

This amendment changes no primary/replacement task, arm definition, model,
prompt, action schema, metric, smoke threshold, formal sample size, paired
analysis, outcome rule, replacement rule, or stopping rule. It introduces no
task selection based on P3b results. A P3 formal matrix remains unauthorized
unless the complete P3c smoke matrix passes all frozen checks.
