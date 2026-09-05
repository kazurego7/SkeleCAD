param([switch]$Tailscale, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
. (Join-Path $PSScriptRoot 'toolchain_paths.ps1')
$python = Get-SkeleCADToolPath 'workflow_python'
$edgeCandidates = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$edge = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not (Test-Path -LiteralPath $python)) { throw "Portable Python not found: $python" }
if (-not $edge -and -not $NoBrowser) { throw "Microsoft Edge was not found" }

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
    Start-Process -FilePath $python -ArgumentList @(
        ('"' + $serverScript + '"'), "--port", "$selectedPort", "--bind", "127.0.0.1"
    ) -WorkingDirectory $project -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime "viewer.stdout.log") -RedirectStandardError (Join-Path $runtime "viewer.stderr.log")
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
    $tsCommand = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    $ts = if ($tsCommand) { $tsCommand.Source } else { "C:\Program Files\Tailscale\tailscale.exe" }
    if (-not (Test-Path -LiteralPath $ts)) { throw "Tailscale is not installed" }
    $status = & $ts status --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $status.BackendState -ne "Running") { throw "Connect Tailscale and sign in first" }
    $dnsName = $status.Self.DNSName.TrimEnd('.')
    $serve = & $ts serve status --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Cannot read Tailscale Serve settings" }
    $hostKey = "${dnsName}:443"
    $target = "http://127.0.0.1:$selectedPort"
    $existing = $serve.Web.$hostKey.Handlers.'/3dviewer'.Proxy
    $rootHandler = $serve.Web.$hostKey.Handlers.'/'
    if ($existing -and $existing -ne $target) { throw "The /3dviewer route already targets $existing; not overwriting it" }
    if ($rootHandler -and $rootHandler.Proxy -ne $target) { throw "The root route is already used by another service; not overwriting it" }
    if ($serve.AllowFunnel.$hostKey) { throw "Funnel is enabled on this host; refusing public exposure" }
    if (-not $existing) {
        & $ts serve --bg --https=443 --set-path=/3dviewer $target
        if ($LASTEXITCODE -ne 0) { throw "Tailscale Serve setup failed" }
    }
    # Also serve the host root: a slashless /3dviewer request resolves the
    # relative viewer redirect to /viewer/, outside the mounted path.
    if (-not $rootHandler) {
        & $ts serve --bg --https=443 --set-path=/ $target
        if ($LASTEXITCODE -ne 0) { throw "Tailscale root route setup failed" }
    }
    Write-Output "Tailscale: https://$dnsName/3dviewer/"
}
if (-not $NoBrowser) { Start-Process -FilePath $edge -ArgumentList "--app=$viewerUrl" }
