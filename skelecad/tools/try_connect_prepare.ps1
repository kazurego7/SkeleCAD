# User-launched preparation trial. Never clicks Send.
[CmdletBinding()]
param([switch]$ExecuteOpenDialog)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.runtime/connect-rpa-venv/Scripts/python.exe'
$job = Join-Path $project '.runtime/connect_test/SkeleCAD_Holding_R3_A1mini_connect_v2.gcode.3mf'
$profile = Join-Path $project 'config/connect_probe.example.json'
$script = Join-Path $PSScriptRoot 'connect_prepare_rpa.py'
$runName = 'rpa-trial-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$resultDirectory = Join-Path $project ('.runtime/connect_test/' + $runName)
[System.IO.Directory]::CreateDirectory($resultDirectory) | Out-Null
$arguments = @('-X', 'utf8', $script, '--file', $job, '--expected', $profile, '--output', $resultDirectory)
if ($ExecuteOpenDialog) {
    # Allow the user to put Connect in front. We never activate or restore it.
    Start-Sleep -Seconds 10
    $arguments += '--execute-open-dialog'
}
& $python @arguments *> (Join-Path $resultDirectory 'trial.log')
exit $LASTEXITCODE
