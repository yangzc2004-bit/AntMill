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

$pythonCommand = @(
    "python -m sec.run_maze_alpha",
    "--phase epsilon_controls",
    "--model DeepSeek-V3",
    "--base-url https://api.modelarts-maas.com/v2",
    "--api-key-env MODELARTS_MAAS_KEY",
    "--seeds 0,1,2,3,4",
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
    "--reviewer-temp 0.2",
    "--tie-rule oldest_evicted_recency_retaining",
    "--skip-completed",
    "--out-dir runs_maze_epsilon_controls",
    "--cache-dir cache_maze_epsilon_controls"
) -join " "

$command = @(
    $dotenvBootstrap,
    $pythonCommand
) -join [Environment]::NewLine

$run = Start-Process -FilePath powershell.exe `
    -ArgumentList @("-NoProfile", "-EncodedCommand", (ConvertTo-EncodedPowerShellCommand $command)) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_controls.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_controls.stderr.log") `
    -PassThru

$finalizerCommand = "Set-Location `"$((Get-Location).Path)`"`n& .\scripts\finalize_epsilon_controls.ps1 -RunProcessId $($run.Id)"
$finalizer = Start-Process -FilePath powershell.exe `
    -ArgumentList @("-NoProfile", "-EncodedCommand", (ConvertTo-EncodedPowerShellCommand $finalizerCommand)) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/epsilon_finalize.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/epsilon_finalize.stderr.log") `
    -PassThru

[pscustomobject]@{
    epsilon_run_pid = $run.Id
    epsilon_finalizer_pid = $finalizer.Id
} | Format-List
