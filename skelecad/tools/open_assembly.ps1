param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
$freecad = Get-SkeleCADToolPath 'freecad'
$parameters = Get-Content -LiteralPath (Join-Path $project 'config/parameters.json') -Raw | ConvertFrom-Json
$assembly = Join-Path $project "$(Get-SkeleCADModelDirectory $parameters)/SkeleCAD_Hybrid_Assembly.FCStd"

if (-not (Test-Path -LiteralPath $assembly)) {
    throw "Assembly has not been generated. Run tools\build.ps1 first."
}

if (-not (Test-Path -LiteralPath $freecad -PathType Leaf)) { throw "FreeCAD not found: $freecad" }
if ($CheckOnly) { return [pscustomobject]@{ Application=$freecad; File=$assembly } }
Start-Process -FilePath $freecad -ArgumentList @('"' + $assembly + '"')
