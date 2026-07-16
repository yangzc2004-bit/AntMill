param(
    [string]$Checkpoint = "formal_provider_freeze_checkpoint_20260715.json",
    [switch]$ProbeOnly
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function ConvertTo-EncodedPowerShellCommand {
    param([Parameter(Mandatory = $true)][string]$Command)
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
}

$dotenvBootstrap = @'
$dotenvLines = Get-Content -LiteralPath ".env" -ErrorAction Stop
foreach ($dotenvLine in $dotenvLines) {
    if ($dotenvLine -match "^\s*MODELARTS_MAAS_KEY\s*=\s*(.+?)\s*$") {
        $env:MODELARTS_MAAS_KEY = $matches[1].Trim().Trim('"').Trim("'")
    }
}
if (-not $env:MODELARTS_MAAS_KEY) {
    throw "Missing MODELARTS_MAAS_KEY after loading .env."
}
'@

Invoke-Expression $dotenvBootstrap
python -m sec.formal_recovery verify --checkpoint $Checkpoint
if ($LASTEXITCODE -ne 0) {
    throw "Formal recovery checkpoint verification failed."
}
python -m sec.formal_recovery probe
if ($LASTEXITCODE -ne 0) {
    throw "ModelArts provider probe failed; formal runs remain paused."
}
if ($ProbeOnly) {
    Write-Output "provider_probe_pass"
    exit 0
}

$epsilonWorkerBody = @'
$matrix = @(
    [pscustomobject]@{ Seed = 1; Arm = "epsilon_shared_consolidated_mmr" }
)
foreach ($seed in 2, 3, 4) {
    foreach ($arm in @(
        "epsilon_frozen_reviewer",
        "epsilon_private_consolidated",
        "epsilon_shared_consolidated",
        "epsilon_shared_append_cap14",
        "epsilon_shared_consolidated_mmr"
    )) {
        $matrix += [pscustomobject]@{ Seed = $seed; Arm = $arm }
    }
}
foreach ($entry in $matrix) {
    $condition = "n4_gt_false_seed$($entry.Seed)_$($entry.Arm)"
    $probeOut = "runs_provider_freeze_audit/20260715_81006/probes/epsilon_$($entry.Seed)_$($entry.Arm).json"
    python -m sec.formal_recovery probe --out $probeOut
    if ($LASTEXITCODE -ne 0) {
        throw "Provider probe failed before Epsilon $condition."
    }
    python -m sec.run_maze_alpha `
        --phase epsilon_controls `
        --model DeepSeek-V3 `
        --base-url https://api.modelarts-maas.com/v2 `
        --api-key-env MODELARTS_MAAS_KEY `
        --seeds $entry.Seed `
        --run-id-filter $entry.Arm `
        --T 6 `
        --train-batch 4 `
        --train-size 24 `
        --heldout-size 12 `
        --maze-width 15 `
        --maze-height 15 `
        --maze-family trap `
        --maze-min-shortest 30 `
        --maze-agent-mode state_guided `
        --max-steps 120 `
        --retrieval-k 6 `
        --library-cap 80 `
        --concurrency 8 `
        --skip-final-train `
        --out-dir runs_maze_epsilon_controls `
        --cache-dir cache_maze_epsilon_controls
    if ($LASTEXITCODE -ne 0) {
        throw "Epsilon formal condition failed: $condition."
    }
    $result = "runs_maze_epsilon_controls/$condition/result.json"
    $quality = "runs_provider_freeze_audit/20260715_81006/quality/epsilon_$($entry.Seed)_$($entry.Arm).json"
    python -m sec.formal_recovery validate-target --suite epsilon --result $result --out $quality
    if ($LASTEXITCODE -ne 0) {
        throw "Epsilon recovery quality failed: $condition."
    }
}
'@
$epsilonWorkerCommand = @(
    $dotenvBootstrap,
    $epsilonWorkerBody,
    "python -m sec.formal_recovery verify --checkpoint $Checkpoint",
    'if ($LASTEXITCODE -ne 0) { throw "Completed pre-outage Epsilon artifacts changed." }'
) -join [Environment]::NewLine

$p3WorkerBody = @'
$matrix = @(
    [pscustomobject]@{ Family = "choose-list"; Seed = 2; Arm = "consolidated" }
)
foreach ($family in @(
    "enter-text",
    "click-checkboxes",
    "login-user",
    "use-autocomplete-nodelay"
)) {
    foreach ($seed in 0, 1, 2) {
        foreach ($arm in "frozen", "append", "consolidated") {
            $matrix += [pscustomobject]@{
                Family = $family
                Seed = $seed
                Arm = $arm
            }
        }
    }
}
foreach ($entry in $matrix) {
    $familyToken = $entry.Family.Replace("-", "_")
    $suffix = @{
        frozen = "frozen_reviewer"
        append = "shared_append_ga"
        consolidated = "shared_consolidated_expel"
    }[$entry.Arm]
    $condition = "n4_gt_false_seed$($entry.Seed)_gamma_p3_$familyToken`_$suffix"
    $probeOut = "runs_provider_freeze_audit/20260715_81006/probes/p3_$familyToken`_$($entry.Seed)_$($entry.Arm).json"
    python -m sec.formal_recovery probe --out $probeOut
    if ($LASTEXITCODE -ne 0) {
        throw "Provider probe failed before P3 $condition."
    }
    python -m sec.resume_p3e_target `
        --family $entry.Family `
        --seed $entry.Seed `
        --arm $entry.Arm
    if ($LASTEXITCODE -ne 0) {
        throw "P3 formal condition failed: $condition."
    }
    $result = "runs_miniwob_gamma_p3e/$condition/result.json"
    $quality = "runs_provider_freeze_audit/20260715_81006/quality/p3_$familyToken`_$($entry.Seed)_$($entry.Arm).json"
    python -m sec.formal_recovery validate-target --suite p3 --result $result --out $quality
    if ($LASTEXITCODE -ne 0) {
        throw "P3 recovery quality failed: $condition."
    }
}
'@
$p3WorkerCommand = @(
    $dotenvBootstrap,
    $p3WorkerBody,
    "python -m sec.formal_recovery verify --checkpoint $Checkpoint",
    'if ($LASTEXITCODE -ne 0) { throw "Completed pre-outage P3 artifacts changed." }'
) -join [Environment]::NewLine

$epsilonWorker = Start-Process -FilePath powershell.exe `
    -ArgumentList @(
        "-NoProfile",
        "-EncodedCommand",
        (ConvertTo-EncodedPowerShellCommand $epsilonWorkerCommand)
    ) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_recovery.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_recovery.stderr.log") `
    -PassThru

$p3Worker = Start-Process -FilePath powershell.exe `
    -ArgumentList @(
        "-NoProfile",
        "-EncodedCommand",
        (ConvertTo-EncodedPowerShellCommand $p3WorkerCommand)
    ) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/p3e_recovery.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/p3e_recovery.stderr.log") `
    -PassThru

$epsilonFinalizerCommand = @"
Set-Location "$((Get-Location).Path)"
& .\scripts\finalize_epsilon_controls.ps1 -RunProcessId $($epsilonWorker.Id)
"@
$epsilonFinalizer = Start-Process -FilePath powershell.exe `
    -ArgumentList @(
        "-NoProfile",
        "-EncodedCommand",
        (ConvertTo-EncodedPowerShellCommand $epsilonFinalizerCommand)
    ) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_recovery_finalize.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_recovery_finalize.stderr.log") `
    -PassThru

$sensitivityCommand = @"
Set-Location "$((Get-Location).Path)"
& .\scripts\run_epsilon_sensitivity_after_controls.ps1 -ControlsFinalizerProcessId $($epsilonFinalizer.Id)
"@
$sensitivitySupervisor = Start-Process -FilePath powershell.exe `
    -ArgumentList @(
        "-NoProfile",
        "-EncodedCommand",
        (ConvertTo-EncodedPowerShellCommand $sensitivityCommand)
    ) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_recovery_sensitivity_supervisor.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_recovery_sensitivity_supervisor.stderr.log") `
    -PassThru

$zetaCommand = @"
Set-Location "$((Get-Location).Path)"
& .\scripts\run_zeta_after_epsilon.ps1
"@
$zetaSupervisor = Start-Process -FilePath powershell.exe `
    -ArgumentList @(
        "-NoProfile",
        "-EncodedCommand",
        (ConvertTo-EncodedPowerShellCommand $zetaCommand)
    ) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/zeta_recovery_supervisor.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/zeta_recovery_supervisor.stderr.log") `
    -PassThru

$p3FinalizerCommand = @"
Set-Location "$((Get-Location).Path)"
& .\scripts\finalize_p3_formal.ps1 -RunProcessId $($p3Worker.Id) -RunsDir runs_miniwob_gamma_p3e -OutDir runs_miniwob_gamma_p3e_stats
"@
$p3Finalizer = Start-Process -FilePath powershell.exe `
    -ArgumentList @(
        "-NoProfile",
        "-EncodedCommand",
        (ConvertTo-EncodedPowerShellCommand $p3FinalizerCommand)
    ) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/p3e_recovery_finalize.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/p3e_recovery_finalize.stderr.log") `
    -PassThru

$launch = [ordered]@{
    status = "formal_recovery_launched"
    created_at = (Get-Date).ToString("o")
    checkpoint = $Checkpoint
    epsilon_worker_pid = $epsilonWorker.Id
    epsilon_finalizer_pid = $epsilonFinalizer.Id
    sensitivity_supervisor_pid = $sensitivitySupervisor.Id
    zeta_supervisor_pid = $zetaSupervisor.Id
    p3_worker_pid = $p3Worker.Id
    p3_finalizer_pid = $p3Finalizer.Id
}
$launchPath = "runs_provider_freeze_audit/20260715_81006/recovery_launch.json"
New-Item -ItemType Directory -Force (Split-Path -Parent $launchPath) | Out-Null
$launch | ConvertTo-Json | Set-Content -LiteralPath $launchPath -Encoding UTF8
$launch | Format-List
