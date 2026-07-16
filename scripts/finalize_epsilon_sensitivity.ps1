param(
    [Parameter(Mandatory = $true)]
    [int]$RunProcessId,
    [string]$RunsDir = "runs_maze_epsilon_sensitivity",
    [string]$OutDir = "runs_maze_epsilon_sensitivity_stats"
)

Set-Location (Split-Path -Parent $PSScriptRoot)
Wait-Process -Id $RunProcessId -ErrorAction SilentlyContinue

$resultCount = (Get-ChildItem -Path $RunsDir -Recurse -Filter result.json -ErrorAction SilentlyContinue | Measure-Object).Count
if ($resultCount -ne 27) {
    throw "Epsilon sensitivity suite is incomplete: expected 27 result.json files, found $resultCount."
}

python -m sec.epsilon_evidence --suite sensitivity --runs-dir $RunsDir --out-dir $OutDir --seeds 0,1,2
if ($LASTEXITCODE -ne 0) {
    throw "Epsilon sensitivity evidence generation failed."
}
