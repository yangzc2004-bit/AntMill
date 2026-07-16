param(
    [string]$RunsDir = "runs_miniwob_gamma_p3e_smoke",
    [string]$OutDir = "runs_miniwob_gamma_p3e_smoke_stats"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$families = @(
    "click-button",
    "choose-list",
    "enter-text",
    "click-checkboxes",
    "login-user",
    "use-autocomplete-nodelay"
)
$arms = @(
    @{ Name = "frozen"; Suffix = "frozen_reviewer" },
    @{ Name = "append"; Suffix = "shared_append_ga" },
    @{ Name = "consolidated"; Suffix = "shared_consolidated_expel" }
)
$resultCount = @(
    Get-ChildItem -LiteralPath $RunsDir -Recurse -Filter result.json -ErrorAction SilentlyContinue
).Count
if ($resultCount -ne 18) {
    throw "P3e smoke matrix is incomplete: expected 18 results, found $resultCount."
}

$runArgs = @()
foreach ($family in $families) {
    foreach ($arm in $arms) {
        $directory = "n4_gt_false_seed0_gamma_p3_$($family.Replace('-', '_'))_$($arm.Suffix)"
        $path = Join-Path $RunsDir "$directory/result.json"
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Missing preregistered P3e smoke result: $path"
        }
        $runArgs += "--run"
        $runArgs += ("{0}:0:{1}={2}" -f $arm.Name, $family, $path)
    }
}

python -m sec.miniwob_stats smoke @runArgs --out-dir $OutDir
if ($LASTEXITCODE -ne 0) {
    throw "P3e smoke report generation failed."
}
$report = Get-Content -LiteralPath (Join-Path $OutDir "p3_smoke_report.json") -Raw |
    ConvertFrom-Json
if (
    $report.decision -ne "smoke_pass" -or
    @($report.runs).Count -ne 18 -or
    @($report.checks.PSObject.Properties | Where-Object { -not [bool]$_.Value }).Count -gt 0
) {
    throw "P3e smoke did not pass every frozen engineering and provenance check."
}
