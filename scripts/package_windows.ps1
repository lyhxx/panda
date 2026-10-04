[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",
    [string]$BuildDirectory = "build/windows-msvc-desktop",
    [string]$OutputDirectory = "dist/Panda",
    [string]$QtRoot = "",
    [switch]$BundlePython,
    [switch]$BundleMeanVC2,
    [string]$CondaEnvironmentPrefix = "",
    [string]$CondaPack = "",
    [string]$CondaExecutable = "",
    [string]$MeanVC2Root = "",
    [string]$DeepFilterNetRoot = "",
    [switch]$SkipTests,
    [switch]$NoZip,
    [string]$CertificateThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

# The product version lives in exactly one place:
# core/include/panda/version.hpp. CMake parses it for project(VERSION) and this
# script reads it for the package manifest, so a release only ever bumps one
# file.
$versionHeaderPath = Join-Path $repoRoot "core\include\panda\version.hpp"
$versionHeader = Get-Content -LiteralPath $versionHeaderPath -Raw
if ($versionHeader -notmatch 'Version\{\s*(\d+),\s*(\d+),\s*(\d+)') {
    throw "Could not read the product version from '$versionHeaderPath'."
}
$pandaVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3])"

# The Python engine lives inside this repository (python/src), so packaging no
# longer reaches out to a sibling checkout.
$engineRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot "python"))
if (-not (Test-Path -LiteralPath (Join-Path $engineRoot "src\panda_infer") -PathType Container)) {
    throw "Engine source was not found under '$engineRoot'."
}

function Get-Sha256Hex([string]$Path) {
    $attempt = 0
    while ($true) {
        try {
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
        catch [System.IO.IOException] {
            # Endpoint protection can briefly lock a freshly extracted native
            # module while the manifest is being hashed.
            $attempt += 1
            if ($attempt -ge 3) {
                throw
            }
            Start-Sleep -Milliseconds 500
        }
    }
}

function Get-SignTool {
    # signtool ships with the Windows SDK, in a version-stamped directory.
    $roots = @(
        (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"),
        (Join-Path $env:ProgramFiles "Windows Kits\10\bin")
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) }

    foreach ($root in $roots) {
        $found = Get-ChildItem `
            -LiteralPath $root `
            -Recurse `
            -Filter "signtool.exe" `
            -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($null -ne $found) {
            return $found.FullName
        }
    }
    return ""
}

if ([string]::IsNullOrWhiteSpace($QtRoot)) {
    $QtRoot = Join-Path $repoRoot "..\.tools\Qt\6.8.3\msvc2022_64"
}
$QtRoot = (Resolve-Path -LiteralPath $QtRoot).Path

$cmakeCommand = Get-Command cmake -ErrorAction SilentlyContinue
$cmake = if ($null -ne $cmakeCommand) { $cmakeCommand.Path } else { "" }
if ([string]::IsNullOrWhiteSpace($cmake)) {
    $cmake = "C:\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
}
$ctest = Join-Path (Split-Path -Parent $cmake) "ctest.exe"
$windeployqt = Join-Path $QtRoot "bin\windeployqt.exe"

if ([string]::IsNullOrWhiteSpace($CondaEnvironmentPrefix)) {
    $CondaEnvironmentPrefix = Join-Path `
        $repoRoot `
        "..\.tools\miniforge3\envs\meanvc2-cpu"
}
if ([string]::IsNullOrWhiteSpace($CondaPack)) {
    $CondaPack = Join-Path `
        $repoRoot `
        "..\.tools\miniforge3\Scripts\conda-pack.exe"
}
if ([string]::IsNullOrWhiteSpace($CondaExecutable)) {
    $CondaExecutable = Join-Path `
        $repoRoot `
        "..\.tools\miniforge3\Scripts\conda.exe"
}
if ([string]::IsNullOrWhiteSpace($MeanVC2Root)) {
    $MeanVC2Root = Join-Path $repoRoot "..\deps\MeanVC2"
}
if ([string]::IsNullOrWhiteSpace($DeepFilterNetRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($env:PANDA_DEEPFILTER_ROOT)) {
        $DeepFilterNetRoot = $env:PANDA_DEEPFILTER_ROOT
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $DeepFilterNetRoot = Join-Path `
            $env:LOCALAPPDATA `
            "DeepFilterNet\DeepFilterNet\Cache\DeepFilterNet3"
    }
}

foreach ($required in @($cmake, $windeployqt)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required tool was not found: $required"
    }
}
if (-not $SkipTests -and -not (Test-Path -LiteralPath $ctest -PathType Leaf)) {
    throw "Required tool was not found: $ctest"
}

$buildPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $BuildDirectory))
$outputPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
$finalOutputPath = $outputPath
$stagingPath = "$outputPath.building-$PID"
$distRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot "dist"))
$distPrefix = $distRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $outputPath.StartsWith(
        $distPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
    throw "OutputDirectory must stay under $distRoot"
}

# Build in a sibling staging directory and swap only after every runtime file
# and the manifest are complete. Otherwise a user who launches the executable
# while packaging is running sees a half-populated directory and Windows
# reports a missing Qt DLL.
$outputPath = $stagingPath
if (Test-Path -LiteralPath $outputPath) {
    Remove-Item -LiteralPath $outputPath -Recurse -Force
}
New-Item -ItemType Directory -Path $outputPath | Out-Null

# Keep user-installed voice packs across a rebuild. The installer already
# preserves its separate voices directory; the portable directory should do
# the same instead of replacing a user's library with an empty folder.
$previousVoicesPath = Join-Path $finalOutputPath "voices"
if (Test-Path -LiteralPath $previousVoicesPath -PathType Container) {
    Copy-Item `
        -Recurse `
        -Force `
        -LiteralPath $previousVoicesPath `
        -Destination $outputPath
}

& $cmake `
    -S $repoRoot `
    -B $buildPath `
    -G "Visual Studio 17 2022" `
    -A x64 `
    -DPANDA_BUILD_DESKTOP=ON `
    -DPANDA_BUILD_TESTS=ON
if ($LASTEXITCODE -ne 0) {
    throw "CMake configure failed"
}

& $cmake --build $buildPath --config $Configuration
if ($LASTEXITCODE -ne 0) {
    throw "CMake build failed"
}

if (-not $SkipTests) {
    & $ctest --test-dir $buildPath -C $Configuration --output-on-failure
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed"
    }
}

$executable = Join-Path `
    $buildPath `
    "desktop\$Configuration\panda_desktop.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Desktop executable was not found: $executable"
}

$packagedExecutable = Join-Path $outputPath "panda_desktop.exe"
Copy-Item -LiteralPath $executable -Destination $packagedExecutable

$deployMode = if ($Configuration -eq "Debug") { "--debug" } else { "--release" }
$deployAttempts = 0
while ($true) {
    & $windeployqt `
        $deployMode `
        --no-translations `
        --qmldir (Join-Path $repoRoot "desktop\qml") `
        $packagedExecutable
    if ($LASTEXITCODE -eq 0) {
        break
    }

    # Endpoint protection can briefly lock a freshly copied executable on
    # Windows. windeployqt then reports that it cannot open the file even
    # though it is present. Retry the deployment before failing the build.
    $deployAttempts += 1
    if ($deployAttempts -ge 3) {
        throw "windeployqt failed after $deployAttempts attempts"
    }
    Write-Warning "windeployqt failed; retrying ($deployAttempts/3)"
    Start-Sleep -Seconds 1
}

