param(
    [switch]$SkipPrimarySmoke
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$primaryTasks = @(
    "click-button",
    "choose-list",
    "enter-text",
    "click-checkboxes",
    "login-user",
    "use-autocomplete-nodelay"
)
$replacementTasks = @("click-menu", "choose-date-nodelay", "form-sequence")

function Invoke-CheckedPowerShell {
    param([string[]]$Arguments)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PowerShell command failed: $($Arguments -join ' ')"
    }
}

function Build-RunSpecs {
    param(
        [string[]]$Tasks,
        [string]$OutDir,
        [string[]]$Seeds
    )
    $specs = @()
    foreach ($task in $Tasks) {
        $safeTask = $task.Replace("-", "_")
        foreach ($seed in $Seeds) {
            foreach ($arm in @(
                @{ Name = "frozen"; Suffix = "frozen_reviewer" },
                @{ Name = "append"; Suffix = "shared_append_ga" },
                @{ Name = "consolidated"; Suffix = "shared_consolidated_expel" }
            )) {
                $path = "$OutDir/n4_gt_false_seed$seed" + "_gamma_p3_$safeTask" + "_$($arm.Suffix)/result.json"
                $specs += "--run"
                $specs += "$($arm.Name):${seed}:${task}=$path"
            }
        }
    }
    return $specs
}

function Write-SelectionManifest {
    param(
        [string[]]$Selected,
        [object[]]$Replacements,
        [string]$Status
    )
    $outDir = "runs_miniwob_gamma_p3_orchestration"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $payload = @{
        status = $Status
        selected_tasks = $Selected
        replacements = $Replacements
        created_at = (Get-Date -Format o)
        preregistration = "prereg_phase_gamma_p3_execution.md"
    }
    $payload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$outDir/task_selection.json" -Encoding utf8
    $lines = @("# Preregistration Deviations", "")
    if ($Replacements.Count -eq 0) {
        $lines += "No task substitutions recorded."
    } else {
        $lines += "Technical smoke substitutions, fixed before formal P3 outcome data:"
        foreach ($item in $Replacements) {
            $lines += "- $($item.primary) -> $($item.replacement); passed=$($item.passed)"
        }
    }
    Set-Content -LiteralPath "$outDir/prereg_deviation_log.md" -Value ($lines -join [Environment]::NewLine) -Encoding utf8
}

function Get-SelectionStatus {
    $path = "runs_miniwob_gamma_p3_orchestration/task_selection.json"
    if (-not (Test-Path -LiteralPath $path)) {
        return ""
    }
    return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json).status
}

function Invoke-SmokeReport {
    param([string[]]$Tasks)
    $specs = Build-RunSpecs -Tasks $Tasks -OutDir "runs_miniwob_gamma_p3_smoke" -Seeds @("0")
    $outDir = "runs_miniwob_gamma_p3_smoke_stats"
    $pythonArgs = @("-m", "sec.miniwob_stats", "smoke") + $specs + @(
        "--out-dir", $outDir,
        "--parse-min", "0.95",
        "--infrastructure-error-max", "0.02",
        "--hash-agreement-min", "0.95",
        "--expected-routes-per-result", "8"
    )
    & python @pythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "P3 smoke statistics failed"
    }
    return Get-Content -LiteralPath "$outDir/p3_smoke_report.json" -Raw | ConvertFrom-Json
}

$existingStatus = Get-SelectionStatus
if ($existingStatus -in @(
    "formal_started",
    "p3_not_evaluable_global_smoke_failure",
    "p3_not_evaluable_too_many_primary_failures",
    "p3_not_evaluable_replacement_failed",
    "p3_not_evaluable_action_interface_failure"
)) {
    Write-Output "[$(Get-Date -Format o)] P3 orchestration already terminal: $existingStatus"
    exit 0
}

if (-not $SkipPrimarySmoke) {
    Write-Output "[$(Get-Date -Format o)] Starting P3 primary-task smoke"
    Invoke-CheckedPowerShell -Arguments (@(
        "-File", (Join-Path $PSScriptRoot "run_gamma_p3.ps1"),
        "-Mode", "Smoke",
        "-Tasks", ($primaryTasks -join ",")
    ))
} else {
    Write-Output "[$(Get-Date -Format o)] Reusing completed primary-task smoke"
}
$smoke = Invoke-SmokeReport -Tasks $primaryTasks

