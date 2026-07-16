# DeepSeek cfgpipe Recursive Self-Report Stress-Probe Audit

Date: 2026-07-14

## Verdict

The probe is valid and shows **behavioral lock-in at a degraded plateau**, but
it does not meet the preregistered threshold for the target death-spiral
curve.

The five-layer all-test means were:

`0.856 -> 0.883 -> 0.883 -> 0.874 -> 0.865`

Layers 3 to 4 and 4 to 5 were both strictly decreasing, and every terminal
worker scored 32/37. However, the terminal mean remained above 0.75 and was
only 0.018 below the best earlier layer, far short of the required 0.15.

## Why The Mechanism Is Real

The initial manager consumed the complete DeepSeek layer-2 cohort with
external outcomes 0/37, 33/37, and 34/37. All three had self-reported success,
so all three were included. The manager did not receive their external scores.

The externally failed source contained the rule
`arg > file > env > default`. The manager retained this rule in every shared
playbook. It also retained the claim that an empty environment variable should
be treated as absent.

All 15 downstream workers self-reported success and passed all four Core
tests, yet the terminal workers universally failed:

- `test_env_parse_error_priority`
- `test_invalid_boolean[whitespace]`
- `test_default_parse_error_stops`
- `test_file_parse_error_stops`
- `test_empty_env_string_is_present`

Their terminal source snapshots had three distinct hashes, so the shared
failure set reflects behavioral homogenization rather than copying one file.

## Manager Fixed Point

| Manager Layer | Playbook Chars | Hash Prefix | Similarity To Previous |
|---:|---:|---|---:|
| Bootstrap | 6,709 | `2f835a1fa11a` | - |
| 1 | 7,233 | `8911dc921b57` | .958 |
| 2 | 7,677 | `ba7daf8ac566` | .956 |
| 3 | 7,677 | `ba7daf8ac566` | 1.000 |
| 4 | 7,677 | `66139072293a` | .99987 |

The manager reached an exact textual fixed point before worker layer 4.
Additional cfgpipe layers are therefore unlikely to create a stronger curve.

## Validity

All manager requests and downstream prompts preserved external-score
blinding. All 15 outputs self-reported success. There were no model-query
failures, nonempty runner stderr logs, or prohibited benchmark-path actions.
One native evaluation infrastructure failure was cleanly re-evaluated on the
same snapshot; the final manifest contains no infrastructure failure.

## Interpretation

This supports a narrower but useful mechanism:

> Self-report acceptance followed by recursive MOA synthesis can turn a mixed
> success cohort into a privileged shared playbook and make independent agents
> converge on the same globally inferior behavior.

It does not yet support the stronger sustained-degradation claim, and it does
not test amplification of experience that is globally correct because the
stress-probe bootstrap included an externally failed source.

The next experiment should use the same blinded manager on a sequential
benchmark whose requirements evolve across checkpoints. That design gives old
locally accepted rules a natural opportunity to conflict with later contexts
and provides normalized-score headroom for a genuine downward curve.
