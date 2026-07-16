# Figure Contract: Experience-Mediated Lock-In

Backend: Python (matplotlib only).

## Figure 1

Core conclusion:
The testbed separates parallel task execution, blinded experience transfer,
local admission, and hidden external evaluation so that behavioral lock-in is
not conflated with benchmark scoring.

Figure archetype:
Schematic-led composite.

Target journal/output:
AAAI double-column figure; editable SVG primary, PDF vector secondary, TIFF
and PNG previews.

Final size:
178 mm x 82 mm.

Panel map:

- a: Three private MiniSWE workers execute the same task in parallel, meet at a
  barrier, and pass only blinded experience to the next layer.
- b: No transfer, cumulative self-report, bounded-recent transfer, local
  implementation-diversity routing, local admission, and recursive manager
  synthesis are distinguished by what is broadcast.
- c: External tests are hidden from workers and managers; performance collapse,
  implementation lock-in, and behavioral lock-in are separate outcomes.

Evidence hierarchy:

- hero evidence: experimental separation and topology;
- validation evidence: frozen policy definitions;
- controls/robustness: hidden evaluator and no-transfer baseline.

Statistics needed:
None; this is a protocol schematic.

Source data needed:
Frozen protocol and audited implementation semantics.

Image-integrity notes:
Vector-native schematic; no raster manipulation.

Reviewer risk:
Readers may mistake local admission for external-test access. The diagram must
show the evaluator behind a dashed isolation boundary.

## Figure 2

Core conclusion:
The frozen main run does not show sustained score collapse; exact implementation
lock-in recurs in two independent cumulative trajectories, a local diversity
router delays the cfgpipe attractor by only one layer, and a same-provider
log_query boundary retains maximal diversity while transfer improves quality.

Figure archetype:
Quantitative grid with a score-curve hero.

Target journal/output:
AAAI double-column figure; editable SVG primary, PDF vector secondary, TIFF
and PNG previews.

Final size:
178 mm x 130 mm.

Panel map:

- a: Mean external all-test score by layer, with worker minima and maxima.
- b: Unique full-workspace snapshot count in two retrospective cumulative
  replications and the frozen main trajectory.
- c: Prospective cfgpipe primary-implementation trajectories under no transfer,
  bounded-recent routing, and bounded-diverse routing.
- d: Mean normalized score versus normalized post-layer-1 primary diversity for
  cfgpipe and the prospectively frozen same-provider log_query boundary.

Evidence hierarchy:

- hero evidence: score trajectories and non-replication of sustained collapse;
- validation evidence: two additional cumulative trajectories;
- controls/robustness: no-transfer, fixed-reference, a local-only diversity
  router, and a same-provider second-task boundary;
- mechanism support: exact lock-in at a fixed reference count of three and only
  transient benefit from local identity deduplication.

Statistics needed:
Three workers per arm and layer; descriptive mean and range only. No
inferential test is claimed because this is one frozen 12-layer run.

Source data needed:
`main_depth12_curves.csv`, `lockin_replication_layers.csv`,
`mitigation_three_arm_layers.csv`, `mitigation_three_arm_summary.csv`, and
`log_query_boundary_summary.csv`.

Image-integrity notes:
Vector plots only.

Reviewer risk:
Retrospective replications could be mistaken for preregistered confirmatory
runs; full-workspace hashes could be confused with primary implementation
hashes; and a one-layer delay could be overstated as successful mitigation.
Label all three boundaries directly.

## Figure 3

Core conclusion:
Observed admission quality is threshold-dependent, while catastrophic tails
and recursive-manager effects vary across model runs and tasks.

Figure archetype:
Asymmetric mixed-modality quantitative figure.

Target journal/output:
AAAI double-column figure; editable SVG primary, PDF vector secondary, TIFF
and PNG previews.

Final size:
178 mm x 102 mm.

Panel map:

- a: Retrospective command-threshold replay showing catastrophic rejection and
  high-quality retention, with the prospectively frozen three-command arm
  marked separately.
- b: Raw-append 0-score event rate across audited model runs.
- c: Terminal treatment-minus-control direction for recursive-manager settings,
  with stress/invalid settings excluded from any pooled claim.

Evidence hierarchy:

- hero evidence: admission trade-off;
- validation evidence: cross-model tail heterogeneity;
- controls/robustness: cross-task effect direction and validity labels.

Statistics needed:
Threshold replay uses all 36 local-arm outputs, including two 0/37 and
thirty-four >=33/37 outputs. Cross-model rates show raw counts, not confidence
intervals. Recursive-manager effects are descriptive normalized-score
differences and are not pooled.

Source data needed:
`local_gate_threshold_replay.csv`, `raw_append_cross_model.csv`, and
`recursive_manager_boundaries.csv`.

Image-integrity notes:
Vector plots only.

Reviewer risk:
Thresholds 1-2 may look universally optimal. Label the analysis retrospective
and specific to this frozen sample. Mark noisy or invalid controls explicitly.
