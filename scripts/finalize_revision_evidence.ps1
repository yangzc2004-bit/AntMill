param(
    [int]$PollSeconds = 60,
    [string]$OutDir = "runs_revision_evidence"
)

Set-Location (Split-Path -Parent $PSScriptRoot)

$required = @(
    "runs_maze_epsilon_controls_stats/evidence_manifest.json",
    "runs_maze_epsilon_sensitivity_stats/evidence_manifest.json",
    "runs_maze_zeta_exact_yoke_stats/evidence_manifest.json",
    "runs_miniwob_gamma_p3e_stats/p3_gate_report.json",
    "runs_miniwob_gamma_p3e_stats/append_secondary/p3_gate_report.json"
)

$missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_) })
while ($missing.Count -gt 0) {
    Start-Sleep -Seconds $PollSeconds
    $missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_) })
}

python -m sec.revision_evidence --out-dir $OutDir
if ($LASTEXITCODE -ne 0) {
    throw "Unified revision evidence generation failed."
}
python -m sec.paper_results `
    --revision-gate (Join-Path $OutDir "revision_evidence.json") `
    --out-dir "paper_draft/generated/revision_results"
if ($LASTEXITCODE -ne 0) {
    throw "Paper-result artifact generation failed."
}
python -m sec.claim_decisions `
    --revision-gate (Join-Path $OutDir "revision_evidence.json") `
    --out-dir "paper_draft/generated/revision_results"
if ($LASTEXITCODE -ne 0) {
    throw "Claim-decision generation failed."
}
python -m sec.reproducibility_checklist
if ($LASTEXITCODE -ne 0) {
    throw "Reproducibility checklist generation failed."
}
python -m sec.environment_manifest
if ($LASTEXITCODE -ne 0) {
    throw "Environment manifest generation failed."
}
