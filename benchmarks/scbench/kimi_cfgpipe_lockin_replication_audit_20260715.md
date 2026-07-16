# Kimi cfgpipe lock-in replication and context-control audit

## Decision

Two independent cumulative self-report trajectories beyond the frozen main run retrospectively reproduce multi-layer exact snapshot lock-in, while both no-transfer controls retain implementation diversity. The prospective bounded-transfer arm also reaches exact implementation lock-in while reference count remains fixed at three; cumulative history growth is therefore not necessary in this tested setting.

## Run summary

| Run | Role | Depth | First two-layer exact lock-in | Terminal snapshots | Terminal score |
|---|---|---:|---:|---:|---:|
| kimi-coding-no-transfer | no_transfer_control | 5 | -- | 3 | 0.919 |
| kimi-coding-self-report-r1 | legacy_bootstrap_score_exposure | 8 | 3 | 1 | 0.613 |
| kimi-coding-self-report-r2 | independent_self_report_replication | 10 | 3 | 1 | 0.919 |
| kimi-maas-self-report-r1 | independent_self_report_replication | 12 | 4 | 1 | 0.613 |
| kimi-maas-no-transfer | no_transfer_control | 12 | -- | 3 | 0.874 |
| kimi-maas-self-report-r2 | frozen_main_self_report | 12 | 5 | 1 | 0.892 |
| kimi-maas-bounded-context-r1 | prospective_context_growth_control | 6 | 2 | 2 | 0.919 |
| log-query-no-transfer | second_task_no_transfer | 5 | -- | 3 | 0.938 |
| log-query-cumulative-verified | second_task_transfer_boundary | 5 | -- | 3 | 0.963 |

## Claim boundary

- The two additional lock-in replications are independent trajectories, but the lock-in metric was audited retrospectively.
- The earliest Kimi Coding r1 trajectory exposed bootstrap Core scores and is retained only as a protocol-drift observation.
- The bounded-context arm prospectively fixes reference count at three; it does not equalize total tokens with no transfer.
- The log-query comparison is a second-task boundary with strict Core-gated transfer, not an exchangeable replication of self-report transfer.
- No layer is treated as an independent statistical sample.

## Key source paths

- JSON audit: `benchmarks\scbench\kimi_cfgpipe_lockin_replication_audit_20260715.json`
- Layer source data: `paper_draft\generated\moa_paper\lockin_replication_layers.csv`
- Bounded run: `runs_scbench_moa_kimi_maas_cfgpipe_cp1_bounded_context_depth6_r1_20260715`
