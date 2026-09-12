# Read-only probe: never focuses windows, clicks controls, or sends print jobs.
[CmdletBinding()]
param(
    [string]$OutputPath,
    [ValidateRange(20, 2000)][int]$MaxNodes = 600
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$expectedPath = Join-Path $env:LOCALAPPDATA 'Programs/bambu-connect/Bambu Connect.exe'
$candidates = @(Get-Process | Where-Object {
    $_.ProcessName -eq 'Bambu Connect' -and
    $_.MainWindowHandle -ne 0 -and $_.Path -eq $expectedPath
})
if ($candidates.Count -ne 1) {
    throw "Expected one Bambu Connect window; found $($candidates.Count). Open Connect and retry."
}
$targetProcess = $candidates[0]
$root = [System.Windows.Automation.AutomationElement]::FromHandle($targetProcess.MainWindowHandle)
$walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
$pending = [System.Collections.Generic.Queue[object]]::new()
$pending.Enqueue(@{ Element = $root; Depth = 0 })
$nodes = [System.Collections.Generic.List[object]]::new()
$failures = [System.Collections.Generic.List[string]]::new()
$timer = [System.Diagnostics.Stopwatch]::StartNew()
while ($pending.Count -gt 0 -and $nodes.Count -lt $MaxNodes -and $timer.Elapsed.TotalSeconds -lt 15) {
    $item = $pending.Dequeue()
    try {
        $element = $item.Element
        $info = $element.Current
        # Password values and editable field values are deliberately not collected.
        if (-not $info.IsPassword) {
            $patterns = @($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
            $nodes.Add([ordered]@{
                depth = $item.Depth
                name = $info.Name
                type = $info.ControlType.ProgrammaticName
                automation_id = $info.AutomationId
                enabled = $info.IsEnabled
                offscreen = $info.IsOffscreen
                patterns = $patterns
            })
        }
        $child = $walker.GetFirstChild($element)
        while ($null -ne $child) {
            if (($pending.Count + $nodes.Count) -ge $MaxNodes -or $timer.Elapsed.TotalSeconds -ge 15) { break }
            $pending.Enqueue(@{ Element = $child; Depth = ($item.Depth + 1) })
            $child = $walker.GetNextSibling($child)
        }
    } catch {
        $failures.Add($_.Exception.GetType().FullName)
    }
}
$report = [ordered]@{
    captured_at = [DateTimeOffset]::Now.ToString('o')
    read_only = $true
    window_title = $targetProcess.MainWindowTitle
    process_id = $targetProcess.Id
    truncated = ($pending.Count -gt 0 -or $nodes.Count -ge $MaxNodes)
    errors = @($failures.ToArray())
    nodes = @($nodes.ToArray())
}
$json = $report | ConvertTo-Json -Depth 8
if ($OutputPath) {
    $resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($resolvedOutput)) | Out-Null
    [System.IO.File]::WriteAllText($resolvedOutput, $json, [System.Text.UTF8Encoding]::new($false))
}
$json
