# SCBench integration

This directory pins and validates the upstream SlopCodeBench runner used by the
cooperative Mixture-of-Agents experiments.

The upstream runner assumes a POSIX host shell and POSIX workspace paths. On
Windows, run it inside the pinned Linux image built by `scripts/setup_scbench.ps1`.
The Windows Docker client only launches the outer runner container; agent
workspaces and checkpoint evaluation execute inside Linux.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_scbench.ps1
```

## Verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_scbench.ps1
```

Verification checks the pinned source revisions, lists the local problem
catalog, and evaluates the upstream `word_stats` known-good fixture at
checkpoint 1. The public problem repository contains some intentionally
unfinished reference solutions, so those are not used as infrastructure health
checks.

The MoA layer must preserve this execution boundary:

1. workers run independently in private workspaces;
2. a barrier closes each checkpoint round;
3. the verifier evaluates each worker snapshot;
4. the orchestrator synthesizes the prior layer outputs;
5. only the synthesized context is delivered to the next worker layer.

## MoA protocol

`sec/scbench_moa.py` uses AutoGen Core's routed-agent runtime and follows the
standard layered Mixture-of-Agents protocol:

1. every worker receives the same task and runs in a private workspace;
2. all workers in a layer execute concurrently;
3. the next layer starts only after the current layer reaches a barrier;
4. every worker in the next layer receives the same selected prior-layer
   context;
5. the final aggregator sees only the last layer's outputs.

The topology is fixed. Experiments vary only the assimilation policy:

- `no_transfer`: suppress prior-layer results;
- `source_success`: broadcast locally verified best results;
- `cumulative_success`: experimental fixed-topology stress policy that
  broadcasts every Core-verified result from all completed layers;
- `recipient_credit`: use paired per-worker layer improvement to decide whether
  the next prior-layer bundle may be broadcast. Credit remains layer-level
  because worker-specific routing would change the standard MoA topology.

Run the protocol test:

```powershell
python -m sec.selftest_scbench_moa
```

Run the end-to-end infrastructure smoke:

```powershell
python -m sec.run_scbench_moa_smoke --mode source_success
```

Run the native MiniSWE plus MaaS go/no-go:

```powershell
python -m sec.run_scbench_moa_miniswe `
  --model deepseek-v4-flash `
  --problem file_backup `
  --checkpoint-limit 1 `
  --workers 2 `
  --layers 2 `
  --mode source_success
```

This invokes SCBench's own MiniSWE implementation. The AntMill code controls
only the standard MoA layer barrier and the prior-output assimilation policy.
For reproducibility, the temporary problem subset materializes a
`requirements.txt` from the problem's public `test_dependencies` list. This
prevents transient packages installed during inference from disappearing
before isolated evaluation.
The pinned upstream revision has a Python module/package name collision that
prevents MiniSWE registration in the stock CLI. `scbench_miniswe_cli.py` loads
the unchanged upstream implementation before entering the stock CLI.

Run the frozen three-condition engineering pilot:

```powershell
python -m sec.run_scbench_moa_curve
```