$failedPrimary = @($smoke.task_eligibility | Where-Object { -not $_.passed } | ForEach-Object { $_.family })
if (-not $smoke.checks.hash_agreement -or -not $smoke.checks.reviewer_summary_schema) {
    Write-SelectionManifest -Selected @() -Replacements @() -Status "p3_not_evaluable_global_smoke_failure"
    Write-Output "[$(Get-Date -Format o)] P3 stops: global smoke guardrail failed"
    exit 0
}
if ($failedPrimary.Count -gt $replacementTasks.Count) {
    Write-SelectionManifest -Selected @() -Replacements @() -Status "p3_not_evaluable_too_many_primary_failures"
    Write-Output "[$(Get-Date -Format o)] P3 stops: more than three primary tasks failed smoke"
    exit 0
}

$selected = New-Object System.Collections.Generic.List[string]
$replacementLog = New-Object System.Collections.Generic.List[object]
$replacementIndex = 0
foreach ($task in $primaryTasks) {
    if ($failedPrimary -contains $task) {
        $replacement = $replacementTasks[$replacementIndex]
        $replacementIndex += 1
        Write-Output "[$(Get-Date -Format o)] Smoke replacement: $task -> $replacement"
        Invoke-CheckedPowerShell -Arguments (@(
            "-File", (Join-Path $PSScriptRoot "run_gamma_p3.ps1"),
            "-Mode", "Smoke",
            "-Tasks", $replacement
        ))
        $replacementSmoke = Invoke-SmokeReport -Tasks @($replacement)
        $replacementEligible = @($replacementSmoke.task_eligibility | Where-Object { $_.family -eq $replacement })[0]
        if (
            -not $replacementSmoke.checks.hash_agreement -or
            -not $replacementSmoke.checks.reviewer_summary_schema -or
            -not $replacementEligible.passed
        ) {
            $replacementLog.Add(@{ primary = $task; replacement = $replacement; passed = $false })
            Write-SelectionManifest -Selected @() -Replacements $replacementLog -Status "p3_not_evaluable_replacement_failed"
            Write-Output "[$(Get-Date -Format o)] P3 stops: replacement smoke failed"
            exit 0
        }
        $replacementLog.Add(@{ primary = $task; replacement = $replacement; passed = $true })
        $selected.Add($replacement)
    } else {
        $selected.Add($task)
    }
}

if ($selected.Count -ne 6) {
    throw "P3 selection did not produce exactly six task families"
}
Write-SelectionManifest -Selected $selected -Replacements $replacementLog -Status "formal_authorized"

Write-Output "[$(Get-Date -Format o)] P3 smoke passed; selected tasks: $($selected -join ', ')"
Write-SelectionManifest -Selected $selected -Replacements $replacementLog -Status "formal_started"
Invoke-CheckedPowerShell -Arguments (@(
    "-File", (Join-Path $PSScriptRoot "run_gamma_p3.ps1"),
    "-Mode", "Formal",
    "-Tasks", ($selected -join ",")
))

$formalSpecs = Build-RunSpecs -Tasks $selected.ToArray() -OutDir "runs_miniwob_gamma_p3" -Seeds @("0", "1", "2")
$statsDir = "runs_miniwob_gamma_p3_stats"
$gateArgs = @("-m", "sec.miniwob_stats", "gate") + $formalSpecs + @(
    "--intervention", "consolidated",
    "--baseline", "frozen",
    "--t", "3",
    "--out-dir", $statsDir
)
& python @gateArgs
if ($LASTEXITCODE -ne 0) {
    throw "P3 gate statistics failed"
}
$latencyArgs = @("-m", "sec.miniwob_stats", "latency-summary") + $formalSpecs + @(
    "--out-dir", $statsDir
)
& python @latencyArgs
if ($LASTEXITCODE -ne 0) {
    throw "P3 latency summary failed"
}
Write-Output "[$(Get-Date -Format o)] Gamma P3 complete; no MiniWoB rescue is scheduled"
