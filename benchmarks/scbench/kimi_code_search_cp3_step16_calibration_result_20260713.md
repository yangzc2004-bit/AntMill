# Kimi Code Search Checkpoint-3 Step-16 Calibration

## Result

Increasing the per-checkpoint action budget from 12 to 16 moved checkpoint 3
from uniformly zero performance into a below-ceiling partial-performance band:

| Worker | Core | Functionality | Regression | Error |
|---|---:|---:|---:|---:|
| worker 1 | 6/8 | 5/12 | 25/25 | 2/2 |
| worker 2 | 0/8 | 0/12 | 25/25 | 2/2 |

Mean normalized Core was 0.375. Both workers preserved all prior-checkpoint
regression tests, and the evaluations used the same test collection hash:
`39d11b6b8327d3049a7b4e00da441d91640b57e6fe866789c506e43a10634395`.

The task now has useful performance variance, but neither worker passed all
Core tests. Therefore the current oracle `source_success` policy would
broadcast no experience and cannot test feedback.

## Decision

Do not increase the action budget again. Add one pre-frozen independent
activation sample at the same 16-step setting, bringing the calibration sample
to three workers. If it also fails to produce an 8/8 Core source, abandon
strict Core-verified checkpoint-3 feedback rather than sampling until success.
