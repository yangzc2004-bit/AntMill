param(
    [Parameter(Mandatory = $true)]
    [int]$RunProcessId,
    [string]$RunsDir = "runs_maze_epsilon_controls",
    [string]$OutDir = "runs_maze_epsilon_controls_stats"
)

Set-Location (Split-Path -Parent $PSScriptRoot)
Wait-Process -Id $RunProcessId -ErrorAction SilentlyContinue

$resultCount = (Get-ChildItem -Path $RunsDir -Recurse -Filter result.json -ErrorAction SilentlyContinue | Measure-Object).Count
if ($resultCount -ne 30) {
    throw "Epsilon controls are incomplete: expected 30 result.json files, found $resultCount."
}

python -m sec.epsilon_evidence --suite controls --runs-dir $RunsDir --out-dir $OutDir --seeds 0,1,2,3,4
if ($LASTEXITCODE -ne 0) {
    throw "Epsilon controls evidence generation failed."
}
