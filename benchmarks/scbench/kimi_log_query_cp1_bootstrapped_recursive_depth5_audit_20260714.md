# Bootstrapped Recursive MoA Audit

## Decision

**Valid experiment; mechanism-task pair falsified.**

The five-layer treatment curve was `1.00, 1.00, 1.00, 1.00, 1.00` Core,
while the matched no-transfer curve was `0.90, 0.90, 0.90, 1.00, 0.90`.
At layer 5, treatment exceeded control by `+0.10` Core and `+4.73`
percentage points over all 134 tests.

## Why This Answers the Iteration Question

The treatment was active before worker layer 1. Its bootstrap playbook was
synthesized from three frozen `10/10 Core` sources. Every later manager update
used the immediately preceding playbook and all three new `10/10 Core`
sources.

Complexity grew materially:

- Manager output: `12,990 -> 18,578` characters (`1.43x`).
- Manager prompt: `7,231 -> 10,886` tokens (`1.51x`).
- Layer-5 worker input: `286,725` tokens versus `206,740` in control
  (`1.39x`).

Despite this growth, every worker from layers 3 through 5 scored `10/10 Core`
and `132/134` overall. Layer-5 implementations had three distinct source
hashes, so stability was behavioral rather than a byte-identical replay.

## Interpretation

For Kimi-K2.6 on `log_query` checkpoint 1, the missing degradation curve is
not plausibly explained only by too few iterations. The manager playbook
approached its size limit, input cost grew substantially, and performance
remained at the Core ceiling for three consecutive layers.

The next experiment should change the stressor rather than add more identical
layers. The best options are an unbounded or weakly compressed verified-output
accumulator, or a sequential task family whose locally valid rules conflict
across contexts.
