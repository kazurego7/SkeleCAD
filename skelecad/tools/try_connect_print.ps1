# Explicit user-launched full print. Defaults to validating the delivery copy only.
[CmdletBinding()]
param([switch]$ExecutePrint)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.runtime/connect-rpa-venv/Scripts/python.exe'
$job = Join-Path $project '.runtime/connect_test/SkeleCAD_Holding_R3_A1mini_connect_v2.gcode.3mf'
$profile = Join-Path $project 'config/printer.local.json'
$script = Join-Path $PSScriptRoot 'connect_send_rpa.py'
$runName = 'rpa-print-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$resultDirectory = Join-Path $project ('.runtime/connect_test/' + $runName)
[System.IO.Directory]::CreateDirectory($resultDirectory) | Out-Null
$arguments = @('-X', 'utf8', $script, '--file', $job, '--expected', $profile, '--output', $resultDirectory)
if ($ExecutePrint) { $arguments += '--execute-print' }
& $python @arguments *> (Join-Path $resultDirectory 'trial.log')
exit $LASTEXITCODE
