$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& "$PSScriptRoot/run_gamma_p3e.ps1" -Mode Smoke
& "$PSScriptRoot/finalize_p3e_smoke.ps1"
& "$PSScriptRoot/run_gamma_p3e.ps1" -Mode Formal
& "$PSScriptRoot/finalize_p3_formal.ps1" `
    -RunsDir "runs_miniwob_gamma_p3e" `
    -OutDir "runs_miniwob_gamma_p3e_stats"
