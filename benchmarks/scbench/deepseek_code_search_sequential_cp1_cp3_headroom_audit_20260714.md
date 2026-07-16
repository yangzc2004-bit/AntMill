# DeepSeek code_search CP1-CP3 Headroom Audit

Date: 2026-07-14

## Run

- Config: `benchmarks/scbench/deepseek_code_search_sequential_cp1_cp3_headroom_config.json`
- Run root: `runs_scbench_moa_deepseek_code_search_sequential_cp1_cp3_headroom_r1_20260714`
- Arm: `no_transfer-a54674a7163a40c9ac88d8d68af96e8f`
- Model: `deepseek-v4-flash`
- Worker count: 3
- Per-checkpoint step limit: 20

## Observed Scores

All three workers passed checkpoint 1 (`7/7 Core`, `13/13 all`) and
checkpoint 2 (`5/5 Core`, `25/25 all`).

At checkpoint 3:

| Worker | Core | All | Steps |
| --- | ---: | ---: | ---: |
| 1 | 0/8 | 25/47 | 20 |
| 2 | 0/8 | 0/47 | 20 |
| 3 | 0/8 | 0/47 | 20 |

The target collection was valid for every checkpoint-3 evaluation:
`47` tests with collection hash
`39d11b6b8327d3049a7b4e00da441d91640b57e6fe866789c506e43a10634395`.

## Budget-Censoring Evidence

Every checkpoint-3 trajectory ended exactly at the imposed 20-step limit.
None of the three workers issued the MiniSWE completion command before the
limit:

- Worker 1 was still developing and testing a structure-matching prototype
  in temporary files at its final action; the prototype had not been merged
  into the submitted `code_search.py`.
- Worker 2's final action was a local invocation of its newly written
  implementation, with no subsequent repair or completion action.
- Worker 3's final action was a compile check that failed because
  `code_search.py` was absent.

The pinned upstream MiniSWE configuration allows `300` steps by default.
Therefore the experimental limit of `20` was a substantial engineering
reduction, not the benchmark's native budget.

The outer orchestration process later exited on its 1,200-second Docker
timeout and did not write a completed arm report. All native checkpoint
evaluations cited above were already present and internally complete, but
the timeout is a separate orchestration failure.

## Decision

The `0/8` checkpoint-3 outcomes are **budget-censored** and do not activate
the preregistered `abandon code_search` rule. They cannot distinguish model
incapability from insufficient action budget.

A prospective one-worker no-transfer calibration was frozen before its
outcome:

`benchmarks/scbench/deepseek_code_search_sequential_cp1_cp3_budget60_probe_config.json`

Its decision rule is:

- `>=2/8 Core`: checkpoint-3 headroom confirmed.
- `1/8 Core`: run one additional 60-step no-transfer worker.
- `0/8 Core`: headroom not confirmed; abandon `code_search` for the main
  transfer contrast.

