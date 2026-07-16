# Depth-10 Cumulative Extension Audit

## Result

The exploratory depth extension did not reveal delayed degradation.

Core means over layers 1 through 10 were:

`0.933, 0.933, 0.900, 0.967, 0.967, 0.900, 0.900, 0.900, 0.900, 0.900`.

Layers 6 through 10 were identical at the aggregate Core level: every worker
scored `9/10`. The same number-parsing Core case failed for every worker in
every one of those layers.

## Complexity Check

The negative result is not explained by weak treatment:

- References grew from 3 to 9.
- Received experience grew from `22,113` to `70,585` characters (`3.19x`).
- Prompt size grew from `23,915` to `74,136` bytes (`3.10x`).
- Layer-10 worker input reached `819,562` tokens, `3.96x` the matching
  no-transfer layer-5 input.

## Why More Identical Layers Will Not Help

The strict source gate admits only `10/10 Core` outputs. Once all layer-6
workers fell to `9/10`, no new output could enter the shared bundle. Prompt
size and reference count therefore remained fixed through layer 10.

This mechanism can lock in a shared failure, but it cannot form a continuing
death spiral after the external verifier closes the feedback loop.

The next experiment should blind source admission to external Core and use the
kind of local acceptance signal available to a real MAS: successful agent
completion plus local smoke checks. External Core remains the outcome measure.
