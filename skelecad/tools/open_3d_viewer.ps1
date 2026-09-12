param([switch]$Tailscale, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
$networkPreference = Join-Path $project '.runtime/viewer-network.json'
if (-not $Tailscale -and (Test-Path -LiteralPath $networkPreference)) {
    $Tailscale = [bool](Get-Content -LiteralPath $networkPreference -Raw | ConvertFrom-Json).tailscale
}
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$python = Get-SkeleCADToolPath 'workflow_python'
$edgeCandidates = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$edge = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not (Test-Path -LiteralPath $python)) { throw "Portable Python not found: $python" }
if (-not $edge -and -not $NoBrowser) { throw "Microsoft Edge was not found" }
$dnsName = $null
if ($Tailscale) {
    $tsCommand = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    $ts = if ($tsCommand) { $tsCommand.Source } else { "C:\Program Files\Tailscale\tailscale.exe" }
    if (-not (Test-Path -LiteralPath $ts)) { throw "Tailscale is not installed" }
    $status = & $ts status --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $status.BackendState -ne "Running") { throw "Connect Tailscale and sign in first" }
    $dnsName = $status.Self.DNSName.TrimEnd('.')
}

$selectedPort = $null
foreach ($candidatePort in 8765..8774) {
    try {
        $probe = Invoke-RestMethod -Uri "http://127.0.0.1:$candidatePort/healthz" -TimeoutSec 1
        if ($probe.app -eq "skelecad-viewer") { $selectedPort = $candidatePort; break }
    } catch {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $candidatePort)
        try { $listener.Start(); $selectedPort = $candidatePort; break } catch {} finally { $listener.Stop() }
    }
}
if ($null -eq $selectedPort) { throw "No local viewer port is available" }

$viewerUrl = "http://127.0.0.1:$selectedPort/viewer/"
$alreadyRunning = $false
try {
    $probe = Invoke-RestMethod -Uri "http://127.0.0.1:$selectedPort/healthz" -TimeoutSec 1
    $alreadyRunning = $probe.app -eq "skelecad-viewer"
} catch {}

if (-not $alreadyRunning) {
    $runtime = Join-Path $project ".runtime"
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $serverScript = Join-Path $PSScriptRoot "viewer_server.py"
    $serverArguments = @(
        ('"' + $serverScript + '"'), "--port", "$selectedPort", "--bind", "127.0.0.1"
    )
    if ($dnsName) { $serverArguments += @('--tailscale-host', $dnsName) }
    Start-Process -FilePath $python -ArgumentList $serverArguments -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime "viewer.stdout.log") -RedirectStandardError (Join-Path $runtime "viewer.stderr.log")
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $probe = Invoke-RestMethod -Uri "http://127.0.0.1:$selectedPort/healthz" -TimeoutSec 1
            if ($probe.app -eq "skelecad-viewer") { $ready = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw "Local 3D viewer did not start" }
}

Write-Output "Local: $viewerUrl"
if ($Tailscale) {
    if ($probe.version -lt 2 -or $probe.tailscale_host -ne $dnsName) {
        throw "The running viewer needs to be restarted with -Tailscale after active modelling jobs finish."
    }
    $serve = & $ts serve status --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Cannot read Tailscale Serve settings" }
    $hostKey = "${dnsName}:443"
    $localTarget = "http://127.0.0.1:$selectedPort"
    $target = "$localTarget/skelecad"
    $existing = $serve.Web.$hostKey.Handlers.'/skelecad'
    $legacy = $serve.Web.$hostKey.Handlers.'/3dviewer'
    $rootHandler = $serve.Web.$hostKey.Handlers.'/'
    if ($existing -and $existing.Proxy -ne $target) { throw "The /skelecad route is already used by another service; not overwriting it" }
    if ($serve.AllowFunnel.$hostKey) { throw "Funnel is enabled on this host; refusing public exposure" }
    if (-not $existing) {
        & $ts serve --bg --https=443 --set-path=/skelecad $target
        if ($LASTEXITCODE -ne 0) { throw "Tailscale Serve setup failed" }
    }
    if ($legacy.Proxy -eq $localTarget) {
        & $ts serve --bg --https=443 --set-path=/3dviewer off
        if ($LASTEXITCODE -ne 0) { throw "Could not remove the old viewer route" }
    }
    # Remove only this viewer's former root workaround; preserve other apps.
    if ($rootHandler.Proxy -eq $localTarget) {
        & $ts serve --bg --https=443 --set-path=/ off
        if ($LASTEXITCODE -ne 0) { throw "Could not remove the old viewer root route" }
    }
    '{"tailscale":true}' | Set-Content -LiteralPath $networkPreference -Encoding utf8
    Write-Output "Tailscale: https://$dnsName/skelecad/"
}
if (-not $NoBrowser) { Start-Process -FilePath $edge -ArgumentList "--app=$viewerUrl" }
