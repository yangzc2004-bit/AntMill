param(
    [ValidateSet("Smoke", "Formal")]
    [string]$Mode = "Smoke",
    [string]$Tasks = "click-button,choose-list,enter-text,click-checkboxes,login-user,use-autocomplete-nodelay"
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

function Assert-Freeze {
    param([Parameter(Mandatory = $true)][string]$RecordPath)
    $record = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
    $document = if ($record.path) { $record.path } else { $record.document }
    if (-not $document) {
        throw "Freeze record has no document path: $RecordPath"
    }
    $actual = (Get-FileHash -LiteralPath $document -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne ([string]$record.sha256).ToLowerInvariant()) {
        throw "Preregistration hash does not match freeze record: $RecordPath"
    }
}

foreach ($record in @(
    "prereg_phase_gamma_p3_execution.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_01.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_02.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_03.freeze.json",
    "prereg_phase_gamma_p3_execution_amendment_04.freeze.json"
)) {
    Assert-Freeze -RecordPath $record
}

$runtime = Get-Content -LiteralPath "prereg_phase_gamma_p3_execution_amendment_04.freeze.json" -Raw |
    ConvertFrom-Json
Import-LocalEnvValue -Name "MODELARTS_MAAS_KEY"
$env:MINIWOB_URL = [string]$runtime.miniwob_url
$env:MINIWOB_BROWSER_EXECUTABLE = [string]$runtime.browser_executable
$env:MINIWOB_BROWSER_TREE_ROOT = Split-Path -Parent $env:MINIWOB_BROWSER_EXECUTABLE
$env:MINIWOB_BROWSER_EXPECTED_VERSION = [string]$runtime.browser_version
$env:MINIWOB_BROWSER_EXPECTED_SHA256 = [string]$runtime.browser_executable_sha256
$env:MINIWOB_BROWSER_EXPECTED_TREE_SHA256 = [string]$runtime.browser_tree_sha256

python -c "from sec.miniwob_gamma import validate_frozen_browser_runtime; r=validate_frozen_browser_runtime(); assert r['ok'], r"
if ($LASTEXITCODE -ne 0) {
    throw "Pinned MiniWoB browser runtime validation failed."
}

$common = @(
    "-m", "sec.miniwob_runner",
    "--tasks", $Tasks,
    "--model", "DeepSeek-V3",
    "--base-url", "https://api.modelarts-maas.com/v2",
    "--api-key-env", "MODELARTS_MAAS_KEY",
    "--max-steps", "15",
    "--episode-concurrency", "1",
    "--max-tokens-solver", "256",
    "--max-tokens-reviewer", "512"
)

if ($Mode -eq "Smoke") {
    $outDir = "runs_miniwob_gamma_p3e_smoke"
    $cacheDir = "cache_miniwob_gamma_p3e_smoke"
    $runArgs = $common + @(
        "--phase", "gamma_p3_smoke",
        "--out-dir", $outDir,
        "--cache-dir", $cacheDir,
        "--cache-policy", "off",
        "--seeds", "0",
        "--T", "1",
        "--heldout-size", "2",
        "--train-size", "2",
        "--train-batch", "2",
        "--concurrency", "8"
    )
} else {
    $smokeReport = "runs_miniwob_gamma_p3e_smoke_stats/p3_smoke_report.json"
    if (-not (Test-Path -LiteralPath $smokeReport)) {
        throw "P3e formal is unauthorized: missing $smokeReport"
    }
    $smoke = Get-Content -LiteralPath $smokeReport -Raw | ConvertFrom-Json
    if (
        $smoke.decision -ne "smoke_pass" -or
        @($smoke.runs).Count -ne 18 -or
        @($smoke.checks.PSObject.Properties | Where-Object { -not [bool]$_.Value }).Count -gt 0
    ) {
        throw "P3e formal is unauthorized: complete pinned-runtime smoke did not pass."
    }
    foreach ($record in @($smoke.source_results) + @($smoke.source_manifests)) {
        if (-not (Test-Path -LiteralPath $record.path)) {
            throw "P3e formal is unauthorized: missing smoke source $($record.path)"
        }
        $actualSourceHash = (
            Get-FileHash -LiteralPath $record.path -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        if ($actualSourceHash -ne ([string]$record.sha256).ToLowerInvariant()) {
            throw "P3e formal is unauthorized: smoke source hash changed for $($record.path)"
        }
    }
    $outDir = "runs_miniwob_gamma_p3e"
    $cacheDir = "cache_miniwob_gamma_p3e"
    $runArgs = $common + @(
        "--phase", "gamma_p3_formal",
        "--out-dir", $outDir,
        "--cache-dir", $cacheDir,
        "--cache-policy", "read_write",
        "--seeds", "0,1,2",
        "--T", "4",
        "--heldout-size", "12",
        "--train-size", "16",
        "--train-batch", "4",
        "--concurrency", "4",
        "--skip-final-train"
    )
}

if (Test-Path -LiteralPath $outDir) {
    $completed = @(
        Get-ChildItem -LiteralPath $outDir -Recurse -Filter result.json -ErrorAction SilentlyContinue
    ).Count
    if ($completed -gt 0) {
        throw "Fresh P3e directory already contains $completed completed results: $outDir"
    }
}

Write-Output "[$(Get-Date -Format o)] Starting Gamma P3e $Mode"
python @runArgs
if ($LASTEXITCODE -ne 0) {
    throw "Gamma P3e $Mode failed with exit code $LASTEXITCODE."
}
Write-Output "[$(Get-Date -Format o)] Gamma P3e $Mode complete"
