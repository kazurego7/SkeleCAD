param([switch]$NoBrowser, [switch]$SetupOnly, [switch]$Tailscale)
$ErrorActionPreference = 'Stop'
$workspace = $PSScriptRoot
$uvCommand = Get-Command uv.exe -ErrorAction SilentlyContinue
$uv = if ($uvCommand) { $uvCommand.Source } else { Join-Path $workspace '.tools/uv/uv.exe' }
if (-not (Test-Path -LiteralPath $uv)) {
    $folder = Join-Path $workspace '.tools/uv'
    New-Item -ItemType Directory -Force $folder | Out-Null
    $archive = Join-Path $folder 'uv.zip'
    $url = 'https://github.com/astral-sh/uv/releases/download/0.12.9/uv-x86_64-pc-windows-msvc.zip'
    Write-Host 'Downloading the Python environment manager...'
    Invoke-WebRequest -UseBasicParsing $url -OutFile $archive
    $expected = 'ddbfcee1ac615a0499f6aa97b5ec8ebdf3ee4a7714a48055ec2ba0030e3cf810'
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'uv download checksum mismatch' }
    Expand-Archive -LiteralPath $archive -DestinationPath $folder -Force
}
$config = Get-Content -LiteralPath (Join-Path $workspace 'skelecad/config/toolchain.json') -Raw | ConvertFrom-Json
& $uv run --no-project --python $config.workflow_python.version (Join-Path $workspace 'skelecad/tools/setup_runtime.py') --uv $uv
if ($LASTEXITCODE -ne 0) { throw 'Setup failed. Correct the reported problem, then run this command again.' }
if (-not $SetupOnly) { & (Join-Path $workspace 'skelecad/tools/open_3d_viewer.ps1') -NoBrowser:$NoBrowser -Tailscale:$Tailscale }
