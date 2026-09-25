# PAPPA port build without CMake - using g++ (msys64/mingw64).
#
# Why: a fallback when CMake (or make) is not installed, but the port must be
# built and CHECKED (CONTEXT §27). The canonical build is CMake - see
# cpp/README.md and cpp/CMakePresets.json; this script does the same compile.
#
# Usage: powershell -File cpp/build_gcc.ps1
#        powershell -File cpp/build_gcc.ps1 -Debug
param(
    [switch]$Debug,
    [string]$Gxx = "C:\msys64\mingw64\bin\g++.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $root "build"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$sources = @(
    "main.cpp",
    "linalg.cpp",
    "signal_tools.cpp",
    "auto_outlier_cleaner.cpp",
    "patch_approximator.cpp",
    "pit_detector.cpp",
    "geometry_pipeline.cpp",
    "json_writer.cpp",
    "sample_writer.cpp"
)

$flags = @("-std=c++17", "-Wall", "-Wextra")
if ($Debug) { $flags += @("-O0", "-g") } else { $flags += @("-O2") }

$exe = Join-Path $outDir "pappa_pipeline.exe"
Push-Location $root
try {
    Write-Host "build: $Gxx -> $exe"
    & $Gxx @flags -o $exe @sources
    if ($LASTEXITCODE -ne 0) { throw "g++ failed with code $LASTEXITCODE" }
    Write-Host "ok: $exe"
} finally {
    Pop-Location
}
