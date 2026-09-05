param([switch]$CheckOnly)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$orcaSlicer = Get-SkeleCADToolPath $SkeleCADTools.active_slicer
$printPlate = Join-Path $projectRoot "build\print\trex_full_print_plate.3mf"
$parameters = Get-Content -LiteralPath (Join-Path $projectRoot 'config/parameters.json') -Raw | ConvertFrom-Json
if ($parameters.hybrid_new) {
    $printPlate = Join-Path $projectRoot "$(Get-SkeleCADModelDirectory $parameters)/print/trex_hybrid_full_print_plate.3mf"
}

foreach ($required in @($orcaSlicer, $printPlate)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file not found: $required"
    }
}

if ($CheckOnly) { return [pscustomobject]@{ Application=$orcaSlicer; File=$printPlate } }
Start-Process -FilePath $orcaSlicer -ArgumentList @('"' + $printPlate + '"')
