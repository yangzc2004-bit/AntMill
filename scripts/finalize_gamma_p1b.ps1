param(
    [Parameter(Mandatory = $true)]
    [int]$TargetProcessId
)

$ErrorActionPreference = "Stop"
Write-Output "[$(Get-Date -Format o)] Waiting for Gamma P1b process $TargetProcessId"
Wait-Process -Id $TargetProcessId
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Python {
    param([string[]]$CommandArgs)
    Write-Output "[$(Get-Date -Format o)] python $($CommandArgs -join ' ')"
    & python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "python exited with code ${LASTEXITCODE}: $($CommandArgs -join ' ')"
    }
}

$cleanRuns = @(
    "--run", "clean:0=runs_maze_gamma_p1b_clean_rescue/n4_gt_false_seed0_gamma_p1b_shared_consolidated_archive_joint_topk/result.json",
    "--run", "clean:1=runs_maze_gamma_p1b_clean_rescue/n4_gt_false_seed1_gamma_p1b_shared_consolidated_archive_joint_topk/result.json",
    "--run", "clean:2=runs_maze_gamma_p1b_clean_rescue/n4_gt_false_seed2_gamma_p1b_shared_consolidated_archive_joint_topk/result.json"
)
$baselineRuns = @(
    "--baseline-run", "consolidated:0=runs_maze_beta_e2/n4_gt_false_seed0_e2_shared_consolidated_expel/result.json",
    "--baseline-run", "consolidated:1=runs_maze_beta_e2/n4_gt_false_seed1_e2_shared_consolidated_expel/result.json",
    "--baseline-run", "consolidated:2=runs_maze_beta_e2/n4_gt_false_seed2_e2_shared_consolidated_expel/result.json"
)

Write-Output "[$(Get-Date -Format o)] Gamma P1b process exited; evaluating manipulation"
$auditArgs = @("-m", "sec.gamma_stats", "retrieval-audit", "--mode", "formal") +
    $cleanRuns + $baselineRuns + @(
        "--out-dir", "runs_maze_gamma_p1b_clean_rescue_stats",
        "--t", "5",
        "--expected-limit", "6",
        "--distinct-ratio-min", "1.5"
    )
Invoke-Python -CommandArgs $auditArgs

$auditReport = Get-Content -LiteralPath `
    "runs_maze_gamma_p1b_clean_rescue_stats/retrieval_audit_report.json" -Raw |
    ConvertFrom-Json

$latencyArgs = @("-m", "sec.gamma_stats", "latency-summary") + $cleanRuns + @(
    "--out-dir", "runs_maze_gamma_p1b_clean_rescue_stats"
)
Invoke-Python -CommandArgs $latencyArgs

if (-not $auditReport.passed) {
    Write-Output "[$(Get-Date -Format o)] Manipulation gate failed: $($auditReport.decision)"
    Write-Output "[$(Get-Date -Format o)] Behavioral gate and compression are blocked by amendment 01"
    exit 0
}

$behaviorRuns = @(
    "--run", "consolidated:0=runs_maze_beta_e2/n4_gt_false_seed0_e2_shared_consolidated_expel/result.json",
    "--run", "consolidated:1=runs_maze_beta_e2/n4_gt_false_seed1_e2_shared_consolidated_expel/result.json",
    "--run", "consolidated:2=runs_maze_beta_e2/n4_gt_false_seed2_e2_shared_consolidated_expel/result.json"
) + $cleanRuns
$gateArgs = @("-m", "sec.gamma_stats", "gate", "--kind", "rescue") + $behaviorRuns + @(
    "--intervention", "clean", "--baseline", "consolidated", "--t", "5",
    "--out-dir", "runs_maze_gamma_p1b_clean_rescue_stats"
)
Invoke-Python -CommandArgs $gateArgs

$gateReport = Get-Content -LiteralPath `
    "runs_maze_gamma_p1b_clean_rescue_stats/rescue_gate_report.json" -Raw |
    ConvertFrom-Json
if ($gateReport.decision -eq "rescue_pass") {
    Write-Output "[$(Get-Date -Format o)] P1b rescue passed; compression is permitted"
} else {
    Write-Output "[$(Get-Date -Format o)] P1b rescue did not pass; compression is blocked"
}
Write-Output "[$(Get-Date -Format o)] Gamma P1b finalization complete"
