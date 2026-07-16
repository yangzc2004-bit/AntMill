param(
    [string]$OutDir = "runs_live_health"
)

Set-Location (Split-Path -Parent $PSScriptRoot)

python -m sec.live_run_health --out-dir $OutDir
