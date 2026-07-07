# E2 5-Seed Verdict

## Frozen Claim

E2 5-seed data support the preregistered degradation claim for `shared_consolidated` relative to `frozen` write-only memory.

| metric | mean diff vs frozen | 95% CI | significant |
|---|---:|---:|---|
| success_excess_steps | 11.843 | [7.661, 16.018] | True |
| looped | 0.138 | [0.092, 0.188] | True |
| stagnation_rate | 0.093 | [0.076, 0.110] | True |
| revisit_max | 1.675 | [1.233, 2.125] | True |

Per-seed `success_excess_steps` direction (paired, prereg method): `5/5` seeds are worse than frozen: seed0 +7.71, seed1 +7.83, seed2 +9.58, seed3 +17.75, seed4 +18.47.

## Private Boundary

`private` memory is also worse than frozen on the main endpoint (sxs 7.325, CI [2.833, 11.895]; looped 0.079, CI [0.037, 0.125]). Thus the broad risk is active memory injection, while the shared-consolidated-specific evidence is narrower.

The same data do not establish that `shared_consolidated` is broadly worse than `private` on the main efficiency endpoint.

| metric | mean diff vs private | 95% CI | significant |
|---|---:|---:|---|
| success_excess_steps | 0.868 | [-4.286, 6.154] | False |
| looped | 0.058 | [0.008, 0.113] | True |

## Mechanism Readout

`shared_consolidated` compresses active strategy supply: mean distinct injected memories are `11.0` vs `25.4` for `shared_append` (`2.31x` append/consolidated ratio).
This supports a write-side consolidation account, not the E3 append-side lambda dose-response account.

## Recommended Manuscript Wording

> Active consolidated memory, compared with a write-only frozen control, significantly increases successful-route excess steps and loop signatures. The current E2 evidence does not show a broad shared-vs-private efficiency separation; shared-specific risk should be framed through loop amplification and write-side strategy-supply compression.