# The executable and every Qt DLL link the dynamic CRT (MSVCP140 /
# VCRUNTIME140*). Windows itself does not carry those: a machine that never
# installed the VC++ redistributable dies in the loader with a "找不到
# VCRUNTIME140.dll" dialog before main() ever runs -- windeployqt does not
# deploy them reliably. Copy the CRT app-locally instead: the executable's
# own directory is first in the DLL search order, so the package stays
# install-free.
$crtCandidates = @(
    "C:\Program Files*\Microsoft Visual Studio\2022\*\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT",
    "C:\Program Files*\Microsoft Visual Studio\2022\*\VC\Redist\MSVC\*\x64\Microsoft.VC142.CRT",
    "C:\BuildTools\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT"
)
$crtDirectories = @(
    Get-ChildItem -Path $crtCandidates -Directory -ErrorAction SilentlyContinue |
        Sort-Object -Property FullName -Descending
)
if ($crtDirectories.Count -eq 0) {
    throw (
        "No VC CRT redistributable found (Microsoft.VC*.CRT); the package " +
        "would not start on machines without the VC++ runtime."
    )
}
Copy-Item `
    -Path (Join-Path $crtDirectories[0].FullName "*.dll") `
    -Destination $outputPath

# Signing has to happen after windeployqt and before the checksum manifest, so
# the recorded hash is the hash of the signed binary.
if (-not [string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    $signtool = Get-SignTool
    if ([string]::IsNullOrWhiteSpace($signtool)) {
        throw (
            "signtool.exe was not found. Install the Windows SDK, or omit " +
            "-CertificateThumbprint to build an unsigned package."
        )
    }

    & $signtool sign `
        /sha1 $CertificateThumbprint `
        /fd SHA256 `
        /tr $TimestampUrl `
        /td SHA256 `
        $packagedExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed to sign $packagedExecutable"
    }

    & $signtool verify /pa $packagedExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "signature verification failed for $packagedExecutable"
    }
    Write-Host "Signed $packagedExecutable"
}
else {
    Write-Host "No -CertificateThumbprint given; building an unsigned package."
}

$pythonShare = Join-Path $outputPath "share\python"
New-Item -ItemType Directory -Path $pythonShare | Out-Null
foreach ($package in @("panda_cli", "panda_infer", "panda_pack")) {
    Copy-Item `
        -Recurse `
        -Force `
        -LiteralPath (Join-Path $engineRoot "src\$package") `
        -Destination (Join-Path $pythonShare $package)
}
# Every package's __init__ does `from panda_version import __version__`, and
# this module sits at the src root next to the packages -- not inside them.
# Without it the import only resolves through the development machine's
# editable-install .pth, i.e. the package works on the packing machine and
# fails on every other computer.
Copy-Item `
    -Force `
    -LiteralPath (Join-Path $engineRoot "src\panda_version.py") `
    -Destination (Join-Path $pythonShare "panda_version.py")

Get-ChildItem -LiteralPath $pythonShare -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $pythonShare -Recurse -File -Filter "*.pyc" |
    Remove-Item -Force

if ($BundlePython) {
    if ([string]::IsNullOrWhiteSpace($DeepFilterNetRoot)) {
        throw (
            "DeepFilterNet checkpoint was not found. Set " +
            "-DeepFilterNetRoot or PANDA_DEEPFILTER_ROOT."
        )
    }
    $resolvedDeepFilterNet = (
        Resolve-Path -LiteralPath $DeepFilterNetRoot
    ).Path
    foreach ($relative in @(
            "config.ini",
            "checkpoints\model_120.ckpt.best"
        )) {
        $required = Join-Path $resolvedDeepFilterNet $relative
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "DeepFilterNet asset was not found: $required"
        }
    }

    $resolvedPrefix = (Resolve-Path -LiteralPath $CondaEnvironmentPrefix).Path
    $resolvedCondaPack = (Resolve-Path -LiteralPath $CondaPack).Path
    $resolvedConda = (Resolve-Path -LiteralPath $CondaExecutable).Path
    foreach ($required in @(
            $resolvedPrefix,
            $resolvedCondaPack,
            $resolvedConda
        )) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Python bundling input was not found: $required"
        }
    }

    $runtimeArchive = Join-Path $outputPath "python-runtime.zip"
    $previousCondaExe = $env:CONDA_EXE
    try {
        $env:CONDA_EXE = $resolvedConda
        & $resolvedCondaPack `
            --prefix $resolvedPrefix `
            --output $runtimeArchive `
            --format zip `
            --compress-level 1 `
            --n-threads 4 `
            --ignore-missing-files `
            --ignore-editable-packages `
            --force `
            --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "conda-pack failed"
        }
    }
    finally {
        if ($null -eq $previousCondaExe) {
            Remove-Item Env:CONDA_EXE -ErrorAction SilentlyContinue
        }
        else {
            $env:CONDA_EXE = $previousCondaExe
        }
    }

    $pythonDirectory = Join-Path $outputPath "python"
    New-Item -ItemType Directory -Path $pythonDirectory -Force | Out-Null
    # Extracting ~50k files in a burst can trip endpoint protection: individual
    # writes fail with "No such file or directory" even though the directory
    # tree is present (observed on ucrtbase.dll; the same entries extract
    # cleanly on retry). Retry like windeployqt instead of failing the run.
    $extractAttempts = 0
    while ($true) {
        tar.exe -xf $runtimeArchive -C $pythonDirectory
        if ($LASTEXITCODE -eq 0) {
            break
        }
        $extractAttempts += 1
        if ($extractAttempts -ge 3) {
            throw "Failed to extract the Python runtime after $extractAttempts attempts"
        }
        Write-Warning "Runtime extraction failed; retrying ($extractAttempts/3)"
        Start-Sleep -Seconds 2
    }
    Remove-Item -LiteralPath $runtimeArchive -Force

    & (Join-Path $pythonDirectory "Scripts\conda-unpack.exe")
    if ($LASTEXITCODE -ne 0) {
        throw "conda-unpack failed"
    }

    # The development environment installed the engine as editable, which
    # leaves a .pth pointing at THIS machine's source checkout. In the
    # packaged runtime that pointer is dead weight on every other computer
    # and a silent dependency on the repository here (it used to be the only
    # reason `panda_version` resolved; that module now ships in share\python).
    $sitePackages = Join-Path $pythonDirectory "Lib\site-packages"
    Get-ChildItem -LiteralPath $sitePackages -Filter "__editable__*.pth" `
        -File -ErrorAction SilentlyContinue |
        Remove-Item -Force

    $deepFilterDestination = Join-Path `
        $outputPath `
        "DeepFilterNet\DeepFilterNet3"
    New-Item -ItemType Directory -Path $deepFilterDestination -Force | Out-Null
    Copy-Item `
        -LiteralPath (Join-Path $resolvedDeepFilterNet "config.ini") `
        -Destination (Join-Path $deepFilterDestination "config.ini")
    $deepFilterCheckpoint = Join-Path `
        $deepFilterDestination `
        "checkpoints\model_120.ckpt.best"
    New-Item `
        -ItemType Directory `
        -Path (Split-Path -Parent $deepFilterCheckpoint) `
        -Force |
        Out-Null
    Copy-Item `
        -LiteralPath (
            Join-Path `
                $resolvedDeepFilterNet `
                "checkpoints\model_120.ckpt.best"
        ) `
        -Destination $deepFilterCheckpoint

    $packagedPython = Join-Path $pythonDirectory "python.exe"
    $probeAttempts = 0
    $numpyVersion = ""
    while ($true) {
        $numpyVersion = & $packagedPython -c (
            "import numpy, df; print(numpy.__version__)"
        )
        if ($LASTEXITCODE -eq 0) {
            break
        }
        $probeAttempts += 1
        if ($probeAttempts -ge 3) {
            throw "Bundled Python cannot import DeepFilterNet"
        }
        Write-Warning (
            "Bundled Python probe failed; retrying " +
            "($probeAttempts/3)"
        )
        Start-Sleep -Seconds 2
    }
    if ([version]$numpyVersion -ge [version]"2.0") {
        throw (
            "DeepFilterNet requires numpy<2, but the bundled environment has " +
            "numpy $numpyVersion"
        )
    }
}

if ($BundleMeanVC2) {
    $resolvedMeanVC2 = (Resolve-Path -LiteralPath $MeanVC2Root).Path
    $meanvc2Destination = Join-Path $outputPath "MeanVC2"
    New-Item -ItemType Directory -Path $meanvc2Destination | Out-Null

    foreach ($directory in @("runtime", "src")) {
        Copy-Item `
            -Recurse `
            -Force `
            -LiteralPath (Join-Path $resolvedMeanVC2 $directory) `
            -Destination (Join-Path $meanvc2Destination $directory)
    }

    foreach ($relative in @(
            "ckpts\vocos\vocos.pt",
            # Both VC variants: 120ms is the default (it is ~2x cheaper per
            # block and runs with a much smaller buffer), 40ms stays selectable.
            "ckpts\pretrained_models\meanvc2_120ms_40ms.safetensors",
            "ckpts\pretrained_models\meanvc2_40ms_40ms.safetensors",
            "preprocess\ckpts\fastu2pp_160ms.pt",
            "preprocess\ckpts\fastu2pp_80ms.pt",
            "preprocess\ckpts\wavlm_large_finetune.pth",
            "preprocess\ckpts\wavlm_large_cfg.pt"
        )) {
        $source = Join-Path $resolvedMeanVC2 $relative
        $destination = Join-Path $meanvc2Destination $relative
        New-Item `
            -ItemType Directory `
            -Path (Split-Path -Parent $destination) `
            -Force |
            Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }
}

