param()

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Versions = Get-Content `
    -LiteralPath (Join-Path $Root "benchmarks\scbench\versions.json") `
    -Raw | ConvertFrom-Json
$RunnerPath = Join-Path $Root ".benchmarks\slop-code-bench"
$ProblemsPath = Join-Path $Root ".benchmarks\scb-problems"
$RunId = Get-Date -Format "yyyyMMdd_HHmmss"
$OutputPath = Join-Path $Root "runs_scbench_integration\$RunId"

foreach ($Item in @(
    @{ Path = $RunnerPath; Commit = $Versions.runner_commit },
    @{ Path = $ProblemsPath; Commit = $Versions.problems_commit }
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $Item.Path ".git"))) {
        throw "Missing checkout: $($Item.Path). Run scripts/setup_scbench.ps1 first."
    }
    $Actual = (git -C $Item.Path rev-parse HEAD).Trim()
    if ($Actual -ne $Item.Commit) {
        throw "Checkout mismatch at $($Item.Path): expected $($Item.Commit), got $Actual"
    }
}

docker image inspect $Versions.image | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Missing image $($Versions.image). Run scripts/setup_scbench.ps1 first."
}

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

docker run --rm `
    --env "SCBENCH_PROBLEMS_PATH=/problems" `
    --volume "${ProblemsPath}:/problems:ro" `
    $Versions.image `
    slop-code problems ls | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Problem catalog validation failed."
}

docker run --rm `
    --env "SCBENCH_PROBLEMS_PATH=/opt/scbench/tests/evaluation/fixtures/word_stats" `
    --volume "${OutputPath}:/outputs" `
    $Versions.image `
    slop-code eval-snapshot `
    /opt/scbench/tests/evaluation/fixtures/word_stats/submission `
    --save-dir /outputs/word_stats_checkpoint_1 `
    --problem-name problem `
    --checkpoint 1 `
    --env-config configs/environments/local-py.yaml `
    --json | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Reference checkpoint evaluation failed."
}

$EvaluationPath = Join-Path $OutputPath "word_stats_checkpoint_1\evaluation.json"
if (-not (Test-Path -LiteralPath $EvaluationPath)) {
    throw "Reference evaluation produced no evaluation.json."
}

$Evaluation = Get-Content -LiteralPath $EvaluationPath -Raw | ConvertFrom-Json
$CorePassed = [int]$Evaluation.pass_counts.Core
$CoreTotal = [int]$Evaluation.total_counts.Core
if (
    $Evaluation.infrastructure_failure `
    -or [int]$Evaluation.pytest_exit_code -ne 0 `
    -or $CoreTotal -le 0 `
    -or $CorePassed -ne $CoreTotal
) {
    throw (
        "Reference evaluation did not pass: " +
        "infrastructure_failure=$($Evaluation.infrastructure_failure), " +
        "pytest_exit_code=$($Evaluation.pytest_exit_code), " +
        "core=$CorePassed/$CoreTotal"
    )
}

Write-Host "SCBench verification passed."
Write-Host "Core tests: $CorePassed/$CoreTotal"
Write-Host "Artifacts: $OutputPath"
