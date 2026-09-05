$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$project = Split-Path -Parent $PSScriptRoot
$conceptPath = Join-Path $project "build\reference\concept_preview.jpg"
$parameters = Get-Content -LiteralPath (Join-Path $project 'config/parameters.json') -Raw | ConvertFrom-Json
if ($parameters.hybrid_new) { $conceptPath = Join-Path $project $parameters.appearance_candidate.source_image }
$currentPath = Join-Path $project "build\preview\orthographic.png"
$outputPath = Join-Path $project "build\preview\concept_comparison.jpg"

foreach ($required in @($conceptPath, $currentPath)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Comparison input not found: $required"
    }
}

function Draw-FitImage {
    param($Graphics, $Image, [float]$X, [float]$Y, [float]$Width, [float]$Height)
    $scale = [Math]::Min($Width / $Image.Width, $Height / $Image.Height)
    $drawWidth = $Image.Width * $scale
    $drawHeight = $Image.Height * $scale
    $drawX = $X + ($Width - $drawWidth) / 2
    $drawY = $Y + ($Height - $drawHeight) / 2
    $Graphics.DrawImage($Image, $drawX, $drawY, $drawWidth, $drawHeight)
}

$canvas = New-Object System.Drawing.Bitmap 1200, 650
$graphics = [System.Drawing.Graphics]::FromImage($canvas)
$graphics.Clear([System.Drawing.Color]::FromArgb(243, 241, 236))
$graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$titleFont = New-Object System.Drawing.Font "Segoe UI", 20, ([System.Drawing.FontStyle]::Bold)
$labelFont = New-Object System.Drawing.Font "Segoe UI", 17, ([System.Drawing.FontStyle]::Bold)
$textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(48, 52, 56))
$panelBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
$borderPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(185, 180, 170)), 2

$graphics.DrawString("Concept / current orthographic comparison", $titleFont, $textBrush, 24, 14)
$graphics.FillRectangle($panelBrush, 18, 60, 572, 570)
$graphics.DrawRectangle($borderPen, 18, 60, 572, 570)
$graphics.FillRectangle($panelBrush, 610, 60, 572, 570)
$graphics.DrawRectangle($borderPen, 610, 60, 572, 570)
$graphics.DrawString("SOURCE IMAGE", $labelFont, $textBrush, 36, 76)
$graphics.DrawString("SKELECAD $($parameters.project.revision)", $labelFont, $textBrush, 628, 76)

$concept = [System.Drawing.Image]::FromFile($conceptPath)
$current = [System.Drawing.Image]::FromFile($currentPath)
Draw-FitImage $graphics $concept 28 112 552 505
Draw-FitImage $graphics $current 620 112 552 505

$encoder = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
    Where-Object { $_.MimeType -eq "image/jpeg" }
$quality = New-Object System.Drawing.Imaging.EncoderParameter(
    [System.Drawing.Imaging.Encoder]::Quality, [long]78
)
$encoderParams = New-Object System.Drawing.Imaging.EncoderParameters 1
$encoderParams.Param[0] = $quality
$canvas.Save($outputPath, $encoder, $encoderParams)

$concept.Dispose()
$current.Dispose()
$encoderParams.Dispose()
$quality.Dispose()
$borderPen.Dispose()
$panelBrush.Dispose()
$textBrush.Dispose()
$labelFont.Dispose()
$titleFont.Dispose()
$graphics.Dispose()
$canvas.Dispose()
