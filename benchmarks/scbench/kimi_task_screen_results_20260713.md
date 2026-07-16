# Kimi SCBench Task Screen

Protocol: two isolated workers, one layer, checkpoint 2, 12 actions per
checkpoint.

| Candidate | Worker scores | Full-Core rate | Decision |
|---|---|---:|---|
| code_search | 5/5, 5/5 | 100% | Too easy |
| circuit_eval | 0/5, 7/9 at checkpoint 1 | 0% | Too hard |
| database_migration | 3/3, 0/3 | 50% | Selected |

`database_migration` is the best candidate because it produces one strictly
verified success and one complete failure under identical conditions. Both
workers used the same checkpoint-2 test collection hash. No infrastructure,
gateway, dependency, or benchmark-access violations were found.

The next run should use two layers first. Layer 1 creates candidate source
experience, and layer 2 is the first recipient layer. A third layer and
replicates should be added only after treatment activation and a directional
effect are observed.
