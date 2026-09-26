# Сборка F#-порта PAPPA. Нужен только .NET SDK: в проекте нет ни одного
# NuGet-пакета (свой JSON, CSV, статистика), поэтому сборка проходит офлайн.
#
#   powershell -File fsharp/build_fsharp.ps1            собрать (Release)
#   powershell -File fsharp/build_fsharp.ps1 -Test      собрать и прогнать SelfTest
#   powershell -File fsharp/build_fsharp.ps1 -Vectors   собрать и проверить конформанс-векторы
#   powershell -File fsharp/build_fsharp.ps1 -Pipeline  собрать и записать samples/synthetic_sphere_fsharp
#   powershell -File fsharp/build_fsharp.ps1 -Clean     пересобрать с нуля (bin/obj долой)
#
# Тот же сценарий без PowerShell (Linux/macOS) — fsharp/build_fsharp.sh.
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
$proj = Join-Path $here 'Pappa.fsproj'

# --- поиск dotnet (PATH, затем стандартные каталоги установки) ---
$dotnet = $null
$cmd = Get-Command dotnet -ErrorAction SilentlyContinue
if ($cmd) { $dotnet = $cmd.Source }
if (-not $dotnet) {
    foreach ($p in @((Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'),
                     (Join-Path $env:LOCALAPPDATA 'Microsoft\dotnet\dotnet.exe'),
                     '/usr/share/dotnet/dotnet',
                     '/usr/local/share/dotnet/dotnet')) {
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
# apphost на Linux/macOS собирается не всегда, поэтому есть запасной путь: dotnet pappa.dll.
# Ловушка PowerShell: функция, которая делает `& $app ...; return $LASTEXITCODE`, заодно
# захватывает в свой выход ВЕСЬ вывод приложения — сравнение с 0 потом врёт. Поэтому
# здесь нет обёртки-функции: префикс команды живёт в массиве, а код берётся из $LASTEXITCODE.
$runner = $exe
$runnerArgs = @()
if (-not $exe) {
    $dll = (Get-ChildItem (Join-Path $here 'bin\Release') -Recurse -Filter 'pappa.dll' -ErrorAction SilentlyContinue |
            Select-Object -First 1).FullName
    if (-not $dll) { throw "не найден собранный pappa.exe/pappa.dll в fsharp/bin/Release" }
    $runner = $dotnet
    $runnerArgs = @($dll)
    Write-Host "собрано: $dll (запуск через dotnet)"
} else {
    Write-Host "собрано: $exe"
}

# PowerShell-ловушка (та же, что у C#-порта): имена переменных регистронезависимы,
# поэтому локальную переменную НЕЛЬЗЯ звать $vectors рядом с параметром
# [switch]$Vectors — это присваивание строки в switch-параметр.
$vecDir = Join-Path $repo 'spec\conformance\vectors'
if ($Test) {
    $a = $runnerArgs + @('selftest', $vecDir)
    & $runner @a
    if ($LASTEXITCODE -ne 0) { throw "SelfTest вернул код $LASTEXITCODE" }
    exit 0
}
if ($Vectors) {
    $a = $runnerArgs + @('conformance', $vecDir)
    & $runner @a
    if ($LASTEXITCODE -ne 0) { throw "векторы: код $LASTEXITCODE" }
    exit 0
}
if ($Pipeline) {
    $a = $runnerArgs + @('pipeline', '--input', (Join-Path $repo 'python\synthetic_data.csv'),
        '--out-dir', (Join-Path $repo 'samples\synthetic_sphere_fsharp'),
        '--name', 'synthetic_sphere', '--quiet')
    & $runner @a
    if ($LASTEXITCODE -ne 0) { throw "пайплайн: код $LASTEXITCODE" }
    exit 0
}


Write-Host "векторы:  .\fsharp\bin\Release\net10.0\pappa.exe conformance spec\conformance\vectors"
Write-Host "тесты:    .\fsharp\bin\Release\net10.0\pappa.exe selftest spec\conformance\vectors"
Write-Host "пайплайн: .\fsharp\bin\Release\net10.0\pappa.exe pipeline --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_fsharp --name synthetic_sphere"
Write-Host "сверка:   python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_fsharp"
