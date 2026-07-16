param(
    [ValidateSet("Smoke", "Formal")]
    [string]$Mode = "Smoke",
    [ValidateSet("Qwen", "Glm")]
    [string]$ModelFamily = "Qwen",
    [ValidateSet(256, 512)]
    [int]$MaxTokensSolver = 256
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

$modelSpec = if ($ModelFamily -eq "Qwen") {
    @{ Id = "qwen3-32b"; Slug = "qwen" }
} else {
    @{ Id = "glm-5.1"; Slug = "glm" }
}

Import-LocalEnvValue -Name "MODELARTS_MAAS_KEY"
$thinkingBody = '{\"enable_thinking\":false}'

$common = @(
    "-m", "sec.run_maze_alpha",
    "--phase", "gamma_p2_cross_model",
    "--model", $modelSpec.Id,
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
    "--max-tokens-solver", [string]$MaxTokensSolver,
    "--max-tokens-reviewer", "512",
    "--disable-thinking",
    "--llm-extra-body-json", $thinkingBody,
    "--skip-final-train"
)

$tag = "$($modelSpec.Slug)$MaxTokensSolver"
if ($Mode -eq "Smoke") {
    $outDir = "runs_maze_gamma_p2_smoke_$tag"
    $statsDir = "${outDir}_stats"
    $runArgs = $common + @(
        "--run-id-filter", "gamma_p2_frozen_reviewer",
        "--out-dir", $outDir,
        "--cache-dir", "cache_maze_gamma_p2_smoke_$tag",
        "--cache-policy", "off",
        "--seeds", "0",
        "--T", "1",
        "--train-size", "0",
        "--train-batch", "0",
        "--heldout-size", "12"
    )
} else {
    $outDir = "runs_maze_gamma_p2_$tag"
    $statsDir = "${outDir}_stats"
    $runArgs = $common + @(
        "--out-dir", $outDir,
        "--cache-dir", "cache_maze_gamma_p2_$tag",
        "--seeds", "0,1,2",
        "--T", "4",
        "--train-size", "24",
        "--train-batch", "4",
        "--heldout-size", "12"
    )
}

Write-Output "[$(Get-Date -Format o)] Starting Gamma P2 $Mode ($($modelSpec.Id), tokens=$MaxTokensSolver)"
& python @runArgs
if ($LASTEXITCODE -ne 0) {
    throw "Gamma P2 $Mode failed with exit code ${LASTEXITCODE}"
}
Write-Output "[$(Get-Date -Format o)] Gamma P2 $Mode complete"

if ($Mode -eq "Smoke") {
    $result = "$outDir/n4_gt_false_seed0_gamma_p2_frozen_reviewer/result.json"
    & python -m sec.gamma_stats model-smoke `
        --result $result `
        --out-dir $statsDir `
        --expected-routes 48 `
        --success-min 0.25 `
        --success-max 0.85 `
        --parse-min 0.95 `
        --error-rate-max 0.01
    if ($LASTEXITCODE -ne 0) {
        throw "Gamma P2 model-smoke report failed with exit code ${LASTEXITCODE}"
    }
    Write-Output "[$(Get-Date -Format o)] Gamma P2 smoke report complete"
}
