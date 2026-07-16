param(
    [string]$PaperDir = "paper_draft",
    [string]$MainStem = "antmill_memory_aaai27_en",
    [string]$SupplementStem = "antmill_memory_aaai27_supp",
    [string]$ChecklistStem = "antmill_memory_reproducibility_checklist"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m sec.revision_evidence --out-dir "runs_revision_evidence"
if ($LASTEXITCODE -ne 0) {
    throw "Unified revision-evidence verification failed."
}
$revisionGate = Get-Content `
    "runs_revision_evidence/revision_evidence.json" `
    -Raw | ConvertFrom-Json
if (
    $revisionGate.status -ne "ready_for_paper_revision" -or
    -not $revisionGate.data_complete -or
    -not $revisionGate.p3_reports_same_quality
) {
    throw "Refusing final compilation; unified revision evidence is incomplete or inconsistent."
}

python -m sec.paper_results `
    --revision-gate "runs_revision_evidence/revision_evidence.json" `
    --out-dir "$PaperDir/generated/revision_results"
if ($LASTEXITCODE -ne 0) {
    throw "Paper-result artifact regeneration failed."
}

python -m sec.claim_decisions `
    --revision-gate "runs_revision_evidence/revision_evidence.json" `
    --out-dir "$PaperDir/generated/revision_results"
if ($LASTEXITCODE -ne 0) {
    throw "Claim-decision regeneration failed."
}

python -m sec.environment_manifest
if ($LASTEXITCODE -ne 0) {
    throw "Execution-environment manifest generation failed."
}
$environmentManifest = Get-Content `
    "$PaperDir/generated/revision_results/environment_manifest.json" `
    -Raw | ConvertFrom-Json
if ($environmentManifest.status -ne "environment_manifest_ready") {
    throw "Refusing final compilation; execution-environment manifest is incomplete."
}

$required = @(
    "$PaperDir/$MainStem.tex",
    "$PaperDir/$SupplementStem.tex",
    "$PaperDir/antmill_memory.bib",
    "$PaperDir/generated/revision_results/revision_macros.tex",
    "$PaperDir/generated/revision_results/mechanism_controls.tex",
    "$PaperDir/generated/revision_results/sensitivity_envelope.tex",
    "$PaperDir/generated/revision_results/miniwob_boundary.tex",
    "$PaperDir/generated/revision_results/appendix_heterogeneity.tex",
    "$PaperDir/generated/revision_results/appendix_diagnostics.tex",
    "$PaperDir/generated/revision_results/claim_decisions.json",
    "$PaperDir/generated/revision_results/paper_results_manifest.json",
    "$PaperDir/generated/revision_results/environment_manifest.json",
    "$PaperDir/generated/revision_results/environment_manifest.tex",
    "reproducibility_checklist_responses_memory.json"
)

$missing = @($required | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missing.Count -gt 0) {
    throw "Refusing final compilation; generated revision artifacts are missing: $($missing -join ', ')"
}

python -m sec.reproducibility_checklist `
    --out "$PaperDir/$ChecklistStem.tex"
if ($LASTEXITCODE -ne 0) {
    throw "Reproducibility checklist generation failed."
}
$checklistReport = Get-Content `
    "$PaperDir/generated/revision_results/reproducibility_checklist_report.json" `
    -Raw | ConvertFrom-Json
if ($checklistReport.status -ne "checklist_ready") {
    throw "Refusing final compilation; reproducibility checklist is not finalized."
}

Push-Location $PaperDir
try {
    & pdflatex -interaction=nonstopmode -halt-on-error "$MainStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "First main-paper pdflatex pass failed." }

    & bibtex $MainStem
    if ($LASTEXITCODE -ne 0) { throw "Main-paper bibtex pass failed." }

    & pdflatex -interaction=nonstopmode -halt-on-error "$MainStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "Second main-paper pdflatex pass failed." }

    & pdflatex -interaction=nonstopmode -halt-on-error "$MainStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "Final main-paper pdflatex pass failed." }

    & pdflatex -interaction=nonstopmode -halt-on-error "$SupplementStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "First supplement pdflatex pass failed." }

    & pdflatex -interaction=nonstopmode -halt-on-error "$SupplementStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "Final supplement pdflatex pass failed." }

    & pdflatex -interaction=nonstopmode -halt-on-error "$ChecklistStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "First checklist pdflatex pass failed." }

    & pdflatex -interaction=nonstopmode -halt-on-error "$ChecklistStem.tex"
    if ($LASTEXITCODE -ne 0) { throw "Final checklist pdflatex pass failed." }
}
finally {
    Pop-Location
}

$mainPdf = Join-Path $PaperDir "$MainStem.pdf"
$supplementPdf = Join-Path $PaperDir "$SupplementStem.pdf"
$checklistPdf = Join-Path $PaperDir "$ChecklistStem.pdf"
if (-not (Test-Path -LiteralPath $mainPdf)) {
    throw "Main-paper PDF was not produced: $mainPdf"
}
if (-not (Test-Path -LiteralPath $supplementPdf)) {
    throw "Supplement PDF was not produced: $supplementPdf"
}
if (-not (Test-Path -LiteralPath $checklistPdf)) {
    throw "Checklist PDF was not produced: $checklistPdf"
}

Write-Output "compiled_main=$mainPdf"
Write-Output "compiled_supplement=$supplementPdf"
Write-Output "compiled_checklist=$checklistPdf"
