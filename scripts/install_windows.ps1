[CmdletBinding()]
param(
    [string]$SourceDirectory = "dist/Panda",
    [string]$InstallDirectory = "",
    [string]$VoiceDirectory = "",
    [switch]$NoShortcut,
    [switch]$Force,
    [switch]$SkipVerify,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-Sha256Hex([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $hash = $sha.ComputeHash($stream)
        }
        finally {
            $sha.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
    return ([BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
}

function Assert-PackageIntegrity([string]$PackageRoot) {
    $manifestPath = Join-Path $PackageRoot "package-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw (
            "Package manifest was not found: $manifestPath. " +
            "Re-run scripts/package_windows.ps1, or pass -SkipVerify to " +
            "install an unverified package."
        )
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ([string]$manifest.format -ne "panda.package") {
        throw "Unexpected package manifest format: $($manifest.format)"
    }
    if ([int]$manifest.schema_version -ne 1) {
        throw "Unsupported package manifest schema: $($manifest.schema_version)"
    }

    $verified = 0
    foreach ($entry in $manifest.files) {
        $relative = ([string]$entry.path).Replace('/', '\')
        if ([string]::IsNullOrWhiteSpace($relative) -or
            [IO.Path]::IsPathRooted($relative) -or
            $relative.Split('\') -contains "..") {
            throw "Package manifest contains an unsafe path: $($entry.path)"
        }

        $filePath = Join-Path $PackageRoot $relative
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            throw "Package file is missing: $($entry.path)"
        }
        $item = Get-Item -LiteralPath $filePath
        if ($item.Length -ne [int64]$entry.size) {
            throw "Package file size mismatch: $($entry.path)"
        }
        if ((Get-Sha256Hex $filePath) -ne ([string]$entry.sha256).ToLowerInvariant()) {
            throw "Package file checksum mismatch: $($entry.path)"
        }
        $verified++
    }

    Write-Host "Verified $verified package file(s)"
    return [string]$manifest.version
}

function Get-SafeFullPath([string]$Path) {
    $resolved = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($resolved)
    if ($resolved.TrimEnd('\', '/') -eq $root.TrimEnd('\', '/')) {
        throw "Refusing to use a filesystem root: $resolved"
    }

    $blockedRoots = @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        $env:WINDIR,
        $env:SystemRoot
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($blocked in $blockedRoots) {
        $prefix = [IO.Path]::GetFullPath($blocked).TrimEnd('\', '/') +
            [IO.Path]::DirectorySeparatorChar
        if ($resolved.StartsWith(
                $prefix,
                [StringComparison]::OrdinalIgnoreCase
            )) {
            throw "Refusing to install under a system directory: $resolved"
        }
    }
    return $resolved
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$sourceCandidate = if ([IO.Path]::IsPathRooted($SourceDirectory)) {
    $SourceDirectory
}
else {
    Join-Path $repoRoot $SourceDirectory
}
$source = (Resolve-Path -LiteralPath $sourceCandidate).Path

$packageVersion = "0.1.0"
if (-not $SkipVerify) {
    $packageVersion = Assert-PackageIntegrity $source
}

$voiceDirectoryWasGiven = -not [string]::IsNullOrWhiteSpace($VoiceDirectory)

if ($RequireSignature) {
    # Checksum verification proves the package was not altered after packing;
    # it says nothing about who packed it. A signature does, so allow a caller
    # to demand one.
    $signedExecutable = Join-Path $source "panda_desktop.exe"
    if (-not (Test-Path -LiteralPath $signedExecutable -PathType Leaf)) {
        throw "Package is missing the executable to verify: $signedExecutable"
    }
    try {
        $signature = Get-AuthenticodeSignature -LiteralPath $signedExecutable
    }
    catch {
        # Usually a PSModulePath inherited from a different PowerShell
        # installation, which leaves the Security module unloadable.
        throw (
            "Cannot verify the signature of $signedExecutable. " +
            "PowerShell's Security module must be loadable: " +
            "$($_.Exception.Message)"
        )
    }
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw (
            "The packaged executable is not validly signed " +
            "(status: $($signature.Status)). Sign the package with " +
            "scripts/package_windows.ps1 -CertificateThumbprint first, or " +
            "drop -RequireSignature."
        )
    }
    Write-Host "Signature is valid: $($signature.SignerCertificate.Subject)"
}

if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $env:LOCALAPPDATA "Panda"
}
if (-not $voiceDirectoryWasGiven) {
    $VoiceDirectory = Join-Path $InstallDirectory "voices"
}

$installRoot = Get-SafeFullPath $InstallDirectory
$voiceRoot = Get-SafeFullPath $VoiceDirectory
$applicationRoot = Join-Path $installRoot "app"

foreach ($required in @(
        (Join-Path $source "panda_desktop.exe"),
        (Join-Path $source "portable")
    )) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Package is missing a required file: $required"
    }
}

$previousVersion = $null
if (Test-Path -LiteralPath $installRoot) {
    if (-not $Force) {
        throw (
            "Installation directory already exists: $installRoot. " +
            "Pass -Force to upgrade in place."
        )
    }

    $infoPath = Join-Path $installRoot "install.json"
    if (-not (Test-Path -LiteralPath $infoPath -PathType Leaf)) {
        throw "Refusing to replace an unknown directory: $installRoot"
    }

    $existing = Get-Content -LiteralPath $infoPath -Raw | ConvertFrom-Json
    if ($null -ne $existing.version) {
        $previousVersion = [string]$existing.version
    }

    # Reuse the recorded voice directory unless the caller named one, so an
    # upgrade never silently starts pointing at an empty voice library.
    if (-not $voiceDirectoryWasGiven -and
        -not [string]::IsNullOrWhiteSpace(
            [string]$existing.voice_directory
        )) {
        $voiceRoot = Get-SafeFullPath ([string]$existing.voice_directory)
    }

    Write-Host "Upgrading the existing installation in place."
    Write-Host "Voice packs at $voiceRoot are preserved."

    # Only the application directory is replaced. Deleting the whole install
    # root would take the voice library with it whenever it lives alongside.
    if (Test-Path -LiteralPath $applicationRoot) {
        Remove-Item -LiteralPath $applicationRoot -Recurse -Force
    }
}

New-Item -ItemType Directory -Path $applicationRoot | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $applicationRoot -Recurse -Force

# Installed copies use the user data directory instead of package-local voices.
Remove-Item -LiteralPath (Join-Path $applicationRoot "portable") -Force `
    -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $voiceRoot -Force | Out-Null
Set-Content `
    -LiteralPath (Join-Path $applicationRoot "voices-path.txt") `
    -Value $voiceRoot `
    -Encoding Utf8

$launchScript = @"
@echo off
setlocal
set "ROOT=%~dp0"
set "PANDA_VOICES_ROOT=$voiceRoot"
set "PANDA_PYTHON=%ROOT%python\python.exe"
set "PANDA_MEANVC2_ROOT=%ROOT%MeanVC2"
set "PYTHONPATH=%ROOT%share\python;%PYTHONPATH%"
set "PYTHONDONTWRITEBYTECODE=1"
start "" "%ROOT%panda_desktop.exe"
"@
Set-Content `
    -LiteralPath (Join-Path $applicationRoot "launch.cmd") `
    -Value $launchScript `
    -Encoding Ascii

$installInfo = [ordered]@{
    version = $packageVersion
    schema_version = 1
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    previous_version = $previousVersion
    application_directory = $applicationRoot
    voice_directory = $voiceRoot
}
$installInfo | ConvertTo-Json | Set-Content `
    -LiteralPath (Join-Path $installRoot "install.json") `
    -Encoding Utf8

Copy-Item `
    -LiteralPath (Join-Path $PSScriptRoot "uninstall_windows.ps1") `
    -Destination (Join-Path $installRoot "uninstall.ps1")

if (-not $NoShortcut) {
    $startMenu = Join-Path `
        $env:APPDATA `
        "Microsoft\Windows\Start Menu\Programs\Panda"
    New-Item -ItemType Directory -Path $startMenu -Force | Out-Null

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut(
        (Join-Path $startMenu "Panda.lnk")
    )
    $shortcut.TargetPath = Join-Path $applicationRoot "panda_desktop.exe"
    $shortcut.WorkingDirectory = $applicationRoot
    $shortcut.IconLocation = Join-Path $applicationRoot "panda_desktop.exe"
    $shortcut.Description = "Panda voice changer"
    $shortcut.Save()

    $uninstallShortcut = $shell.CreateShortcut(
        (Join-Path $startMenu "Uninstall Panda.lnk")
    )
    $uninstallShortcut.TargetPath = "powershell.exe"
    $uninstallShortcut.Arguments = (
        "-NoProfile -ExecutionPolicy Bypass -File `"$installRoot\uninstall.ps1`""
    )
    $uninstallShortcut.WorkingDirectory = $installRoot
    $uninstallShortcut.IconLocation = "shell32.dll,31"
    $uninstallShortcut.Save()
}

Write-Host "Installed Panda at $installRoot"
Write-Host "Voice packs are stored at $voiceRoot"
