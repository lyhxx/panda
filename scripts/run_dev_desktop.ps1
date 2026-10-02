[CmdletBinding()]
param(
    [string]$QtRoot = "",
    [string]$BuildDirectory = "build/windows-msvc-desktop",
    [switch]$Wait
)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

if ([string]::IsNullOrWhiteSpace($QtRoot)) {
    $QtRoot = Join-Path $repoRoot "..\.tools\Qt\6.8.3\msvc2022_64"
}
$QtRoot = (Resolve-Path -LiteralPath $QtRoot).Path
$executable = Join-Path `
    $repoRoot `
    "$BuildDirectory\desktop\Release\panda_desktop.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Development desktop executable was not found: $executable"
}

$python = Join-Path `
    $repoRoot `
    "..\.tools\miniforge3\envs\meanvc2-cpu\python.exe"
$meanvc2 = Join-Path $repoRoot "..\deps\MeanVC2"
$voices = Join-Path $repoRoot "dist\Panda\voices"

$env:PATH = (Join-Path $QtRoot "bin") + [IO.Path]::PathSeparator + $env:PATH
$env:PANDA_PYTHON = $python
$env:PANDA_MEANVC2_ROOT = $meanvc2
$env:PANDA_VOICES_ROOT = $voices

if (-not (Test-Path -LiteralPath $voices -PathType Container)) {
    New-Item -ItemType Directory -Path $voices -Force | Out-Null
}

Write-Host "Starting Panda development build"
Write-Host "Qt:     $QtRoot"
Write-Host "Python: $python"
Write-Host "Voices: $voices"

if ($Wait) {
    & $executable
}
else {
    Start-Process `
        -FilePath $executable `
        -WorkingDirectory (Split-Path -Parent $executable)
}
