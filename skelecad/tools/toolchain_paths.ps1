# Shared paths; resolve tool versions from config instead of launcher literals.
$SkeleCADProject = Split-Path -Parent $PSScriptRoot
$SkeleCADWorkspace = Split-Path -Parent $SkeleCADProject
$SkeleCADTools = Get-Content -LiteralPath (Join-Path $SkeleCADProject 'config/toolchain.json') -Raw | ConvertFrom-Json
function Get-SkeleCADToolPath {
    param([string]$Tool, [string]$Field = 'executable')
    $value = $SkeleCADTools.$Tool.$Field
    if (-not $value) { throw "Missing toolchain path: $Tool.$Field" }
    if ([IO.Path]::IsPathRooted($value)) { return $value }
    return Join-Path $SkeleCADWorkspace $value
}
function Get-SkeleCADModelDirectory {
    param($Parameters)
    if ($Parameters.hybrid_new.palm_size.enabled) { return $Parameters.hybrid_new.palm_size.output_directory }
    if ($Parameters.hybrid_new) { return $Parameters.hybrid_new.output_directory }
    return $Parameters.hybrid.output_directory
}
