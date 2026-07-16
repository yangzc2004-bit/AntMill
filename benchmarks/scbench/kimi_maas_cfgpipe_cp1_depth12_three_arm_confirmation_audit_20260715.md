# Kimi MaaS cfgpipe depth-12 three-arm confirmation audit

## Frozen decision

The fresh self-report replication is **falsified under the frozen criterion**: it produced 0 post-layer-6 `0/37` events, versus the required minimum of 2.

The local completion-and-smoke mechanism is **supported**: both local-arm `0/37` false-completion outputs had fewer than three successful commands, were rejected, and never appeared in later recipient prompts.

## Curves

- Self report: `0.919, 0.901, 0.892, 0.892, 0.892, 0.892, 0.892, 0.892, 0.892, 0.892, 0.892, 0.892`
- No transfer: `0.910, 0.874, 0.856, 0.910, 0.703, 0.613, 0.883, 0.901, 0.883, 0.910, 0.901, 0.874`
- Local acceptance: `0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.919, 0.613, 0.613, 0.919`

## Trajectory findings

- Self report locks to `33/37` for all 30 worker-layer outcomes from layers 3-12.
- From layer 5 onward, all self-report workers produce the exact same snapshot hash at every layer.
- Shared self-report failures: `test_default_parse_error_stops`, `test_env_parse_error_priority`, `test_file_parse_error_stops`, `test_unrecognized_type`.
- Local layer 10 worker_3: `0/37`, 1 model step, 0 successful commands; rejected and absent downstream.
- Local layer 11 worker_2: `0/37`, 1 model step, 0 successful commands; rejected and absent downstream.
- No-transfer layer 5 worker_2: `12/37`, Core `0/4`, 12 model steps; action budget exhausted without submission, with a valid model query and non-infrastructure evaluation.
- No-transfer layer 6 worker_2: `1/37`, Core `0/4`, 12 model steps; action budget exhausted without submission, with a valid model query and non-infrastructure evaluation.
- Gate tradeoff: 7 local outputs were rejected in total. Besides the two `0/37` collapses, five `34/37` outputs were also rejected because they used only two successful commands.


## Validity

All 108 evaluations use the frozen 4-Core/37-test target and test hash. Every interpreted model call has `had_error=false` and at least one completed step.

Transient provider RPM warnings occurred during the nine-way parallel launch, but retries completed. No rate-limit or gateway failure was scored as a benchmark failure.

Recipient blinding and prohibited-access scans passed across 888 assistant messages.

## Claim boundary

The prior recurrent catastrophic depth-12 curve should remain exploratory because its exact `0/37` pattern did not replicate. The confirmatory result supports the rejection mechanism, a stable self-report-arm `33/37` lock-in, and substantial stochastic tail risk, while also revealing a nontrivial false-rejection cost. It does not establish a monotonic death spiral or a unique catastrophic effect of self-report transfer.
