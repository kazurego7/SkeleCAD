param([switch]$FitOnly, [switch]$LegacyOrca)
$ErrorActionPreference = 'Stop'
if (-not $LegacyOrca) {
    & (Join-Path $PSScriptRoot 'slice_bambu_print.ps1') -FitOnly:$FitOnly
    return
}
$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
$exe = Join-Path $workspace '.tools/orcaslicer-2.4.2/orca-slicer.exe'
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$python = Get-SkeleCADToolPath 'workflow_python'
$parameters = Get-Content (Join-Path $project 'config/parameters.json') -Raw | ConvertFrom-Json
if (-not $parameters.printing.production_profile.plate_confirmed) { throw 'Plate confirmation required' }
$revision = $parameters.project.revision
$output = New-Item -ItemType Directory -Force -Path (Join-Path $project "build/print_ready/sliced_$revision")
$jobs = if ($FitOnly) { @('fit_kit') } else { @('fit_kit','120mm') }
foreach ($job in $jobs) {
    $prepareArgs = @((Join-Path $project 'tools/prepare_palm_print.py'))
    if ($job -eq 'fit_kit') { $prepareArgs += '--fit' }
    & $python @prepareArgs
    if ($LASTEXITCODE -ne 0) { throw "Preparation failed: $job" }
    $base = "SkeleCAD_${revision}_${job}_A1mini_BambuMatte_TexturedPEI"
    $inputFile = Join-Path $project "build/print_ready/$base.3mf"
    $jobOutput = New-Item -ItemType Directory -Force -Path (Join-Path $output.FullName $job)
    $argsForSlice = @('--slice','1','--arrange','0','--orient','0',
        '--outputdir',('"'+$jobOutput.FullName+'"'),
        '--export-3mf',($base+'.gcode.3mf'),('"'+$inputFile+'"'))
    # No GUI interaction, printer connection or print-start option is used.
    $process = Start-Process -FilePath $exe -ArgumentList $argsForSlice -WindowStyle Hidden -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "Orca slicing failed: $job exit $($process.ExitCode)" }
    $package = Join-Path $jobOutput.FullName ($base+'.gcode.3mf')
    if (-not (Test-Path -LiteralPath $package)) { throw "No sliced package: $job" }
    Write-Host "SLICED: $package"
}
