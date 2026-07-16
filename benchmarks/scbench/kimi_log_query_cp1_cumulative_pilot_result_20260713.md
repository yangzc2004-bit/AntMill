# Kimi Log Query Checkpoint-1 Cumulative Pilot

Date: 2026-07-13

## Decision

This pilot does **not** establish the target degradation curve. It shows a clean
one-layer degradation and tail-risk signal, followed by full recovery at the
terminal layer. Under the frozen decision rule, `log_query` checkpoint 1 is
stopped here.

## Frozen Setup

- Model: `kimi-k2.6`
- Agent: native SCBench MiniSWE
- Arms: `cumulative_success` and `no_transfer`
- Topology: 3 independent workers x 3 layers
- Budget: 12 MiniSWE steps per worker-layer
- Target: checkpoint-1 Core, 10 tests
- Transfer rule: broadcast every prior output that passed all 10 Core tests
- Experience cap: 12,000 characters per source

## Core Results

| Arm | Layer 1 | Layer 2 | Layer 3 |
|---|---:|---:|---:|
| cumulative_success workers | 8/10, 10/10, 10/10 | 9/10, 10/10, 0/10 | 10/10, 10/10, 9/10 |
| cumulative_success mean | 0.933 | 0.633 | 0.967 |
| no_transfer workers | 9/10, 10/10, 9/10 | 10/10, 9/10, 9/10 | 9/10, 10/10, 9/10 |
| no_transfer mean | 0.933 | 0.933 | 0.933 |
| treatment minus control | 0.000 | -0.300 | +0.033 |

The arms began at exactly the same mean. After two strict Core-verified layer-1
outputs were broadcast, the cumulative arm fell by 0.30 at layer 2 and one
worker scored 0/10. The cumulative arm then recovered to 0.967 at layer 3.

## Complexity

| Arm | Layer 1 input tokens | Layer 2 input tokens | Layer 3 input tokens |
|---|---:|---:|---:|
| cumulative_success | 202,806 | 331,811 | 397,871 |
| no_transfer | 205,611 | 189,996 | 194,945 |

Each cumulative worker received two sources at layer 2 and three historical
sources at layer 3. Layer-3 cumulative input was 2.041 times the no-transfer
input, so coordination-context complexity clearly accumulated even though the
terminal score recovered.

## Gate Audit

| Frozen gate | Result | Evidence |
|---|---|---|
| Source activation | Pass | Every layer-2 worker received two strict 10/10 sources |
| Control headroom | Pass | No-transfer layer-3 mean was 0.933 |
| Target consistency | Pass | All 18 evaluations used checkpoint-1 Core total 10 |
| Integrity | Pass | One test hash, zero infrastructure failures, all runner stderr files empty |
| Primary terminal effect | Fail | Layer-3 treatment difference was +0.033, not <= -0.20 |
| Within-arm terminal decline | Fail | The cumulative peak occurred at layer 3 |
| Post-transfer decrease | Pass | Cumulative layer 1 to layer 2 fell by 0.30 |
| Complexity support | Pass | Non-zero transfer and 2.041x layer-3 input tokens |

## Interpretation

The defensible claim is narrow: cumulative verified-experience transfer can
induce a substantial transient collapse and increase lower-tail risk even from
a matched baseline. This run does not support a persistent death-spiral or
terminal degradation claim because the treatment recovered at the next layer.

Per the pre-registered falsification rule, adding layers or replications to
rescue this candidate would be post-outcome tuning. The next candidate must be
screened and frozen independently.