if ($BundlePython) {
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $pythonShare
        $doctorArguments = @(
            "-m",
            "panda_cli",
            "doctor",
            "--python",
            $packagedPython
        )
        if ($BundleMeanVC2) {
            $doctorArguments += @(
                "--meanvc2-root",
                (Join-Path $outputPath "MeanVC2")
            )
        }
        if ($BundlePython) {
            $doctorArguments += @(
                "--deepfilter-root",
                (Join-Path $outputPath "DeepFilterNet\DeepFilterNet3")
            )
        }
        & $packagedPython @doctorArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Bundled Python runtime self-check failed"
        }
    }
    finally {
        if ($null -eq $previousPythonPath) {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONPATH = $previousPythonPath
        }
    }
}

foreach ($document in @(
        "LICENSE",
        "NOTICE",
        "README.md"
    )) {
    Copy-Item `
        -LiteralPath (Join-Path $repoRoot $document) `
        -Destination (Join-Path $outputPath $document)
}

$thirdPartyDestination = Join-Path $outputPath "third_party"
New-Item -ItemType Directory -Path $thirdPartyDestination -Force | Out-Null
Copy-Item `
    -Recurse `
    -Force `
    -LiteralPath (Join-Path $repoRoot "third_party\notices") `
    -Destination $thirdPartyDestination

