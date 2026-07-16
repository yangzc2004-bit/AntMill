param()

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VersionsPath = Join-Path $Root "benchmarks\scbench\versions.json"
$Versions = Get-Content -LiteralPath $VersionsPath -Raw | ConvertFrom-Json
$BenchmarksRoot = Join-Path $Root ".benchmarks"
$RunnerPath = Join-Path $BenchmarksRoot "slop-code-bench"
$ProblemsPath = Join-Path $BenchmarksRoot "scb-problems"

New-Item -ItemType Directory -Force -Path $BenchmarksRoot | Out-Null

function Ensure-PinnedCheckout {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$Commit,
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path -LiteralPath (Join-Path $Path ".git"))) {
        git clone $Repository $Path
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to clone $Repository"
        }
    }

    $Current = (git -C $Path rev-parse HEAD).Trim()
    if ($Current -ne $Commit) {
        git -C $Path fetch --depth 1 origin $Commit
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to fetch pinned commit $Commit"
        }
        git -C $Path switch --detach $Commit
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to switch $Path to pinned commit $Commit"
        }
    }

    $Resolved = (git -C $Path rev-parse HEAD).Trim()
    if ($Resolved -ne $Commit) {
        throw "Pinned checkout mismatch for $Path`: expected $Commit, got $Resolved"
    }
}

Ensure-PinnedCheckout `
    -Repository $Versions.runner_repository `
    -Commit $Versions.runner_commit `
    -Path $RunnerPath
Ensure-PinnedCheckout `
    -Repository $Versions.problems_repository `
    -Commit $Versions.problems_commit `
    -Path $ProblemsPath

docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running."
}

$Dockerfile = Join-Path $Root "benchmarks\scbench\Dockerfile"
$BuildContext = Join-Path $Root "benchmarks\scbench"
docker build `
    --build-arg "SCBENCH_COMMIT=$($Versions.runner_commit)" `
    --tag $Versions.image `
    --file $Dockerfile `
    $BuildContext
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build $($Versions.image)"
}

Write-Host "SCBench runner ready: $($Versions.image)"
Write-Host "Runner commit: $($Versions.runner_commit)"
Write-Host "Problems commit: $($Versions.problems_commit)"
