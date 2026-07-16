# Phase Gamma P3 execution amendment 03: explicit local browser bootstrap

Status: frozen on 2026-07-14 before generating any P3d smoke outcome data.

## Trigger

The P3c complete-smoke launch was stopped for an infrastructure configuration
failure. Its manifests recorded empty `MINIWOB_URL` and
`MINIWOB_BROWSER_EXECUTABLE` values. BrowserGym therefore failed during
environment reset before solvers could take an action. The six completed P3c
arm-family artifacts are invalid infrastructure records only and are not
included in any smoke report or task eligibility decision.

P3b's prior action-interface calibration used the local MiniWoB++ root
`file:///D:/antmill/tmp/miniwob-plusplus/miniwob/html/miniwob/` and Chrome
executable `C:/Program Files/Google/Chrome/Application/chrome.exe`. Both paths
exist at the time of this freeze.

## Frozen P3d smoke execution

Run the unchanged six-family P3c smoke matrix in new directories:

- `runs_miniwob_gamma_p3d_smoke`
- `cache_miniwob_gamma_p3d_smoke`

Set the following process environment variables for the entire run:

```powershell
$env:MINIWOB_URL = "file:///D:/antmill/tmp/miniwob-plusplus/miniwob/html/miniwob/"
$env:MINIWOB_BROWSER_EXECUTABLE = "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

All P3 base-appendix, amendment-01 action-interface, and amendment-02
complete-matrix rules apply unchanged. The P3d smoke report must use only P3d
artifacts. It may authorize formal P3 only if all frozen checks pass.

## What remains unchanged

This is an environment bootstrap correction only. It does not alter models,
task families, replacement policy, arms, prompts, action schema, cache policy,
metrics, thresholds, formal matrix, analysis, or stopping rules.
