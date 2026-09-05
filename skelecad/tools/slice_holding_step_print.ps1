$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
$workspace=Split-Path -Parent $project
$parameters=Get-Content (Join-Path $project 'config/parameters.json') -Raw | ConvertFrom-Json
$toolchain=Get-Content (Join-Path $project 'config/toolchain.json') -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$python = Get-SkeleCADToolPath 'workflow_python'
& $python (Join-Path $project 'tools/prepare_holding_step_print.py')
if ($LASTEXITCODE -ne 0) { throw 'Holding step print preparation failed' }
$out=Join-Path (Join-Path $project $parameters.joint_holding_step_trial.output_directory) 'print'
$inputFile=Join-Path $out 'input.3mf'
$argsList=@('--slice','1','--arrange','0','--orient','0','--outputdir',('"'+$out+'"'),
            '--export-3mf','SkeleCAD_Holding_R3_A1mini_PLA_Matte.3mf',('"'+$inputFile+'"'))
$process=Start-Process -FilePath $toolchain.bambu_studio.executable -ArgumentList $argsList -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $out 'cli_stdout.log') -RedirectStandardError (Join-Path $out 'cli_stderr.log')
if ($process.ExitCode -ne 0) { throw "Bambu CLI failed: $($process.ExitCode)" }
& $python (Join-Path $project 'tools/audit_holding_step_print.py')
if ($LASTEXITCODE -ne 0) { throw 'Holding step print release audit failed' }
Write-Host (Join-Path $out 'SkeleCAD_Holding_R3_A1mini_PLA_Matte.3mf')
