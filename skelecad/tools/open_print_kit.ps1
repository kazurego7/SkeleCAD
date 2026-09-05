param([switch]$CheckOnly)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')

$projectRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$slicer = Get-SkeleCADToolPath $SkeleCADTools.active_slicer
$parameters = Get-Content -LiteralPath (Join-Path $projectRoot 'config/parameters.json') -Raw | ConvertFrom-Json
$trialName = $parameters.hybrid_new.production_joint_profile.source_trial
if (-not $trialName) { throw "Current production_joint_profile.source_trial is required" }
    $trial = $parameters.$trialName
    if (-not $trial.output_directory) { throw "Unknown production fit trial: $trialName" }
    $printKit = Join-Path $projectRoot "$($trial.output_directory)/print/input.3mf"

if (-not (Test-Path -LiteralPath $slicer)) {
    throw "Configured slicer was not found at: $slicer"
}

if (-not (Test-Path -LiteralPath $printKit)) {
    throw "Fit kit not prepared: $printKit. Build the trial, then run its prepare/slice script."
}

if ($CheckOnly) { return [pscustomobject]@{ Application=$slicer; File=$printKit } }
Start-Process -FilePath $slicer -ArgumentList @('"' + $printKit + '"')
