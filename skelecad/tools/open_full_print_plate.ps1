param([switch]$CheckOnly)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$slicer = Get-SkeleCADToolPath $SkeleCADTools.active_slicer
$parameters = Get-Content -LiteralPath (Join-Path $projectRoot 'config/parameters.json') -Raw | ConvertFrom-Json
$printPlate = Join-Path $projectRoot "$(Get-SkeleCADModelDirectory $parameters)/print/trex_hybrid_full_print_plate.3mf"

foreach ($required in @($slicer, $printPlate)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required file not found: $required"
    }
}

if ($CheckOnly) { return [pscustomobject]@{ Application=$slicer; File=$printPlate } }
Start-Process -FilePath $slicer -ArgumentList @('"' + $printPlate + '"')
