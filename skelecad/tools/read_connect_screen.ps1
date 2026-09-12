# Run with Windows PowerShell 5.1. Read-only capture and local Windows OCR.
[CmdletBinding()]
param(
    [string]$InputImage,
    [string]$OutputDirectory,
    [ValidateRange(1, 3)][int]$OcrScale = 2,
    [switch]$Invert,
    [switch]$Worker
)
$ErrorActionPreference = 'Stop'
function Invoke-ConnectOcr {
param([string]$InputImage, [string]$OutputDirectory, [ValidateRange(1,3)][int]$OcrScale = 2, [switch]$Invert, [switch]$CaptureOnly)
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot '../.runtime/connect_test/vision' }
if ($PSVersionTable.PSEdition -eq 'Core') { throw 'Run this tool with powershell.exe (Windows PowerShell 5.1).' }
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$outputDir = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($outputDir) | Out-Null
$captureTime = [DateTimeOffset]::Now.ToString('o')
$windowTitle = $null
$windowReference = $null
if (-not $InputImage) {
    $expectedPath = Join-Path $env:LOCALAPPDATA 'Programs/bambu-connect/Bambu Connect.exe'
    $targets = @(Get-Process -Name 'Bambu Connect' -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -eq 'Bambu Connect' -and $_.MainWindowHandle -ne 0 -and $_.Path -eq $expectedPath
    })
    if ($targets.Count -ne 1) { throw 'Open exactly one Bambu Connect window first.' }
    if (-not ('ConnectCapture' -as [type])) { Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ConnectCapture {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out Rect r);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
    }
    [ConnectCapture]::SetProcessDPIAware() | Out-Null
    $targetHandle = $targets[0].MainWindowHandle
    if ([ConnectCapture]::IsIconic($targetHandle) -or -not [ConnectCapture]::IsWindowVisible($targetHandle)) {
        throw 'Please restore Bambu Connect. This tool does not move or activate windows.'
    }
    $rect = New-Object ConnectCapture+Rect
    if (-not [ConnectCapture]::GetWindowRect($targetHandle, [ref]$rect)) { throw 'Cannot read window size.' }
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -lt 100 -or $height -lt 100 -or $width -gt 8000 -or $height -gt 8000) { throw 'Unexpected window size.' }
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $dc = $graphics.GetHdc()
    try { $ok = [ConnectCapture]::PrintWindow($targetHandle, $dc, 2) }
    finally { $graphics.ReleaseHdc($dc); $graphics.Dispose() }
    try {
        if (-not $ok) { throw 'Window capture failed. No desktop capture fallback is used.' }
        $InputImage = Join-Path $outputDir 'window.png'
        $bitmap.Save($InputImage, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $bitmap.Dispose() }
    $windowTitle = $targets[0].MainWindowTitle
    $windowReference = [ordered]@{
        handle = $targetHandle.ToInt64(); process_id = $targets[0].Id; executable = $targets[0].Path
        left = $rect.Left; top = $rect.Top; width = $width; height = $height
    }
}
$imagePath = (Resolve-Path -LiteralPath $InputImage).Path
$original = [System.Drawing.Bitmap]::FromFile($imagePath)
try {
    $originalWidth = $original.Width
    $originalHeight = $original.Height
    if ($CaptureOnly) {
        $report = [ordered]@{
            read_only=$true; captured_at=$captureTime; window_title=$windowTitle; window_reference=$windowReference
            image=$imagePath; width=$originalWidth; height=$originalHeight; capture_only=$true; lines=@()
        }
        $json = $report | ConvertTo-Json -Depth 8
        [System.IO.File]::WriteAllText((Join-Path $outputDir 'ocr.json'), $json, [System.Text.UTF8Encoding]::new($false))
        return $json
    }
    $scaled = New-Object System.Drawing.Bitmap(($originalWidth * $OcrScale), ($originalHeight * $OcrScale))
    $canvas = [System.Drawing.Graphics]::FromImage($scaled)
    try {
        $canvas.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        if ($Invert) {
            $attributes = New-Object System.Drawing.Imaging.ImageAttributes
            $matrix = New-Object System.Drawing.Imaging.ColorMatrix
            $matrix.Matrix00 = -1; $matrix.Matrix11 = -1; $matrix.Matrix22 = -1
            $matrix.Matrix40 = 1; $matrix.Matrix41 = 1; $matrix.Matrix42 = 1
            $attributes.SetColorMatrix($matrix)
            try {
                $destination = New-Object System.Drawing.Rectangle(0, 0, $scaled.Width, $scaled.Height)
                $canvas.DrawImage($original, $destination, 0, 0, $original.Width, $original.Height,
                    [System.Drawing.GraphicsUnit]::Pixel, $attributes)
            } finally { $attributes.Dispose() }
        } else { $canvas.DrawImage($original, 0, 0, $scaled.Width, $scaled.Height) }
        if ($Worker) {
            # Avoid PNG compression and disk round-trips for the enlarged OCR image.
            # The original capture and recognized words remain in the audit folder.
            $ocrBuffer = [System.IO.MemoryStream]::new()
            $scaled.Save($ocrBuffer, [System.Drawing.Imaging.ImageFormat]::Bmp)
            $ocrBuffer.Position = 0
        } else {
            $ocrImagePath = Join-Path $outputDir 'ocr-input.png'
            $scaled.Save($ocrImagePath, [System.Drawing.Imaging.ImageFormat]::Png)
        }
    } finally { $canvas.Dispose(); $scaled.Dispose() }
} finally { $original.Dispose() }

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and
    $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Wait-WinRT($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(15000)) { throw 'Windows OCR operation timed out.' }
    return $task.Result
}
if ($Worker) {
    $stream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($ocrBuffer)
} else {
    $file = Wait-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ocrImagePath)) ([Windows.Storage.StorageFile])
    $stream = Wait-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
}
$softwareBitmap = $null
try {
    $decoder = Wait-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $softwareBitmap = Wait-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    if ($null -eq $script:connectOcrEngine) {
        $script:connectOcrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
    }
    $engine = $script:connectOcrEngine
    if ($null -eq $engine) { throw 'Windows English OCR language support is not installed.' }
    $result = Wait-WinRT ($engine.RecognizeAsync($softwareBitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @($result.Lines | ForEach-Object {
        [ordered]@{ text = $_.Text; words = @($_.Words | ForEach-Object {
            [ordered]@{ text = $_.Text; x = ($_.BoundingRect.X / $OcrScale); y = ($_.BoundingRect.Y / $OcrScale);
                width = ($_.BoundingRect.Width / $OcrScale); height = ($_.BoundingRect.Height / $OcrScale) }
        }) }
    })
    $report = [ordered]@{
        read_only = $true; captured_at = $captureTime; window_title = $windowTitle; window_reference = $windowReference
        image = $imagePath; width = $originalWidth; height = $originalHeight; ocr_scale = $OcrScale; inverted = [bool]$Invert
        language = $engine.RecognizerLanguage.LanguageTag; lines = $lines
    }
    $json = $report | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText((Join-Path $outputDir 'ocr.json'), $json, [System.Text.UTF8Encoding]::new($false))
    $json
} finally {
    if ($null -ne $softwareBitmap) { $softwareBitmap.Dispose() }
    $stream.Dispose()
    if ($null -ne $ocrBuffer) { $ocrBuffer.Dispose() }
}
}

if ($Worker) {
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    while ($null -ne ($requestLine = [Console]::ReadLine())) {
        try {
            $request = $requestLine | ConvertFrom-Json
            $null = Invoke-ConnectOcr -InputImage $request.image -OutputDirectory $request.output -OcrScale $request.scale -CaptureOnly:([bool]$request.capture_only)
            [Console]::WriteLine('{"ok":true}')
        } catch {
            [Console]::WriteLine((@{ok=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress))
        }
    }
} else {
    Invoke-ConnectOcr -InputImage $InputImage -OutputDirectory $OutputDirectory -OcrScale $OcrScale -Invert:$Invert
}
