$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$commit = "7fd85d71a4b60325c6585396ec4f48377d049838"
$repo = Join-Path (Get-Location) "tmp/miniwob-plusplus"

if (-not (Test-Path -LiteralPath $repo)) {
    Write-Output "[$(Get-Date -Format o)] Cloning MiniWoB++ runtime"
    & git clone https://github.com/Farama-Foundation/miniwob-plusplus.git $repo
    if ($LASTEXITCODE -ne 0) {
        throw "MiniWoB++ clone failed"
    }
}

Write-Output "[$(Get-Date -Format o)] Checking out MiniWoB++ $commit"
& git -C $repo checkout --detach $commit
if ($LASTEXITCODE -ne 0) {
    throw "MiniWoB++ commit checkout failed"
}
$resolved = (Resolve-Path -LiteralPath (Join-Path $repo "miniwob/html/miniwob")).Path
if (-not (Test-Path -LiteralPath $resolved)) {
    throw "MiniWoB++ HTML task directory is missing: $resolved"
}

$browserExecutable = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($browserExecutable) {
    Write-Output "[$(Get-Date -Format o)] Using installed browser $browserExecutable"
} else {
    Write-Output "[$(Get-Date -Format o)] Installing Playwright Chromium"
    & python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) {
        throw "Playwright Chromium installation failed"
    }
}

$url = [System.Uri]::new($resolved + [IO.Path]::DirectorySeparatorChar).AbsoluteUri
$manifestDir = Join-Path (Get-Location) "tmp/miniwob-runtime"
New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
@{
    miniwob_plusplus_commit = $commit
    repo = $repo
    miniwob_url = $url
    browser_executable = $browserExecutable
    created_at = (Get-Date -Format o)
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $manifestDir "setup_manifest.json") -Encoding utf8
Write-Output "MINIWOB_URL=$url"
