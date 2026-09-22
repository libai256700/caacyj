param(
  [string]$Serial = '',
  [string]$AdbPath = 'adb'
)

$ErrorActionPreference = 'Stop'

function Invoke-Adb {
  param([string[]]$Arguments)
  & $AdbPath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "ADB command failed ($LASTEXITCODE): $($Arguments -join ' ')"
  }
}

if (-not $Serial) {
  $deviceLines = @(& $AdbPath devices) | Select-Object -Skip 1 | Where-Object {
    $_ -match '^\S+\s+device\s*$'
  }
  if ($deviceLines.Count -eq 1) {
    $Serial = ($deviceLines[0] -split '\s+')[0]
  } elseif ($deviceLines.Count -eq 0) {
    throw 'No Android device in device state. Connect the phone with ADB first.'
  } else {
    throw 'Multiple Android devices found. Pass -Serial explicitly.'
  }
}

$adbPrefix = @('-s', $Serial)
$remotePath = '/sdcard/codex-ui-tree.xml'
$dumpOutput = & $AdbPath @adbPrefix shell uiautomator dump $remotePath 2>&1
if ($LASTEXITCODE -ne 0) {
  throw "uiautomator dump failed: $dumpOutput"
}

$xmlText = (& $AdbPath @adbPrefix exec-out cat $remotePath) -join "`n"
if (-not $xmlText.Trim().StartsWith('<?xml')) {
  throw "uiautomator returned invalid XML: $xmlText"
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$reportDir = Join-Path (Join-Path $PSScriptRoot '..\reports\ui-tree') $timestamp
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$xmlPath = Join-Path $reportDir 'window.xml'
$csvPath = Join-Path $reportDir 'nodes.csv'
[IO.File]::WriteAllText($xmlPath, $xmlText, [Text.UTF8Encoding]::new($false))

[xml]$document = $xmlText
$nodes = @($document.hierarchy.node | ForEach-Object { $_.SelectNodes('.//node') })
$rows = @($nodes | ForEach-Object {
  [pscustomobject]@{
    ResourceId = $_.'resource-id'
    Text = $_.text
    ContentDesc = $_.'content-desc'
    Class = $_.class
    Bounds = $_.bounds
    Clickable = $_.clickable
    Enabled = $_.enabled
  }
} | Where-Object {
  $_.ResourceId -or $_.Text -or $_.ContentDesc -or $_.Clickable -eq 'true'
})
$rows | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8

Write-Host "Device: $Serial"
Write-Host "XML:    $xmlPath"
Write-Host "Table:  $csvPath"
$rows | Format-Table -AutoSize ResourceId, Text, ContentDesc, Class, Bounds, Clickable, Enabled
