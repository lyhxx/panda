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
$voiceRoot = if (-not [string]::IsNullOrWhiteSpace([string]$info.voice_directory)) {
    [IO.Path]::GetFullPath([string]$info.voice_directory)
}
else {
    Join-Path $installRoot "voices"
}

$startMenu = Join-Path `
    $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Panda"
if (Test-Path -LiteralPath $startMenu) {
    Remove-Item -LiteralPath $startMenu -Recurse -Force
}

if ($RemoveVoices) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}
else {
    # Keep the voice library. By default it lives INSIDE the install root
    # (installRoot\voices), so removing the root wholesale would delete it
    # too -- which is exactly what happened before, while printing that the
    # packs had been preserved. Delete every entry except the voice subtree.
    $resolvedVoices = [IO.Path]::GetFullPath($voiceRoot).TrimEnd('\')
    $resolvedRoot = [IO.Path]::GetFullPath($installRoot).TrimEnd('\')
    if ($resolvedVoices -eq $resolvedRoot) {
        throw (
            "Voice directory equals the install root ($voiceRoot). " +
            "Re-run with -RemoveVoices to remove everything."
        )
    }
    Get-ChildItem -LiteralPath $installRoot -Force | ForEach-Object {
        $candidate = [IO.Path]::GetFullPath($_.FullName).TrimEnd('\')
        $isVoice = $candidate -eq $resolvedVoices -or
            $candidate.StartsWith(
                $resolvedVoices + [IO.Path]::DirectorySeparatorChar,
                [StringComparison]::OrdinalIgnoreCase
            )
        if (-not $isVoice) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }
}

Write-Host "Panda was uninstalled."
if (-not $RemoveVoices) {
    Write-Host "Voice packs were preserved at $voiceRoot"
}
