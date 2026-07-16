param(
    [Parameter(Mandatory = $true)]
    [int]$TargetProcessId
)

$ErrorActionPreference = "Stop"
Write-Output "[$(Get-Date -Format o)] Waiting for Gamma P1 process $TargetProcessId"
Wait-Process -Id $TargetProcessId
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Output "[$(Get-Date -Format o)] Gamma P1 process exited; generating rescue gate"

function Invoke-Python {
    param([string[]]$CommandArgs)
    & python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "python exited with code ${LASTEXITCODE}: $($CommandArgs -join ' ')"
    }
}

$runs = @(
    "--run", "consolidated:0=runs_maze_beta_e2/n4_gt_false_seed0_e2_shared_consolidated_expel/result.json",
    "--run", "consolidated:1=runs_maze_beta_e2/n4_gt_false_seed1_e2_shared_consolidated_expel/result.json",
    "--run", "consolidated:2=runs_maze_beta_e2/n4_gt_false_seed2_e2_shared_consolidated_expel/result.json",
    "--run", "rescue:0=runs_maze_gamma_p1_rescue/n4_gt_false_seed0_gamma_p1_shared_consolidated_archive_rescue/result.json",
    "--run", "rescue:1=runs_maze_gamma_p1_rescue/n4_gt_false_seed1_gamma_p1_shared_consolidated_archive_rescue/result.json",
    "--run", "rescue:2=runs_maze_gamma_p1_rescue/n4_gt_false_seed2_gamma_p1_shared_consolidated_archive_rescue/result.json"
)

$gateArgs = @("-m", "sec.gamma_stats", "gate", "--kind", "rescue") + $runs + @(
    "--intervention", "rescue", "--baseline", "consolidated", "--t", "5",
    "--out-dir", "runs_maze_gamma_p1_rescue_stats"
)
Invoke-Python -CommandArgs $gateArgs

$rescueRuns = @(
    "--run", "rescue:0=runs_maze_gamma_p1_rescue/n4_gt_false_seed0_gamma_p1_shared_consolidated_archive_rescue/result.json",
    "--run", "rescue:1=runs_maze_gamma_p1_rescue/n4_gt_false_seed1_gamma_p1_shared_consolidated_archive_rescue/result.json",
    "--run", "rescue:2=runs_maze_gamma_p1_rescue/n4_gt_false_seed2_gamma_p1_shared_consolidated_archive_rescue/result.json"
)

$latencyArgs = @("-m", "sec.gamma_stats", "latency-summary") + $rescueRuns + @(
    "--out-dir", "runs_maze_gamma_p1_rescue_stats"
)
Invoke-Python -CommandArgs $latencyArgs
Write-Output "[$(Get-Date -Format o)] Gamma P1 finalization complete"
