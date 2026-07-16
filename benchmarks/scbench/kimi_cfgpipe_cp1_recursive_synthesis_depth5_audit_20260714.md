# Kimi cfgpipe Recursive-Synthesis Depth-5 Audit

Date: 2026-07-14

## Verdict

The pre-registered degradation curve did not appear. Recursive synthesis and
no transfer both reached a layer-5 mean Core score of 1.0, so the primary
terminal Core effect was 0.0 rather than the required -0.20. Recursive Core
also remained flat at 1.0 from layer 2 through layer 5.

The exact mechanism-task pair should therefore be stopped rather than extended
to more layers.

## Curves

| Mode | L1 Core | L2 Core | L3 Core | L4 Core | L5 Core |
|---|---:|---:|---:|---:|---:|
| Recursive synthesis | 0.833 | 1.000 | 1.000 | 1.000 | 1.000 |
| No transfer | 0.500 | 0.667 | 0.500 | 1.000 | 1.000 |

| Mode | L1 all tests | L2 all tests | L3 all tests | L4 all tests | L5 all tests |
|---|---:|---:|---:|---:|---:|
| Recursive synthesis | 0.874 | 0.874 | 0.865 | 0.865 | 0.865 |
| No transfer | 0.649 | 0.865 | 0.622 | 0.910 | 0.919 |

At layer 5, every recursive worker passed 32/37 tests, while every no-transfer
worker passed 34/37. This is a secondary terminal gap of -5.4 percentage
points, not a progressive within-arm decline.

## Why More Iterations Are Not The Fix

The layer-3 and layer-4 manager playbooks are byte-identical, with SHA-256
prefix `37820be0253d`. Their text similarity is 1.0. All three layer-5 recursive
worker snapshots are also identical, with hash prefix `d390d0571ce0`.

The system had therefore reached a fixed point before layer 5. Extra layers
would most likely reproduce the same playbook and implementation, not reveal a
delayed threshold.

## Lock-In Evidence

The no-transfer layer-5 workers retained three distinct snapshot hashes:
`b8e23628431a`, `bd03497f012c`, and `a14a73fa8388`. Recursive broadcast
eliminated this diversity and made all three workers share the same five
failures.

Three failures occurred in both arms:

- `test_env_parse_error_priority`
- `test_default_parse_error_stops`
- `test_file_parse_error_stops`

Two failures were present in all recursive layer-5 workers but absent from all
no-transfer layer-5 workers:

- `test_invalid_schema_json`
- `test_file_value_is_trimmed`

The manager repeatedly encoded an `arg > file > env > default` rule and
retained code that returned the original integer string, so `0042` remained
`0042` rather than becoming `42`. From layer 2 onward it also recommended a
unified schema-loading error path whose emitted message did not reliably
contain `JSON`. These choices were not caught by the four Core tests, were
re-imported as verified experience, and became universal by layer 5.

## Scientific Interpretation

This run supports a narrower result: Core-only local verification plus
centralized recursive synthesis can homogenize independent agents around a
stable, locally verified but globally inferior implementation.

It does not support the target claim that globally correct but increasingly
complex experience creates a progressively worsening curve. Here the manager
introduced or retained semantic mistakes and then converged. The next
benchmark must expose a continuous cost or robustness metric on strategies
that remain functionally correct, so complexity can accumulate without relying
on verifier blind spots or ambiguous specification semantics.
