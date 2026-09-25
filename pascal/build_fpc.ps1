# Сборка Free Pascal порта PAPPA. Компилятор ищем в PATH, затем в C:\FPC\<версия>
# и в комплекте Lazarus — отдельная настройка не нужна.
#
#   powershell -File pascal/build_fpc.ps1            собрать в pascal/bin
#   powershell -File pascal/build_fpc.ps1 -Test      собрать и прогнать SelfTest
#   powershell -File pascal/build_fpc.ps1 -Vectors   собрать и проверить векторы
#   powershell -File pascal/build_fpc.ps1 -Clean     пересобрать с нуля
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here

# --- поиск fpc.exe ---
$candidates = @()
$cmd = Get-Command fpc -ErrorAction SilentlyContinue
if ($cmd) { $candidates += $cmd.Source }
foreach ($base in @('C:\FPC', "$env:LOCALAPPDATA\Programs", 'C:\lazarus\fpc')) {
    if (Test-Path $base) {
        $candidates += (Get-ChildItem $base -Recurse -Depth 4 -Filter 'fpc.exe' `
            -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
}
$fpc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $fpc) {
    throw "fpc не найден. Установите Free Pascal (freepascal.org) или Lazarus."
}
Write-Host "fpc: $fpc"

foreach ($d in @('lib', 'bin')) {
    $p = Join-Path $here $d
    if ($Clean -and (Test-Path $p)) { Remove-Item -Recurse -Force $p }
    New-Item -ItemType Directory -Force -Path $p | Out-Null
}
if ($Clean) {
    Get-ChildItem $here -Include *.ppu, *.o -Recurse -File -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

# ВНИМАНИЕ: FPC требует ПРИКЛЕЕННЫХ значений опций (-Fusrc, -obin\x.exe);
# вариант "-Fu src" компилятор понимает как «исходник с именем src».
Push-Location $here
try {
    foreach ($prog in @('conformance', 'selftest', 'pappa')) {
        & $fpc '-Fusrc' '-FUlib' '-FEbin' "-obin\$prog.exe" "src\$prog.lpr" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "fpc вернул код $LASTEXITCODE на $prog" }
    }
} finally {
    Pop-Location
}
Write-Host "собрано: $(Join-Path $here 'bin')"

$vec = Join-Path $repo 'spec\conformance\vectors'
if ($Test) {
    & (Join-Path $here 'bin\selftest.exe') $vec
    if ($LASTEXITCODE -ne 0) { throw "SelfTest вернул код $LASTEXITCODE" }
    exit 0
}
if ($Vectors) {
    & (Join-Path $here 'bin\conformance.exe') $vec
    if ($LASTEXITCODE -ne 0) { throw "векторы: код $LASTEXITCODE" }
    exit 0
}

Write-Host "векторы:  .\pascal\bin\conformance.exe spec\conformance\vectors"
Write-Host "тесты:    .\pascal\bin\selftest.exe spec\conformance\vectors"
Write-Host "пайплайн: .\pascal\bin\pappa.exe --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_pascal"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_pascal"
