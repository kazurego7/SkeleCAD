param([switch]$FitOnly)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
$toolchain = Get-Content (Join-Path $project 'config/toolchain.json') -Raw | ConvertFrom-Json
$exe = $toolchain.bambu_studio.executable
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$python = Get-SkeleCADToolPath 'workflow_python'
$parameters = Get-Content (Join-Path $project 'config/parameters.json') -Raw | ConvertFrom-Json
$revision = $parameters.project.revision
$output = New-Item -ItemType Directory -Force -Path (Join-Path $project "build/print_ready/bambu_$revision")
$jobs = if ($FitOnly) { @('fit_kit') } else { @('fit_kit','120mm') }
foreach ($job in $jobs) {
    $layoutArgs = @((Join-Path $project 'tools/prepare_palm_print.py'))
    if ($job -eq 'fit_kit') { $layoutArgs += '--fit' }
    & $python @layoutArgs
    if ($LASTEXITCODE -ne 0) { throw "Bambu layout preparation failed: $job" }
    $prepareArgs = @((Join-Path $project 'tools/prepare_bambu_print.py'))
    if ($job -eq 'fit_kit') { $prepareArgs += '--fit' }
    & $python @prepareArgs
    if ($LASTEXITCODE -ne 0) { throw "Bambu preparation failed: $job" }
    $inputFile = Join-Path $output.FullName "input/$job.3mf"
    $jobOutput = New-Item -ItemType Directory -Force -Path (Join-Path $output.FullName $job)
    $name = "SkeleCAD_${revision}_${job}_BambuStudio_A1mini.3mf"
    $sliceArgs = @('--slice','1','--arrange','0','--orient','0','--outputdir',('"'+$jobOutput.FullName+'"'),
        '--export-3mf',$name,('"'+$inputFile+'"'))
    $process = Start-Process -FilePath $exe -ArgumentList $sliceArgs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Bambu CLI failed: $job exit $($process.ExitCode)" }
    $package=Join-Path $jobOutput.FullName $name
    if (-not (Test-Path -LiteralPath $package)) { throw "Bambu did not produce $package" }
    Write-Host "SLICED: $package"
}
