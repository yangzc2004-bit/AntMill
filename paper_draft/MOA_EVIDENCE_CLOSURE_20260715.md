# MoA Evidence Closure

Date: 2026-07-15

## Supported conclusion

In the audited `cfgpipe` setting, blinded experience transfer can create a
multi-layer implementation attractor without sustained score collapse.
Two cumulative self-report trajectories beyond the frozen main run reproduce
consecutive byte-identical worker snapshots, and a prospective fixed-reference
control reaches the same criterion while every worker receives only three
recent summaries. Cumulative history growth is therefore not necessary for
exact implementation lock-in in this setting, although transferred context
itself remains a plausible contributor.

The evidence does not support a universal death spiral, permanent
irreversibility, or a generally harmful effect of experience transfer.

## Evidence table

| Run | Role | First consecutive exact-lock-in layer | Boundary |
|---|---|---:|---|
| Kimi Coding cumulative r2 | independent retrospective audit | 3 | 10 layers, terminal 34/37 |
| Kimi MaaS cumulative r1 | independent retrospective audit | 4 | intermittent 0/37 tails |
| Kimi MaaS cumulative r2 | frozen main run | 5 | stable 33/37 plateau |
| Kimi MaaS bounded recent transfer | prospective context-growth control | 2 | exactly three references per worker and layer |
| Kimi Coding no transfer | control | none | three distinct terminal snapshots |
| Kimi MaaS no transfer | control | none | three distinct terminal snapshots |
| `log_query` verified cumulative transfer | second-task boundary | none | three distinct terminal snapshots and higher score than control |

The earliest Kimi Coding r1 trajectory exposed bootstrap Core scores and is
retained only as a protocol-drift observation. It is not counted as one of the
two independent replications.

## Admission interpretation

The three-command local gate was frozen before the 36-output local-admission
arm ran. It prospectively rejected both observed zero-command 0/37 false
completions and prevented their direct downstream appearance.

The threshold sweep from zero to six commands is retrospective. It estimates
the sample-specific retention/rejection trade-off and does not identify a
universal optimal threshold.

## Claim firewall

Allowed:

- shared experience can create a multi-layer implementation attractor;
- exact lock-in recurs across three audited cumulative trajectories;
- cumulative reference-count growth is not necessary in the tested setting;
- bounded transfer can briefly re-diversify and later reconverge;
- strict verified transfer on `log_query` preserves terminal implementation
  diversity, so direction is task- and admission-dependent;
- the frozen local gate prospectively blocks direct propagation of the
  observed false completions, with measurable false-rejection cost.

Forbidden:

- context length is irrelevant;
- lock-in is permanent or irreversible;
- shared experience generally harms multi-agent systems;
- exact snapshot identity proves semantic identity outside the test suite;
- the command threshold is universally optimal;
- historical layers are independent statistical replicates.

## Reproducibility artifacts

- Frozen bounded-control configuration and SHA-256 sidecar:
  `benchmarks/scbench/kimi_maas_cfgpipe_cp1_bounded_context_depth6_config.*`
- Raw bounded-control run:
  `runs_scbench_moa_kimi_maas_cfgpipe_cp1_bounded_context_depth6_r1_20260715`
- Deterministic replication audit:
  `scripts/audit_scbench_lockin_replications.py`
- Audit report:
  `benchmarks/scbench/kimi_cfgpipe_lockin_replication_audit_20260715.json`
- Figure source data:
  `paper_draft/generated/moa_paper/lockin_replication_layers.csv`
