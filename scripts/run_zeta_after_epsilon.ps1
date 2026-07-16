param(
    [int]$PollSeconds = 60,
    [string]$SensitivityManifest = "runs_maze_epsilon_sensitivity_stats/evidence_manifest.json",
    [string]$SchedulePath = "runs_maze_zeta_schedule/zeta_schedule.json",
    [string]$RunsDir = "runs_maze_zeta_exact_yoke",
    [string]$CacheDir = "cache_maze_zeta_exact_yoke",
    [string]$StatsDir = "runs_maze_zeta_exact_yoke_stats"
)

Set-Location (Split-Path -Parent $PSScriptRoot)

while (-not (Test-Path -LiteralPath $SensitivityManifest)) {
    Start-Sleep -Seconds $PollSeconds
}

python -m sec.epsilon_yoke extract `
    --controls-dir runs_maze_epsilon_controls `
    --out $SchedulePath
if ($LASTEXITCODE -ne 0) {
    throw "Phase Zeta schedule extraction failed."
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

$runner = @(
    "python -m sec.epsilon_yoke run",
    "--schedule-json $SchedulePath",
    "--",
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
    "--out-dir $RunsDir",
    "--cache-dir $CacheDir"
) -join " "
$command = @($dotenvBootstrap, $runner) -join [Environment]::NewLine
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$run = Start-Process -FilePath powershell.exe `
    -ArgumentList @("-NoProfile", "-EncodedCommand", $encoded) `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path (Get-Location) "logs/zeta_exact_yoke.stdout.log") `
    -RedirectStandardError (Join-Path (Get-Location) "logs/zeta_exact_yoke.stderr.log") `
    -PassThru

Wait-Process -Id $run.Id -ErrorAction SilentlyContinue
$resultCount = (Get-ChildItem -Path $RunsDir -Recurse -Filter result.json -ErrorAction SilentlyContinue | Measure-Object).Count
if ($resultCount -ne 5) {
    throw "Phase Zeta is incomplete: expected 5 result.json files, found $resultCount."
}

python -m sec.zeta_evidence `
    --controls-dir runs_maze_epsilon_controls `
    --zeta-dir $RunsDir `
    --schedule-json $SchedulePath `
    --out-dir $StatsDir
if ($LASTEXITCODE -ne 0) {
    throw "Phase Zeta evidence generation failed."
}
