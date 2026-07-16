param(
    [ValidateSet("Smoke", "Formal")]
    [string]$Mode = "Smoke",
    [Parameter(Mandatory = $true)]
    [string]$Tasks
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

function Set-MiniwobUrl {
    $existing = [Environment]::GetEnvironmentVariable("MINIWOB_URL", "Process")
    if ($existing) {
        return
    }
    $line = Get-Content -LiteralPath ".env" |
        Where-Object { $_ -match "^\s*MINIWOB_URL\s*=" } |
        Select-Object -First 1
    if ($line) {
        $value = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
        if ($value) {
            [Environment]::SetEnvironmentVariable("MINIWOB_URL", $value, "Process")
            return
        }
    }
    $root = Join-Path (Get-Location) "tmp/miniwob-plusplus/miniwob/html/miniwob"
    if (-not (Test-Path -LiteralPath $root)) {
        throw "MiniWoB runtime is missing. Run scripts/setup_gamma_p3_miniwob.ps1 first."
    }
    $uri = [System.Uri]::new((Resolve-Path -LiteralPath $root).Path + [IO.Path]::DirectorySeparatorChar).AbsoluteUri
    [Environment]::SetEnvironmentVariable("MINIWOB_URL", $uri, "Process")
}

function Set-MiniwobBrowserExecutable {
    $existing = [Environment]::GetEnvironmentVariable("MINIWOB_BROWSER_EXECUTABLE", "Process")
    if ($existing -and (Test-Path -LiteralPath $existing)) {
        return
    }
    $candidates = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    )
    $browser = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($browser) {
        [Environment]::SetEnvironmentVariable("MINIWOB_BROWSER_EXECUTABLE", $browser, "Process")
    }
}

function Assert-P3Freeze {
    $record = Get-Content -LiteralPath "prereg_phase_gamma_p3_execution.freeze.json" -Raw | ConvertFrom-Json
    $actual = (Get-FileHash -LiteralPath $record.path -Algorithm SHA256).Hash
    if ($actual -ne $record.sha256) {
        throw "P3 execution preregistration hash does not match its freeze record."
    }
}

function Invoke-Python {
    param([string[]]$CommandArgs)
    Write-Output "[$(Get-Date -Format o)] python $($CommandArgs -join ' ')"
    & python @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "python exited with code ${LASTEXITCODE}: $($CommandArgs -join ' ')"
    }
}

Assert-P3Freeze
Import-LocalEnvValue -Name "MODELARTS_MAAS_KEY"
Set-MiniwobUrl
Set-MiniwobBrowserExecutable

$taskCsv = $Tasks
$common = @(
    "-m", "sec.run_miniwob_gamma",
    "--tasks", $taskCsv,
    "--model", "DeepSeek-V3",
    "--base-url", "https://api.modelarts-maas.com/v2",
    "--api-key-env", "MODELARTS_MAAS_KEY",
    "--max-steps", "15",
    "--concurrency", "8",
    "--episode-concurrency", "2",
    "--max-tokens-solver", "256",
    "--max-tokens-reviewer", "512"
)

if ($Mode -eq "Smoke") {
    $outDir = "runs_miniwob_gamma_p3_smoke"
    $cacheDir = "cache_miniwob_gamma_p3_smoke"
    $phase = "gamma_p3_smoke"
    $runArgs = $common + @(
        "--phase", $phase,
        "--out-dir", $outDir,
        "--cache-dir", $cacheDir,
        "--cache-policy", "off",
        "--seeds", "0",
        "--T", "1",
        "--heldout-size", "2",
        "--train-size", "2",
        "--train-batch", "2"
    )
} else {
    $outDir = "runs_miniwob_gamma_p3"
    $cacheDir = "cache_miniwob_gamma_p3"
    $phase = "gamma_p3_formal"
    $runArgs = $common + @(
        "--phase", $phase,
        "--out-dir", $outDir,
        "--cache-dir", $cacheDir,
        "--seeds", "0,1,2",
        "--T", "4",
        "--heldout-size", "12",
        "--train-size", "16",
        "--train-batch", "4",
        "--skip-final-train"
    )
}

Write-Output "[$(Get-Date -Format o)] Starting Gamma P3 $Mode for $taskCsv"
Invoke-Python -CommandArgs $runArgs
Write-Output "[$(Get-Date -Format o)] Gamma P3 $Mode complete"
