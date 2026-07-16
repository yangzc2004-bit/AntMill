# Kimi Checkpoint-1 Candidate Screen

Date: 2026-07-13

## Frozen Rule

Each candidate received two independent one-worker, one-layer, 12-step
no-transfer samples. A candidate required at least one strict full-Core result
and at least one non-full result. Passing candidates were ranked by strict-source
rate, then by smaller checkpoint-1 specification size.

## Results

| Problem | Samples | Source rate | Gate | Spec bytes |
|---|---:|---:|---|---:|
| textdrop | 4/4, 0/4 | 1/2 | Pass | 4,410 |
| cfgpipe | 0/4, 4/4 | 1/2 | Pass | 4,818 |
| file_merger | 14/18, 17/18 | 0/2 | Fail | 4,694 |
| layered_config_synthesizer | not run | n/a | Invalid | 8,280 |

`layered_config_synthesizer` never entered model inference because its deeply
nested fixture paths exceeded the Windows path-length limit during isolated
catalog materialization.

## Selection

`textdrop` and `cfgpipe` tied at a 0.5 strict-source rate. `textdrop` won the
pre-registered specification-size tie-break.

The `textdrop` 0/4 sample was audited. It completed model inference, wrote a
working Flask service, and manually exercised the endpoints, but omitted the
required extensionless entrypoint. This is a genuine task-completion failure,
not an API, container, or evaluator failure.

