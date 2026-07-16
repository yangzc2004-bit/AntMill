# Kimi Code Search Checkpoint-3 Task Screen

## Result

The 12-step checkpoint-3 screen was too hard:

| Worker | Core | Functionality | Regression | Error |
|---|---:|---:|---:|---:|
| worker 1 | 0/8 | 0/12 | 25/25 | 0/2 |
| worker 2 | 0/8 | 0/12 | 25/25 | 2/2 |

Both workers preserved all checkpoint-1 and checkpoint-2 regression behavior
but implemented none of the new structure-aware pattern functionality.

## Trajectory Diagnosis

Both workers exhausted all 12 MiniSWE actions while selecting and debugging a
parsing approach. Their final actions still inspected parser package APIs; no
checkpoint-3 matcher implementation was written. This is an action-budget
submission-boundary failure rather than a regression or infrastructure
failure.

Both evaluations used test collection hash
`39d11b6b8327d3049a7b4e00da441d91640b57e6fe866789c506e43a10634395`.
There were no infrastructure failures, non-empty runner stderr logs, or
prohibited benchmark-path actions.

## Decision

Do not use the 12-step setting for a layered contrast. Run one documented
minimum calibration at 16 actions while holding every other factor fixed.