New-Item `
    -ItemType Directory `
    -Path (Join-Path $outputPath "voices") `
    -Force |
    Out-Null
New-Item -ItemType File -Path (Join-Path $outputPath "portable") | Out-Null

$launchScript = @"
@echo off
setlocal
set "ROOT=%~dp0"
if not defined PANDA_VOICES_ROOT set "PANDA_VOICES_ROOT=%ROOT%voices"
if not defined PANDA_PYTHON if exist "%ROOT%python\python.exe" set "PANDA_PYTHON=%ROOT%python\python.exe"
if not defined PANDA_MEANVC2_ROOT if exist "%ROOT%MeanVC2\runtime\run_rt.py" set "PANDA_MEANVC2_ROOT=%ROOT%MeanVC2"
if not defined PANDA_DEEPFILTER_ROOT if exist "%ROOT%DeepFilterNet\DeepFilterNet3\config.ini" set "PANDA_DEEPFILTER_ROOT=%ROOT%DeepFilterNet\DeepFilterNet3"
set "PYTHONPATH=%ROOT%share\python;%PYTHONPATH%"
set "PYTHONDONTWRITEBYTECODE=1"
start "" "%ROOT%panda_desktop.exe"
"@
Set-Content `
    -LiteralPath (Join-Path $outputPath "launch.cmd") `
    -Value $launchScript `
    -Encoding Ascii

