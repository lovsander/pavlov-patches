# Сборка Kotlin-порта PAPPA. Компилятор берём из PATH, иначе — из Android Studio
# (плагин Kotlin кладёт туда полный kotlinc, отдельная установка не нужна).
#
#   powershell -File kotlin/build.ps1            собрать в kotlin/out
#   powershell -File kotlin/build.ps1 -Test      собрать и прогнать SelfTest
#   powershell -File kotlin/build.ps1 -Clean     пересобрать с нуля
param(
    [switch]$Test,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$out = Join-Path $here 'out'

# --- поиск kotlinc ---
$candidates = @()
$cmd = Get-Command kotlinc -ErrorAction SilentlyContinue
if ($cmd) { $candidates += $cmd.Source }
# Android Studio кладёт полный компилятор в plugins\Kotlin\kotlinc\bin\kotlinc.bat
foreach ($base in @('C:\Program Files\Android', "$env:LOCALAPPDATA\Programs", "$env:LOCALAPPDATA\Android")) {
    if (Test-Path $base) {
        $candidates += (Get-ChildItem $base -Recurse -Depth 6 -Filter 'kotlinc.bat' `
            -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
}
$kotlinc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $kotlinc) {
    throw "kotlinc не найден (PATH и Android Studio). Установите Kotlin или Android Studio."
}
Write-Host "kotlinc: $kotlinc"

# kotlin-stdlib рядом с компилятором — нужен в classpath при запуске через java
$stdlib = Join-Path (Split-Path (Split-Path $kotlinc)) 'lib\kotlin-stdlib.jar'
if (-not (Test-Path $stdlib)) { $stdlib = '' }

if ($Clean -and (Test-Path $out)) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force -Path $out | Out-Null

$src = Get-ChildItem (Join-Path $here 'src') -Recurse -Filter *.kt |
    ForEach-Object { $_.FullName }
& $kotlinc -d $out $src
if ($LASTEXITCODE -ne 0) { throw "kotlinc вернул код $LASTEXITCODE" }
Write-Host "собрано: $out"

$cp = if ($stdlib) { "$out;$stdlib" } else { $out }
if ($Test) {
    & java -cp $cp pappa.SelfTest (Join-Path $repo 'spec/conformance/vectors')
    if ($LASTEXITCODE -ne 0) { throw "SelfTest вернул код $LASTEXITCODE" }
    exit 0
}

Write-Host "векторы:  java -cp `"$cp`" pappa.cli.ConformanceMain spec/conformance/vectors"
Write-Host "пайплайн: java -cp `"$cp`" pappa.cli.PappaMain --input python/synthetic_data.csv --out-dir samples/synthetic_sphere_kotlin"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_kotlin"
