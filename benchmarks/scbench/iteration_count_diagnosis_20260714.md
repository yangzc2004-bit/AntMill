# Iteration-count diagnosis

## Two different budgets

The experiments expose two distinct meanings of "too few iterations":

1. **Agent action budget**: the number of MiniSWE actions available to one
   worker while solving one checkpoint.
2. **MAS feedback depth**: the number of worker generations and experience
   assimilation rounds.

They must not be interpreted as the same variable.

## Agent action budget

The original `code_search` screen used 20 actions. That budget was too small:
a valid DeepSeek CP1 trajectory required 21 actions and passed all tests.
Increasing the CP3 budget to 60 still ended at the action boundary without
submission. Increasing it to 120 removed that censoring: the model explicitly
submitted at action 118, but clean evaluation was 0/47 because the solution
depended on undeclared `tree_sitter`. Therefore:

- 20 and 60 actions can create false benchmark failures;
- after censoring was removed, the remaining CP3 failure was an actual
  solution/environment-contract error;
- further action-budget increases are not justified for
  `code_search + deepseek-v4-flash`.

The xjq calibration gives a cleaner matched confirmation. At 12 actions, all
12 control trajectories hit the exact boundary, none emitted an explicit
completion marker, and all three `0/13` outcomes occurred at that boundary.
At 20 and 28 actions, all six calibration workers reached `12/13`; the
28-action calibration also produced one natural checkpoint-2 completion at
action 18. Therefore, the original 12-action xjq control was invalid because
of action-budget censoring, and the formal contrast correctly used 28 actions.

## MAS feedback depth

Feedback depth does affect the chance of observing rare failures. The first
Kimi self-report-only cumulative arm was flat through layer 7 and produced its
first valid catastrophic `0/37` output only at layer 8, after 24 references and
about 245k received experience characters.

However, a fresh outcome-independent Kimi depth-10 replication was completely
flat:

| Layer | Mean Core | Mean all tests | References | Received chars |
|---:|---:|---:|---:|---:|
| 1 | 1.000 | 0.919 | 3 | 25,934 |
| 5 | 1.000 | 0.919 | 15 | 152,110 |
| 8 | 1.000 | 0.919 | 24 | 246,074 |
| 10 | 1.000 | 0.919 | 30 | 309,998 |

All 30 outputs made real model calls, self-reported success, used the expected
test hash, and had no infrastructure, quota, or rate-limit failure. Layer-10
input was 11.54 times the matching no-transfer control.

DeepSeek showed two isolated catastrophic outputs across ten layers but
recovered immediately after both. GLM-5 was flat through ten layers.

## Decision

The defensible conclusion is:

> Too few feedback rounds can hide late, model-dependent false-success tail
> events, but more rounds alone do not reproducibly cause sustained
> degradation in append-all experience assimilation.

The next positive path is not another deeper raw-append run. It is a benchmark
with stable nonzero headroom combined with the MOA-style recursive self-report
manager, so an accepted bad lesson remains privileged and can plausibly
amplify instead of being diluted among a growing mass of correct artifacts.

## Formal xjq recursive-manager result

The calibrated 28-action xjq contrast tested that positive path. Its mean Core
curves were:

| Layer | No transfer | Recursive self-report manager |
|---:|---:|---:|
| 1 | 0.897 | 0.897 |
| 2 | 0.795 | 0.744 |
| 3 | 0.923 | 0.615 |
| 4 | 0.923 | 0.923 |
| 5 | 0.744 | 0.923 |

The treatment showed a real transient collapse at layer 3 but recovered fully
at layers 4 and 5. Its terminal score exceeded control by 0.179, despite a
1.209x layer-5 input-token load and a 1.479x increase in manager prompt tokens
from the first to final synthesis. All validity, target-consistency,
score-blinding, and model-query gates passed.

This separates the two hypotheses:

- **Yes**: too few per-agent actions can manufacture false failures.
- **No**: too few MAS feedback layers do not explain the missing sustained
  degradation here; five recursive layers were enough to show recovery, and
  the preregistered mechanism-task pair is a valid negative result.
