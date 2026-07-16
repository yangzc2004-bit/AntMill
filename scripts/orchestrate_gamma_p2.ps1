$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-P2Smoke {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("Qwen", "Glm")][string]$ModelFamily,
        [Parameter(Mandatory = $true)][ValidateSet(256, 512)][int]$MaxTokensSolver
    )
    $slug = if ($ModelFamily -eq "Qwen") { "qwen" } else { "glm" }
    $tag = "$slug$MaxTokensSolver"
    Write-Output "[$(Get-Date -Format o)] P2 smoke attempt: $tag"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        (Join-Path $PSScriptRoot "run_gamma_p2.ps1") `
        -Mode Smoke -ModelFamily $ModelFamily -MaxTokensSolver $MaxTokensSolver
    if ($LASTEXITCODE -ne 0) {
        Write-Output "[$(Get-Date -Format o)] P2 smoke command failed: $tag"
        return $null
    }
    $reportPath = "runs_maze_gamma_p2_smoke_${tag}_stats/model_smoke_report.json"
    if (-not (Test-Path -LiteralPath $reportPath)) {
        Write-Output "[$(Get-Date -Format o)] P2 smoke report missing: $tag"
        return $null
    }
    return Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
}

function Select-P2Model {
    $qwen256 = Invoke-P2Smoke -ModelFamily Qwen -MaxTokensSolver 256
    if ($qwen256 -and $qwen256.decision -eq "smoke_pass") {
        return @{ Family = "Qwen"; Tokens = 256; Smoke = $qwen256 }
    }
    if ($qwen256 -and $qwen256.decision -eq "retry_with_512") {
        $qwen512 = Invoke-P2Smoke -ModelFamily Qwen -MaxTokensSolver 512
        if ($qwen512 -and $qwen512.decision -eq "smoke_pass") {
            return @{ Family = "Qwen"; Tokens = 512; Smoke = $qwen512 }
        }
    }

    $glm256 = Invoke-P2Smoke -ModelFamily Glm -MaxTokensSolver 256
    if ($glm256 -and $glm256.decision -eq "smoke_pass") {
        return @{ Family = "Glm"; Tokens = 256; Smoke = $glm256 }
    }
    if ($glm256 -and $glm256.decision -eq "retry_with_512") {
        $glm512 = Invoke-P2Smoke -ModelFamily Glm -MaxTokensSolver 512
        if ($glm512 -and $glm512.decision -eq "smoke_pass") {
            return @{ Family = "Glm"; Tokens = 512; Smoke = $glm512 }
        }
    }
    return $null
}

function Invoke-Python {
    param([string[]]$CommandArgs)
    Write-Output "[$(Get-Date -Format o)] python $($CommandArgs -join ' ')"
    & python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "python exited with code ${LASTEXITCODE}: $($CommandArgs -join ' ')"
    }
}

$selected = Select-P2Model
if (-not $selected) {
    Write-Output "[$(Get-Date -Format o)] No P2 model passed smoke; P2 stops as not evaluable"
    exit 0
}

$slug = if ($selected.Family -eq "Qwen") { "qwen" } else { "glm" }
$tag = "$slug$($selected.Tokens)"
Write-Output "[$(Get-Date -Format o)] P2 selected $($selected.Family) at $($selected.Tokens) tokens"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $PSScriptRoot "run_gamma_p2.ps1") `
    -Mode Formal -ModelFamily $selected.Family -MaxTokensSolver $selected.Tokens
if ($LASTEXITCODE -ne 0) {
    throw "Gamma P2 formal failed with exit code ${LASTEXITCODE}"
}

$outDir = "runs_maze_gamma_p2_$tag"
$statsDir = "${outDir}_stats"
$allRuns = @(
    "--run", "frozen:0=$outDir/n4_gt_false_seed0_gamma_p2_frozen_reviewer/result.json",
    "--run", "append:0=$outDir/n4_gt_false_seed0_gamma_p2_shared_append_ga/result.json",
    "--run", "consolidated:0=$outDir/n4_gt_false_seed0_gamma_p2_shared_consolidated_expel/result.json",
    "--run", "frozen:1=$outDir/n4_gt_false_seed1_gamma_p2_frozen_reviewer/result.json",
    "--run", "append:1=$outDir/n4_gt_false_seed1_gamma_p2_shared_append_ga/result.json",
    "--run", "consolidated:1=$outDir/n4_gt_false_seed1_gamma_p2_shared_consolidated_expel/result.json",
    "--run", "frozen:2=$outDir/n4_gt_false_seed2_gamma_p2_frozen_reviewer/result.json",
    "--run", "append:2=$outDir/n4_gt_false_seed2_gamma_p2_shared_append_ga/result.json",
    "--run", "consolidated:2=$outDir/n4_gt_false_seed2_gamma_p2_shared_consolidated_expel/result.json"
)
$primaryRuns = @(
    "--run", "frozen:0=$outDir/n4_gt_false_seed0_gamma_p2_frozen_reviewer/result.json",
    "--run", "consolidated:0=$outDir/n4_gt_false_seed0_gamma_p2_shared_consolidated_expel/result.json",
    "--run", "frozen:1=$outDir/n4_gt_false_seed1_gamma_p2_frozen_reviewer/result.json",
    "--run", "consolidated:1=$outDir/n4_gt_false_seed1_gamma_p2_shared_consolidated_expel/result.json",
    "--run", "frozen:2=$outDir/n4_gt_false_seed2_gamma_p2_frozen_reviewer/result.json",
    "--run", "consolidated:2=$outDir/n4_gt_false_seed2_gamma_p2_shared_consolidated_expel/result.json"
)

Invoke-Python -CommandArgs (@("-m", "sec.gamma_stats", "gate", "--kind", "p2") + $primaryRuns + @(
    "--intervention", "consolidated",
    "--baseline", "frozen",
    "--t", "3",
    "--out-dir", $statsDir
))
Invoke-Python -CommandArgs (@("-m", "sec.gamma_stats", "latency-summary") + $allRuns + @(
    "--out-dir", $statsDir
))
Write-Output "[$(Get-Date -Format o)] Gamma P2 complete; no rescue is scheduled because P1b manipulation did not pass"
