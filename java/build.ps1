# Сборка Java-порта PAPPA: javac без зависимостей и сборщиков.
#
#   powershell -File java/build.ps1            собрать в java/out
#   powershell -File java/build.ps1 -Test      собрать и прогнать SelfTest (векторы + дымовой тест)
#   powershell -File java/build.ps1 -Clean     пересобрать с нуля
param(
    [switch]$Test,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$out = Join-Path $here 'out'

if ($Clean -and (Test-Path $out)) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force -Path $out | Out-Null

$src = Get-ChildItem (Join-Path $here 'src') -Recurse -Filter *.java |
    ForEach-Object { $_.FullName }
& javac '-Xlint:all' -d $out $src
if ($LASTEXITCODE -ne 0) { throw "javac вернул код $LASTEXITCODE" }
Write-Host "собрано: $out"

if ($Test) {
    & java -cp $out pappa.SelfTest (Join-Path $repo 'spec/conformance/vectors')
    if ($LASTEXITCODE -ne 0) { throw "SelfTest вернул код $LASTEXITCODE" }
    exit 0
}

Write-Host "векторы:  java -cp $out pappa.cli.ConformanceMain spec/conformance/vectors"
Write-Host "пайплайн: java -cp $out pappa.cli.PappaMain --input python/synthetic_data.csv --out-dir samples/synthetic_sphere_java"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_java"
