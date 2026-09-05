# Shared paths; resolve tool versions from config instead of launcher literals.
$SkeleCADProject = Split-Path -Parent $PSScriptRoot
$SkeleCADWorkspace = Split-Path -Parent $SkeleCADProject
$SkeleCADTools = Get-Content -LiteralPath (Join-Path $SkeleCADProject 'config/toolchain.json') -Raw | ConvertFrom-Json
$localConfig = Join-Path $SkeleCADProject 'config/toolchain.local.json'
if (Test-Path -LiteralPath $localConfig) {
    $localTools = Get-Content -LiteralPath $localConfig -Raw | ConvertFrom-Json
    foreach ($tool in $localTools.PSObject.Properties) {
        foreach ($field in $tool.Value.PSObject.Properties) {
            $SkeleCADTools.($tool.Name) | Add-Member -NotePropertyName $field.Name -NotePropertyValue $field.Value -Force
        }
    }
}
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
    throw "Current model configuration hybrid_new is required"
}
