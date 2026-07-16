param(
    [ValidateSet("Render", "Finalize")]
    [string]$Mode = "Render",
    [string]$Pdf = "paper_draft/antmill_memory_aaai27_en.pdf",
    [string]$RenderDir = "tmp/pdfs/antmill_memory_final",
    [string]$FinalAudit = "paper_draft/generated/revision_results/final_render_audit.json",
    [switch]$ConfirmAllPagesRendered,
    [switch]$ConfirmNoTextOrTableClipping,
    [switch]$ConfirmNoOverlappingElements,
    [switch]$ConfirmFiguresAndTablesLegible,
    [switch]$ConfirmCaptionsMatchContent
)

Set-Location (Split-Path -Parent $PSScriptRoot)

if ($Mode -eq "Render") {
    python -m sec.pdf_render_audit render --pdf $Pdf --out-dir $RenderDir
    exit $LASTEXITCODE
}

python -m sec.pdf_render_audit finalize `
    --draft (Join-Path $RenderDir "render_audit_draft.json") `
    --out $FinalAudit `
    $(if ($ConfirmAllPagesRendered) { "--confirm-all-pages-rendered" }) `
    $(if ($ConfirmNoTextOrTableClipping) { "--confirm-no-text-or-table-clipping" }) `
    $(if ($ConfirmNoOverlappingElements) { "--confirm-no-overlapping-elements" }) `
    $(if ($ConfirmFiguresAndTablesLegible) { "--confirm-figures-and-tables-legible" }) `
    $(if ($ConfirmCaptionsMatchContent) { "--confirm-captions-match-content" })
exit $LASTEXITCODE
