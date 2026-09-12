# User-launched end-to-end preparation trial. Never clicks Send.
[CmdletBinding()]
param([switch]$ExecuteImportAndPrepare)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.runtime/connect-rpa-venv/Scripts/python.exe'
$job = Join-Path $project '.runtime/connect_test/SkeleCAD_Holding_R3_A1mini_connect_v2.gcode.3mf'
$profile = Join-Path $project 'config/connect_probe.example.json'
$script = Join-Path $PSScriptRoot 'connect_import_rpa.py'
$runName = 'rpa-import-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$resultDirectory = Join-Path $project ('.runtime/connect_test/' + $runName)
[System.IO.Directory]::CreateDirectory($resultDirectory) | Out-Null
$arguments = @('-X', 'utf8', $script, '--file', $job, '--expected', $profile, '--output', $resultDirectory)
if ($ExecuteImportAndPrepare) { $arguments += '--execute-import-and-prepare' }
& $python @arguments *> (Join-Path $resultDirectory 'trial.log')
exit $LASTEXITCODE
