param(
    [Parameter(Mandatory = $true)]
    [int]$RunProcessId,
    [string]$RunsDir = "runs_miniwob_gamma_p3e",
    [string]$OutDir = "runs_miniwob_gamma_p3e_stats"
)

Set-Location (Split-Path -Parent $PSScriptRoot)
Wait-Process -Id $RunProcessId -ErrorAction SilentlyContinue

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
$resultCount = (Get-ChildItem -Path $RunsDir -Recurse -Filter result.json -ErrorAction SilentlyContinue | Measure-Object).Count
if ($resultCount -ne 54) {
    throw "P3 formal matrix is incomplete: expected 54 result.json files, found $resultCount."
}

$runArgs = @()
foreach ($family in $families) {
    foreach ($seed in 0, 1, 2) {
        foreach ($arm in $arms) {
            $directory = "n4_gt_false_seed${seed}_gamma_p3_$($family.Replace('-', '_'))_$($arm.Suffix)"
            $path = Join-Path $RunsDir "$directory/result.json"
            if (-not (Test-Path $path)) {
                throw "Missing preregistered P3 result: $path"
            }
            $runArgs += "--run"
            $runArgs += ("{0}:{1}:{2}={3}" -f $arm.Name, $seed, $family, $path)
        }
    }
}

python -m sec.miniwob_stats gate @runArgs --intervention consolidated --baseline frozen --out-dir $OutDir --t 3
if ($LASTEXITCODE -ne 0) {
    throw "P3 consolidated gate generation failed."
}
$primary = Get-Content -LiteralPath (Join-Path $OutDir "p3_gate_report.json") -Raw |
    ConvertFrom-Json
if ($primary.formal_data_quality.status -ne "quality_clear") {
    Write-Warning (
        "P3 consolidated formal quality is not clear; the report is retained " +
        "with behavioral interpretation withheld."
    )
}
python -m sec.miniwob_stats gate @runArgs --intervention append --baseline frozen --out-dir (Join-Path $OutDir "append_secondary") --t 3
if ($LASTEXITCODE -ne 0) {
    throw "P3 append-secondary gate generation failed."
}
$secondary = Get-Content -LiteralPath (Join-Path $OutDir "append_secondary/p3_gate_report.json") -Raw |
    ConvertFrom-Json
if ($secondary.formal_data_quality.status -ne "quality_clear") {
    Write-Warning (
        "P3 append-secondary formal quality is not clear; the report is retained " +
        "with behavioral interpretation withheld."
    )
}
python -m sec.miniwob_stats latency-summary @runArgs --out-dir $OutDir
if ($LASTEXITCODE -ne 0) {
    throw "P3 latency summary generation failed."
}
