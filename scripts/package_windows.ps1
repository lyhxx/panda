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
    # Where the audio engine source lives (the panda-engine repository).
    [string]$EngineDirectory = "",
    [switch]$SkipTests,
    [switch]$NoZip,
    [string]$CertificateThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

if ([string]::IsNullOrWhiteSpace($EngineDirectory)) {
    $EngineDirectory = Join-Path $repoRoot "..\panda-engine"
}
$engineRoot = [IO.Path]::GetFullPath($EngineDirectory)
if (-not (Test-Path -LiteralPath (Join-Path $engineRoot "src\panda_infer") -PathType Container)) {
    throw "Engine source was not found under '$engineRoot'. Pass -EngineDirectory <panda-engine path>."
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
    New-Item -ItemType Directory -Path $pythonDirectory | Out-Null
    tar.exe -xf $runtimeArchive -C $pythonDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to extract the Python runtime"
    }
    Remove-Item -LiteralPath $runtimeArchive -Force

    & (Join-Path $pythonDirectory "Scripts\conda-unpack.exe")
    if ($LASTEXITCODE -ne 0) {
        throw "conda-unpack failed"
    }

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
        "README.md",
        "THIRD_PARTY_NOTICES.md"
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
    version = "0.1.0"
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
    $zipPath = "$outputPath.zip"
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    if ($BundlePython -or $BundleMeanVC2) {
        tar.exe -a -c -f $zipPath -C $outputPath .
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to archive the Windows package"
        }
    }
    else {
        Compress-Archive `
            -Path (Join-Path $outputPath "*") `
            -DestinationPath $zipPath
    }
}

Write-Host "Packaged Panda at $outputPath"