# Record a checksum manifest so the installer can detect a tampered or
# truncated package before copying anything into place.
$manifestPath = Join-Path $outputPath "package-manifest.json"
if (Test-Path -LiteralPath $manifestPath) {
    Remove-Item -LiteralPath $manifestPath -Force
}
$packageFiles = @()
foreach ($item in Get-ChildItem -LiteralPath $outputPath -Recurse -File) {
    $relative = $item.FullName.Substring($outputPath.Length + 1).Replace('\', '/')
    $packageFiles += [ordered]@{
        path = $relative
        size = $item.Length
        sha256 = Get-Sha256Hex $item.FullName
    }
}
$packageInfo = [ordered]@{
    format = "panda.package"
    schema_version = 1
    version = $pandaVersion
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    files = @($packageFiles)
}
$packageInfo | ConvertTo-Json -Depth 4 | Set-Content `
    -LiteralPath $manifestPath `
    -Encoding Utf8
Write-Host "Wrote package manifest with $($packageFiles.Count) file(s)"

$backupPath = "$finalOutputPath.previous-$PID"
if (Test-Path -LiteralPath $backupPath) {
    Remove-Item -LiteralPath $backupPath -Recurse -Force
}
if (Test-Path -LiteralPath $finalOutputPath) {
    Move-Item -LiteralPath $finalOutputPath -Destination $backupPath
}
Move-Item -LiteralPath $outputPath -Destination $finalOutputPath
if (Test-Path -LiteralPath $backupPath) {
    Remove-Item -LiteralPath $backupPath -Recurse -Force
}
$outputPath = $finalOutputPath

if (-not $NoZip) {
    # The release ships as three assembly parts plus a standalone pack tool:
    #   1) Panda-<version>.zip  program: exe, Qt, engine source, documents
    #   2) Panda-runtime.zip    bundled python/ + DeepFilterNet/
    #   3) Panda-Models.zip     bundled MeanVC2/ models
    #   4) Panda-Pack.zip       voice-pack exporter (no environment)
    # Parts 1-3 extract into the same folder: launch.cmd then finds python/,
    # MeanVC2/ and DeepFilterNet/ next to the executable. GitHub limits a
    # single release asset to 2 GiB, so every archive is checked after it is
    # written instead of after an upload is rejected.
    $releaseDirectory = Join-Path (Split-Path -Parent $outputPath) "release"
    if (Test-Path -LiteralPath $releaseDirectory) {
        Remove-Item -LiteralPath $releaseDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $releaseDirectory | Out-Null
    $archives = @()

    # Legacy single-file package from before the split.
    $legacyZip = "$outputPath.zip"
    if (Test-Path -LiteralPath $legacyZip) {
        Remove-Item -LiteralPath $legacyZip -Force
    }

    # 1) Program. Staged through robocopy so the bundled runtime, the models
    #    and voices/ stay out: voices holds the user's private packs and must
    #    never end up in a public asset.
    $mainZip = Join-Path $releaseDirectory "Panda-$pandaVersion.zip"
    $programStaging = Join-Path $releaseDirectory "program-staging"
    New-Item -ItemType Directory -Path $programStaging | Out-Null
    # /XD matches a bare name at ANY depth, so excluding "python" would also
    # drop share\python -- the engine source the packaged app runs from.
    # Match by absolute path so only the top-level bundled directories are
    # left out of the program asset.
    $bundledRoot = [IO.Path]::GetFullPath($outputPath)
    $robocopyArgs = @(
        $outputPath, $programStaging, "/E", "/R:1", "/W:1",
        "/XD",
        (Join-Path $bundledRoot "python"),
        (Join-Path $bundledRoot "MeanVC2"),
        (Join-Path $bundledRoot "DeepFilterNet"),
        (Join-Path $bundledRoot "voices"),
        "/NFL", "/NDL", "/NJH", "/NJS", "/NP"
    )
    robocopy @robocopyArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed while staging the program package ($LASTEXITCODE)"
    }
    tar.exe -a -c -f $mainZip -C $programStaging .
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to archive the program package"
    }
    Remove-Item -LiteralPath $programStaging -Recurse -Force
    $archives += $mainZip

    # 2) Python runtime and 3) models, streamed straight from the package tree.
    if ($BundlePython) {
        $runtimeZip = Join-Path $releaseDirectory "Panda-runtime.zip"
        tar.exe -a -c -f $runtimeZip -C $outputPath python DeepFilterNet
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to archive the Python runtime package"
        }
        $archives += $runtimeZip
    }
    if ($BundleMeanVC2) {
        $modelsZip = Join-Path $releaseDirectory "Panda-Models.zip"
        tar.exe -a -c -f $modelsZip -C $outputPath MeanVC2
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to archive the model package"
        }
        $archives += $modelsZip
    }

    # 4) Standalone voice-pack exporter: source plus a usage note only -- it
    #    deliberately ships without an environment, so whoever builds packs
    #    supplies Python and the MeanVC2 checkout themselves.
    $packReadme = @"
