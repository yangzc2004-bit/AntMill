# Prospective cfgpipe Mitigation Audit

- Protocol freeze passed: **True**
- All validity gates passed: **True**
- Prospective outcome: **partial_support**

## Three-arm summary

| Arm | Diversity AUC L2-L6 | Diverse post-L1 layers | Two-layer lock-in | Mean all tests | Minimum worker | Input tokens | Mean duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| no_transfer | 15 | 5 | none | 30.00/37 | 1/37 | 994,496 | 214.5s |
| bounded_recent | 5 | 0 | L2 | 34.00/37 | 34/37 | 1,399,159 | 167.7s |
| bounded_diverse | 6 | 1 | L3 | 34.00/37 | 34/37 | 1,507,917 | 166.2s |

## Frozen endpoint

- Bounded-recent AUC: 5.
- Diversity-preserving AUC: 6.
- Gain: 1.
- Exact primary lock-in moved from L2 to L3.
- Mean all-test quality remained 34/37 in both transfer arms.

## Interpretation

The local-only router produced a real but transient delay. It preserved two implementations at L2, after which all workers converged to one implementation through L6. This is partial support for routing as a mechanism component and negative evidence against claiming that deduplication alone solves the attractor.

The no-transfer arm retained three implementations throughout L1-L6 but had substantially lower and less stable task quality. The result therefore exposes a quality-diversity trade-off rather than a free mitigation.

## Outputs

- JSON: `benchmarks\scbench\kimi_maas_cfgpipe_cp1_mitigation_three_arm_audit_20260716.json`
- Layer CSV: `paper_draft\generated\moa_paper\mitigation_three_arm_layers.csv`
- Summary CSV: `paper_draft\generated\moa_paper\mitigation_three_arm_summary.csv`
