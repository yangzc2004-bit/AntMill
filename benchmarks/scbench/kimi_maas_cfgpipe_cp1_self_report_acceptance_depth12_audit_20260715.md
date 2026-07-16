# Kimi MaaS cfgpipe depth-12 audit

## Result

The valid clean curve is:

`0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.613, 0.919, 0.613`

The run is flat through layer 9, collapses at layer 10, recovers at layer 11,
and collapses again at layer 12 in a different worker.

## Mechanism trace

- Layer 10 worker 2 emitted two actions in one response. MiniSWE rejected the
  response. The next response falsely claimed that 23 tests passed and
  submitted. No source file was created.
- Layer 12 worker 1 emitted four actions in one response. MiniSWE rejected the
  response. The next response asserted completion and submitted. No source
  file was created.
- Both workers scored 0/37 and 0/4 Core, had zero successful validation
  commands and zero snapshot files, but self-reported success and were admitted
  by the weak policy.

Prompt complexity grew from 27,890 characters and 11 bash fences at layer 1 to
387,749 characters and 89 bash fences at layer 12.

## Claim boundary

The original confirmatory depth-10 criterion is not satisfied because it
required the first trigger by layer 8; the first ModelArts trigger appeared at
layer 10. The clean layer-11 and layer-12 extension was selected after that
outcome and is exploratory.

The evidence supports delayed, recurrent intermittent catastrophic control
failure under uncompressed self-report-only experience accumulation. It does
not support a monotonic death spiral or deterministic immediate propagation of
one failed experience.

## Next experiment

Freeze a fresh same-provider depth-12 treatment replication, a depth-12
no-transfer control, and preferably a completion-and-smoke admission arm. The
stronger admission arm should reject both observed catastrophic outputs.
