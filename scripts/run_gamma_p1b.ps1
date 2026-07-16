param(
    [ValidateSet("Smoke", "Formal")]
    [string]$Mode = "Smoke"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Import-LocalEnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $line = Get-Content -LiteralPath ".env" |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -First 1
    if (-not $line) {
        throw "Missing $Name in .env"
    }
    $value = ($line -split "=", 2)[1].Trim()
    if (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($Name, $value, "Process")
}

Import-LocalEnvValue -Name "MODELARTS_MAAS_KEY"

$common = @(
    "-m", "sec.run_maze_alpha",
    "--phase", "gamma_p1b_clean_rescue",
    "--model", "DeepSeek-V3",
    "--base-url", "https://api.modelarts-maas.com/v2",
    "--api-key-env", "MODELARTS_MAAS_KEY",
    "--maze-width", "15",
    "--maze-height", "15",
    "--maze-family", "trap",
    "--maze-agent-mode", "state_guided",
    "--maze-min-shortest", "30",
    "--max-steps", "120",
    "--concurrency", "8",
    "--retrieval-k", "6",
    "--library-cap", "80",
    "--max-tokens-solver", "256",
    "--max-tokens-reviewer", "512",
    "--skip-final-train"
)

if ($Mode -eq "Smoke") {
    $runArgs = $common + @(
        "--out-dir", "runs_maze_gamma_p1b_smoke",
        "--cache-dir", "cache_maze_gamma_p1b_smoke",
        "--seeds", "9001",
        "--T", "2",
        "--train-size", "8",
        "--train-batch", "4",
        "--heldout-size", "2"
    )
} else {
    $runArgs = $common + @(
        "--out-dir", "runs_maze_gamma_p1b_clean_rescue",
        "--cache-dir", "cache_maze_gamma_p1b_clean_rescue",
        "--seeds", "0,1,2",
        "--T", "6",
        "--train-size", "24",
        "--train-batch", "4",
        "--heldout-size", "12"
    )
}

Write-Output "[$(Get-Date -Format o)] Starting Gamma P1b $Mode"
& python @runArgs
if ($LASTEXITCODE -ne 0) {
    throw "Gamma P1b $Mode failed with exit code $LASTEXITCODE"
}
Write-Output "[$(Get-Date -Format o)] Gamma P1b $Mode complete"

if ($Mode -eq "Smoke") {
    & python -m sec.gamma_stats retrieval-audit `
        --mode smoke `
        --run "clean:9001=runs_maze_gamma_p1b_smoke/n4_gt_false_seed9001_gamma_p1b_shared_consolidated_archive_joint_topk/result.json" `
        --out-dir runs_maze_gamma_p1b_smoke_stats `
        --expected-limit 6
    if ($LASTEXITCODE -ne 0) {
        throw "Gamma P1b smoke retrieval audit failed with exit code $LASTEXITCODE"
    }
    Write-Output "[$(Get-Date -Format o)] Gamma P1b smoke audit complete"
}
