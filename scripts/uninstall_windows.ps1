[CmdletBinding()]
param(
    [string]$InstallDirectory = "",
    [switch]$RemoveVoices
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $env:LOCALAPPDATA "Panda"
}
$installRoot = [IO.Path]::GetFullPath($InstallDirectory)
$infoPath = Join-Path $installRoot "install.json"
if (-not (Test-Path -LiteralPath $infoPath -PathType Leaf)) {
    throw "Panda installation metadata was not found: $infoPath"
}

$info = Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json
$voiceRoot = [IO.Path]::GetFullPath([string]$info.voice_directory)

$startMenu = Join-Path `
    $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Panda"
if (Test-Path -LiteralPath $startMenu) {
    Remove-Item -LiteralPath $startMenu -Recurse -Force
}

Remove-Item -LiteralPath $installRoot -Recurse -Force
if ($RemoveVoices -and (Test-Path -LiteralPath $voiceRoot)) {
    Remove-Item -LiteralPath $voiceRoot -Recurse -Force
}

Write-Host "Panda was uninstalled."
if (-not $RemoveVoices) {
    Write-Host "Voice packs were preserved at $voiceRoot"
}
