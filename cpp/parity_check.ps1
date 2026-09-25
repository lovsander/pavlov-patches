# PAPPA port parity check: Python reference vs C++ port (used by ctest).
#
# Registered as the "port_parity_python" test in cpp/CMakeLists.txt:
#   cmake --build --preset msvc-release && ctest --preset msvc-release
#
# Steps: (1) build the reference sample folder with Python, (2) build the same
# sample with the port, (3) compare them numerically (degrees, max|dr|, RMSE to
# the ideal) and return exit code 0/1/2.

param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [string]$Python = "",
    [string]$Csv = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path          # cpp/
$repo = Split-Path -Parent $here                                  # repository root

if ([string]::IsNullOrEmpty($Python)) {
    $Python = "python"
}

# CMake может найти системный Python без numpy (так и было при первом запуске
# ctest). Поэтому проверяем интерпретатор делом и, если numpy нет, берём
# известное окружение проекта (CONTEXT §3).
function Test-PythonWithNumpy([string]$exe) {
    if ([string]::IsNullOrEmpty($exe)) { return $false }
    try {
        & $exe -c "import numpy" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (-not (Test-PythonWithNumpy $Python)) {
    $candidates = @(
        "C:\Users\maxan\miniconda3\envs\geom-toolkit\python.exe",
        "python"
    )
    foreach ($c in $candidates) {
        if (Test-PythonWithNumpy $c) { $Python = $c; break }
    }
}
if (-not (Test-PythonWithNumpy $Python)) {
    throw "No Python with numpy found (pass -Python <path> or -DPython3_EXECUTABLE=...)"
}

if ([string]::IsNullOrEmpty($Csv)) { $Csv = Join-Path $repo "python\synthetic_data.csv" }

$pyDir = Join-Path $repo "samples\_parity_py"
$cppDir = Join-Path $repo "samples\_parity_cpp"
$env:MPLBACKEND = "Agg"

Write-Host "[1/3] reference sample by Python -> $pyDir"
& $Python (Join-Path $repo "python\studies\build_sample.py") --name _parity_py | Out-Null
if ($LASTEXITCODE -ne 0) { throw "build_sample.py failed with $LASTEXITCODE" }

Write-Host "[2/3] sample by the C++ port -> $cppDir"
& $Exe --input $Csv --out-dir $cppDir --name _parity_cpp --quiet | Out-Null
if ($LASTEXITCODE -ne 0) { throw "pappa_pipeline failed with $LASTEXITCODE" }

Write-Host "[3/3] numeric comparison (degrees, max|dr|, RMSE to ideal)"
& $Python (Join-Path $repo "python\studies\verify_port.py") --py-dir $pyDir --cpp-dir $cppDir
exit $LASTEXITCODE
