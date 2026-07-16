# Prospective log_query Boundary Audit

- Freeze passed: **True**
- All validity gates passed: **True**
- Cross-task lock-in support: **False**
- Cross-task boundary observed: **True**
- Mitigation effect identifiable: **False**
- Diversity-routing support: **False**
- Raw strong-mitigation criterion met: **True**
- Strong mitigation support: **False**

## Three-arm summary

| Arm | Diversity AUC L2-L3 | L2 unique | L3 unique | Mean Core | Mean all tests | Minimum Core | Input tokens | Mean duration |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| no_transfer | 6 | 3 | 3 | 7.89/10 | 108.44/134 | 0/10 | 544,396 | 197.1s |
| bounded_recent | 6 | 3 | 3 | 9.67/10 | 127.22/134 | 9/10 | 1,279,735 | 217.9s |
| bounded_diverse | 6 | 3 | 3 | 9.67/10 | 130.11/134 | 9/10 | 1,250,575 | 207.3s |

## Interpretation

The result is interpreted strictly under the frozen three-layer rules. A boundary result means that the exact cfgpipe lock-in pattern did not reproduce on log_query within the observed horizon; it does not prove absence at greater depth.

Because bounded-recent already retained the maximum three implementations at both measured post-transfer layers, the mitigation contrast is ceiling-limited. The diverse arm met the raw layer-3 diversity-and-Core criterion, but no incremental mitigation effect is identifiable.

## Outputs

- JSON: `benchmarks\scbench\kimi_maas_log_query_cp1_three_arm_boundary_depth3_audit_20260716.json`
- Layer CSV: `paper_draft\generated\moa_paper\log_query_boundary_layers.csv`
- Summary CSV: `paper_draft\generated\moa_paper\log_query_boundary_summary.csv`
