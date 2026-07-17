param(
    [Parameter(Mandatory = $false)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = "0.3.0",

    [Parameter(Mandatory = $false)]
    [string]$Python = "",

    [Parameter(Mandatory = $false)]
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $projectRoot "build"
$workRoot = Join-Path $buildRoot "release-work"
$pyiWork = Join-Path $buildRoot "pyinstaller"
$releaseDir = Join-Path $buildRoot "release"
$appDir = Join-Path $workRoot "Genshin_autoTTS"

if (-not $Python) {
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
}

if (-not $IsccPath) {
    $knownIsccPaths = @(
        (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Programs\Inno Setup 7\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
        "C:\Program Files\Inno Setup 7\ISCC.exe"
    )
    $IsccPath = $knownIsccPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw "Inno Setup compiler ISCC.exe was not found. Install Inno Setup 6/7 or pass -IsccPath."
}

foreach ($path in @($workRoot, $pyiWork, $releaseDir)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $path | Out-Null
}

Push-Location $projectRoot
try {
    $sampleDataPath = Join-Path $projectRoot "src\genshin_autotts\sample_voicepack"
    $pyInstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name", "Genshin_autoTTS",
        "--paths", "src",
        "--distpath", $workRoot,
        "--workpath", $pyiWork,
        "--specpath", $pyiWork,
        "--collect-all", "rapidocr_onnxruntime",
        "--collect-all", "imageio_ffmpeg",
        "--exclude-module", "edge_tts",
        "--exclude-module", "aiohttp",
        "--add-data", "$sampleDataPath;genshin_autotts\sample_voicepack",
        "packaging\launcher.py"
    )
    & $Python @pyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $selfTestPath = Join-Path $workRoot "release-self-test.json"
    $frozenExe = Join-Path $appDir "Genshin_autoTTS.exe"
    $selfTestProcess = Start-Process -FilePath $frozenExe -ArgumentList @(
        "--self-test",
        "`"$selfTestPath`""
    ) -Wait -PassThru
    if ($selfTestProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $selfTestPath)) {
        throw "Frozen application self-test failed with exit code $($selfTestProcess.ExitCode)"
    }
    $selfTest = Get-Content -Raw -Encoding UTF8 -LiteralPath $selfTestPath | ConvertFrom-Json
    if (-not $selfTest.ok -or -not $selfTest.cache_hit_verified) {
        throw "Frozen application self-test did not verify OCR, recording, and cache"
    }

    Copy-Item -LiteralPath "README.md" -Destination (Join-Path $appDir "README.md")
    Copy-Item -LiteralPath "LICENSE" -Destination (Join-Path $appDir "LICENSE.txt")
    Copy-Item -LiteralPath "SAMPLE_AUDIO_LICENSE.md" -Destination (Join-Path $appDir "SAMPLE_AUDIO_LICENSE.md")
    Copy-Item -LiteralPath "config.example.json" -Destination (Join-Path $appDir "config.example.json")
    Copy-Item -LiteralPath "docs\QUICKSTART.zh-CN.md" -Destination (Join-Path $appDir "QUICKSTART.zh-CN.md")

    $portablePath = Join-Path $releaseDir "Genshin_autoTTS-Portable-x64.zip"
    Compress-Archive -Path $appDir -DestinationPath $portablePath -CompressionLevel Optimal

    & $IsccPath "/DMyAppVersion=$Version" "/DSourceDir=$appDir" "/DOutputDir=$releaseDir" "packaging\installer.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }

    $assets = @(
        (Join-Path $releaseDir "Genshin_autoTTS-Setup-x64.exe")
        $portablePath
    )
    $checksumLines = foreach ($asset in $assets) {
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $asset
        "$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($asset))"
    }
    $checksumPath = Join-Path $releaseDir "SHA256SUMS.txt"
    [IO.File]::WriteAllLines($checksumPath, $checksumLines, [Text.UTF8Encoding]::new($false))

    Get-ChildItem -LiteralPath $releaseDir | Select-Object Name, Length, LastWriteTime
}
finally {
    Pop-Location
}
