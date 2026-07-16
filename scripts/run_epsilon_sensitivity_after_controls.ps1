param(
    [Parameter(Mandatory = $true)]
    [int]$ControlsFinalizerProcessId,
    [string]$ControlsStatsDir = "runs_maze_epsilon_controls_stats",
    [string]$RunsDir = "runs_maze_epsilon_sensitivity",
    [string]$CacheDir = "cache_maze_epsilon_sensitivity"
)

Set-Location (Split-Path -Parent $PSScriptRoot)
Wait-Process -Id $ControlsFinalizerProcessId -ErrorAction SilentlyContinue

if (-not (Test-Path (Join-Path $ControlsStatsDir "evidence_manifest.json"))) {
    throw "Epsilon controls finalization did not produce $ControlsStatsDir/evidence_manifest.json."
}

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

$pythonCommand = @(
    "python -m sec.run_maze_alpha",
    "--phase epsilon_sensitivity",
    "--model DeepSeek-V3",
    "--base-url https://api.modelarts-maas.com/v2",
    "--api-key-env MODELARTS_MAAS_KEY",
    "--seeds 0,1,2",
    "--T 6",
    "--train-batch 4",
    "--train-size 24",
    "--heldout-size 12",
    "--maze-width 15",
    "--maze-height 15",
    "--maze-family trap",
    "--maze-min-shortest 30",
    "--maze-agent-mode state_guided",
    "--max-steps 120",
    "--retrieval-k 6",
    "--library-cap 80",
    "--concurrency 8",
    "--skip-final-train",
    "--out-dir $RunsDir",
    "--cache-dir $CacheDir"
) -join " "

$command = @(
    $dotenvBootstrap,
    $pythonCommand
) -join [Environment]::NewLine

$run = Start-Process -FilePath powershell.exe -ArgumentList @("-NoProfile", "-EncodedCommand", (ConvertTo-EncodedPowerShellCommand $command)) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_sensitivity.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_sensitivity.stderr.log") `
    -PassThru

$finalizerCommand = "Set-Location `"$((Get-Location).Path)`"`n& .\scripts\finalize_epsilon_sensitivity.ps1 -RunProcessId $($run.Id)"
Start-Process -FilePath powershell.exe -ArgumentList @("-NoProfile", "-EncodedCommand", (ConvertTo-EncodedPowerShellCommand $finalizerCommand)) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_sensitivity_finalize.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_sensitivity_finalize.stderr.log") | Out-Null

[pscustomobject]@{
    sensitivity_run_pid = $run.Id
    controls_stats_dir = $ControlsStatsDir
    runs_dir = $RunsDir
} | Format-List
