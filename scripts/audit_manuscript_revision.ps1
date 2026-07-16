param(
    [string]$OutDir = "runs_manuscript_revision_audit"
)

Set-Location (Split-Path -Parent $PSScriptRoot)

python -m sec.manuscript_revision_audit --out-dir $OutDir
