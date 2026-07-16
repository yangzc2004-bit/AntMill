# Kimi TextDrop Checkpoint-1 Cumulative Pilot

Date: 2026-07-13

## Decision

This pilot does **not** establish the target degradation curve. All validity
gates passed, but cumulative verified-experience transfer improved and then
preserved performance instead of degrading it. Under the frozen decision rule,
`textdrop` checkpoint 1 is stopped here and the next screened candidate is
`cfgpipe` checkpoint 1.

## Core Results

| Arm | Layer 1 | Layer 2 | Layer 3 |
|---|---:|---:|---:|
| cumulative_success workers | 4/4, 0/4, 0/4 | 4/4, 4/4, 4/4 | 4/4, 4/4, 4/4 |
| cumulative_success mean | 0.333 | 1.000 | 1.000 |
| no_transfer workers | 4/4, 0/4, 0/4 | 4/4, 4/4, 4/4 | 4/4, 0/4, 4/4 |
| no_transfer mean | 0.333 | 1.000 | 0.667 |
| treatment minus control | 0.000 | 0.000 | +0.333 |

The arms began with exactly the same worker-level results. Every cumulative
layer-2 worker received one strict 4/4 source, and every layer-3 worker received
four historical strict sources. Cumulative performance reached 1.0 and did not
fall.

## Complexity

| Arm | Layer 1 input tokens | Layer 2 input tokens | Layer 3 input tokens |
|---|---:|---:|---:|
| cumulative_success | 140,260 | 182,244 | 417,625 |
| no_transfer | 162,521 | 159,809 | 190,961 |

Layer-3 cumulative input was 2.187 times the no-transfer input. Mean received
experience grew from 12,000 characters at layer 2 to 44,262 at layer 3, so the
stress policy clearly amplified coordination context without reducing Core
correctness.

## Gate Audit

| Frozen gate | Result | Evidence |
|---|---|---|
| Source activation | Pass | Every cumulative layer-2 worker received one strict 4/4 source |
| Control headroom | Pass | No-transfer layer-3 mean was 0.667 |
| Target consistency | Pass | All 18 evaluations used checkpoint-1 Core total 4 and collected 28 tests |
| Integrity | Pass | One test hash, zero infrastructure failures, empty runner stderr, no benchmark-path action |
| Primary terminal effect | Fail | Layer-3 treatment difference was +0.333, not <= -0.20 |
| Within-arm terminal decline | Fail | Cumulative layer 3 remained at its 1.0 peak |
| Post-transfer decrease | Fail | Neither cumulative transition decreased |
| Complexity support | Pass | Non-zero transfer and 2.187x layer-3 input tokens |

Two cumulative-agent actions inspected `/proc` only to stop their own local
TextDrop server processes. They did not access benchmark catalogs, tests,
outputs, or reference solutions.

## Excluded Run

The earlier run at
`runs_scbench_moa_kimi_textdrop_cp1_cumulative_pilot_20260713` is invalid and
excluded. Lingering agent-started HTTP servers interfered with marker
collection, incorrectly changing the target from 4 Core tests to 8. Clean
zero-model re-evaluation restored the canonical 4-test target, and the process
isolation fix was validated before this replacement contrast was run.

## Interpretation

The defensible result is coordination-cost amplification without an accuracy
penalty. This candidate provides no transient or terminal degradation signal,
so adding replications or another transfer arm would violate the frozen
falsification rule.
