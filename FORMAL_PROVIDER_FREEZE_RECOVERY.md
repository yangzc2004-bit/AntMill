# Formal Provider-Freeze Recovery

Status: prepared after the formal runners were paused on 2026-07-15 for HTTP
403 `ModelArts.81006` ("The resource is frozen").

Latest provider probe: `provider_probe_failed` with the same
`ModelArts.81006` code at `2026-07-16T01:35:32+08:00` after 0.703 seconds. No
recovery worker has been launched.

## Preserved State

- Epsilon controls: 9 completed `result.json` files.
- P3e MiniWoB: 17 completed `result.json` files.
- Interrupted Epsilon target:
  `n4_gt_false_seed1_epsilon_shared_consolidated_mmr`.
- Interrupted P3e target:
  `n4_gt_false_seed2_gamma_p3_choose_list_shared_consolidated_expel`.
- No completed result was deleted, moved, or rewritten.
- The interrupted directories were copied to
  `runs_provider_freeze_audit/20260715_81006`.

`formal_provider_freeze_checkpoint_20260715.json` binds every file in the
9+17 completed condition directories, both runtime-source freeze records and
their embedded files, and the recovery source files by SHA-256.

Checkpoint SHA-256:
`9f250ac1176ec4aafac8c0e5a141fa27ec2f7139a766ad3e85409492206b7991`.
The initial verification report has status `checkpoint_verified` with zero
failures.

## Recovery Invariants

1. The provider probe must return successfully before any formal condition.
2. Every condition is run individually from round zero.
3. A runner refuses to overwrite an existing P3 `result.json`.
4. Epsilon uses its frozen `--run-id-filter` path to select one arm and seed.
5. P3 uses `sec.resume_p3e_target` only to select one existing frozen config.
6. Each recovered condition must pass route-count, configuration, manifest,
   environment, LLM-path, parse/infrastructure, and reviewer-schema checks as
   applicable before the next condition starts.
7. Any provider failure stops the worker before the next condition.
8. The pre-outage completed-artifact hashes must still match after all
   recovered conditions.
9. Finalizers still require exactly 25 Epsilon and 54 P3e results.

## Commands

Probe without launching:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/resume_formal_after_provider_unfreeze.ps1 -ProbeOnly
```

Resume after the probe passes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/resume_formal_after_provider_unfreeze.ps1
```

The launcher starts hidden Epsilon and P3 workers, their existing finalizers,
the existing Epsilon sensitivity supervisor, and the existing Zeta supervisor.
Launch PIDs and logs are recorded under
`runs_provider_freeze_audit/20260715_81006` and `logs/`.

## Scope

The interruption and recovery change orchestration only. They do not change
the model, prompts, cache policy, browser runtime, maze generator, arm
definitions, task families, seeds, rounds, endpoints, statistical gates,
stopping rules, or outcome-to-claim map. Interrupted partial artifacts are
audit-only and are never analyzed as formal outcomes.
