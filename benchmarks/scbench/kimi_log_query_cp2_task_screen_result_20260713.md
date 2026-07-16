# Kimi Log Query Checkpoint-2 Task Screen

## Evaluation Correction

The first run was invalid because a worker that stopped at checkpoint 1 was
reported with checkpoint-1 Core while another worker was reported with
checkpoint-2 Core. The worker backend was fixed so that an early-stop snapshot
is always evaluated against the configured target checkpoint.

The fix was validated on the original early-stop snapshot: its score changed
from checkpoint-1 `9/10` to checkpoint-2 `0/5`.

## Corrected Result

The unchanged screen was rerun under
`runs_scbench_moa_kimi_log_query_cp2_task_screen_20260713_targetfix`.

| Worker | Target evaluation | Core | Functionality | Regression | Error |
|---|---|---:|---:|---:|---:|
| worker 1 | external checkpoint-2 evaluation after early stop | 0/5 | 3/64 | 122/134 | 4/4 |
| worker 2 | native checkpoint-2 evaluation | 0/5 | 3/64 | 130/134 | 4/4 |

Both evaluations used test collection hash
`01baf5a5a1d7623915f69ca4d988db9f53ea14c177ef0875ae3aebcf766bc6aa`
without infrastructure failure.

Checkpoint 2 is rejected as too hard for strict verified-source feedback.
Checkpoint 1 remains a candidate because the same Kimi screen produced native
checkpoint-1 scores of 9/10 and 10/10.