Panda voice-pack exporter
=========================

Turns audio files (WAV / MP3 / FLAC / OGG ...) into a .zip voice pack for
Panda Voice Changer.

Requirements (not bundled):
  * Python 3.10+
      pip install numpy soundfile scipy pillow
  * The official MeanVC2 checkout for speaker-embedding extraction
    (pass its path with --meanvc2-root)

Run from this folder:

      python -m panda_pack --help

Example:

      python -m panda_pack --name "My Voice" --id my-voice --audio voice.wav ^
          --meanvc2-root C:\path\MeanVC2 --python python --device cpu ^
          --output out --overwrite
"@
    $packZip = Join-Path $releaseDirectory "Panda-Pack.zip"
    $packStaging = Join-Path $releaseDirectory "pack-staging"
    $packRoot = Join-Path $packStaging "Panda-Pack"
    New-Item -ItemType Directory -Path $packRoot -Force | Out-Null
    Copy-Item -Recurse -Force `
        -LiteralPath (Join-Path $engineRoot "src\panda_pack") `
        -Destination (Join-Path $packRoot "panda_pack")
    Copy-Item -Force `
        -LiteralPath (Join-Path $engineRoot "src\panda_version.py") `
        -Destination (Join-Path $packRoot "panda_version.py")
    Get-ChildItem -LiteralPath $packRoot -Recurse -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force
    Set-Content `
        -LiteralPath (Join-Path $packRoot "README.txt") `
        -Value $packReadme `
        -Encoding Utf8
    tar.exe -a -c -f $packZip -C $packStaging Panda-Pack
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to archive the pack tool package"
    }
    Remove-Item -LiteralPath $packStaging -Recurse -Force
    $archives += $packZip

    $gitHubAssetLimit = 2L * 1024 * 1024 * 1024
    foreach ($archive in $archives) {
        $size = (Get-Item -LiteralPath $archive).Length
        if ($size -gt $gitHubAssetLimit) {
            throw (
                "'$(Split-Path $archive -Leaf)' is " +
                "$([math]::Round($size / 1GB, 2)) GB, over the 2 GiB " +
                "GitHub release asset limit. Split the package further."
            )
        }
        Write-Host ("  {0,-26} {1,7:N2} GB" -f `
            (Split-Path $archive -Leaf), ($size / 1GB))
    }
}

Write-Host "Packaged Panda at $outputPath"
if (-not $NoZip) {
    Write-Host "Release assets at $releaseDirectory"
}
