$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$reviewImage = Join-Path $projectRoot "build\review\current\assembly.png"
$reviewSummary = Join-Path $projectRoot "build\review\current\summary.md"

foreach ($required in @($reviewImage, $reviewSummary)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Review file was not found. Run tools\build.ps1 first: $required"
    }
}

Start-Process -FilePath $reviewImage
Start-Process -FilePath $reviewSummary
