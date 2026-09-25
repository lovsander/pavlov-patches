# Сборка C#-порта PAPPA. Нужен только .NET SDK: в проекте нет ни одного
# NuGet-пакета (свой JSON, CSV, статистика), поэтому сборка проходит офлайн.
#
#   powershell -File csharp/build.ps1            собрать (Release)
#   powershell -File csharp/build.ps1 -Test      собрать и прогнать SelfTest
#   powershell -File csharp/build.ps1 -Vectors   собрать и проверить конформанс-векторы
#   powershell -File csharp/build.ps1 -Pipeline  собрать и записать samples/synthetic_sphere_csharp
#   powershell -File csharp/build.ps1 -Clean     пересобрать с нуля (bin/obj долой)
#
# Кириллица в сообщениях, как и у соседних build-скриптов, в Windows PowerShell 5.1
# отображается кракозябрами: файл UTF-8 без BOM, а PS 5.1 читает его как ANSI.
# На код возврата это не влияет (ворота в verify_all.ps1 — именно код).
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Pipeline,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$proj = Join-Path $here 'Pappa.csproj'

# --- поиск dotnet (PATH, затем стандартные каталоги установки) ---
$dotnet = $null
$cmd = Get-Command dotnet -ErrorAction SilentlyContinue
if ($cmd) { $dotnet = $cmd.Source }
if (-not $dotnet) {
    foreach ($p in @((Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'),
                     (Join-Path $env:LOCALAPPDATA 'Microsoft\dotnet\dotnet.exe'))) {
        if (Test-Path $p) { $dotnet = $p; break }
    }
}
if (-not $dotnet) {
    throw "dotnet не найден (PATH и стандартные каталоги). Установите .NET SDK 8+ (проверено на 10.0)."
}
Write-Host "dotnet: $dotnet"

if ($Clean) {
    foreach ($d in @('bin', 'obj')) {
        $path = Join-Path $here $d
        if (Test-Path $path) { Remove-Item -Recurse -Force $path }
    }
}

& $dotnet build $proj -c Release --nologo
if ($LASTEXITCODE -ne 0) { throw "dotnet build вернул код $LASTEXITCODE" }

$exe = (Get-ChildItem (Join-Path $here 'bin\Release') -Recurse -Filter 'pappa.exe' -ErrorAction SilentlyContinue |
        Select-Object -First 1).FullName
if (-not $exe) { throw "не найден собранный pappa.exe в csharp/bin/Release" }
Write-Host "собрано: $exe"

# PowerShell-ловушка: имена переменных регистронезависимы, поэтому локальную
# переменную НЕЛЬЗЯ звать $vectors/$test рядом с параметром [switch]$Vectors —
# присваивание строки в switch-параметр падает с "Cannot convert value ... SwitchParameter".
$vecDir = Join-Path $repo 'spec\conformance\vectors'
if ($Test) {
    & $exe selftest $vecDir
    if ($LASTEXITCODE -ne 0) { throw "SelfTest вернул код $LASTEXITCODE" }
    exit 0
}
if ($Vectors) {
    & $exe conformance $vecDir
    if ($LASTEXITCODE -ne 0) { throw "векторы: код $LASTEXITCODE" }
    exit 0
}
if ($Pipeline) {
    & $exe pipeline --input (Join-Path $repo 'python\synthetic_data.csv') `
        --out-dir (Join-Path $repo 'samples\synthetic_sphere_csharp') `
        --name synthetic_sphere --quiet
    if ($LASTEXITCODE -ne 0) { throw "пайплайн: код $LASTEXITCODE" }
    exit 0
}

Write-Host "векторы:  .\csharp\bin\Release\net10.0\pappa.exe conformance spec\conformance\vectors"
Write-Host "тесты:    .\csharp\bin\Release\net10.0\pappa.exe selftest spec\conformance\vectors"
Write-Host "пайплайн: .\csharp\bin\Release\net10.0\pappa.exe pipeline --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_csharp --name synthetic_sphere"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_csharp"
