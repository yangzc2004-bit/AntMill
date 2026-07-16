param(
    [string]$OutDir = "runs_goal_evidence_audit"
)

Set-Location (Split-Path -Parent $PSScriptRoot)

python -m sec.goal_evidence_audit --out-dir $OutDir
