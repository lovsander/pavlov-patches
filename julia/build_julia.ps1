# Сборка/запуск Julia-порта PAPPA. Компиляции нет (Julia — интерпретатор), но нужен
# путь к julia.exe: juliaup ставит лончер в %LOCALAPPDATA%\Microsoft\WindowsApps,
# а сам интерпретатор — в %USERPROFILE%\.julia\juliaup\julia-<версия>\bin\julia.exe.
#
#   powershell -File julia/build_julia.ps1             проверить, что пакет грузится
#   powershell -File julia/build_julia.ps1 -Test       + тесты (julia/test/runtests.jl)
#   powershell -File julia/build_julia.ps1 -Vectors    + конформанс-векторы
#   powershell -File julia/build_julia.ps1 -Pipeline   + пайплайн и подсказка со сверкой
# ВАЖНО ПРО КОДИРОВКУ: этот файл сохранён как UTF-8 БЕЗ BOM (как и остальные .ps1 в
# репозитории). Windows PowerShell 5.1 читает такой файл в кодовой странице ANSI, и
# байты кириллицы превращаются в мусор; при этом байт 0x82 декодируется в «умную
# кавычку» U+201A, которую токенайзер PowerShell считает разделителем строки —
# скрипт ломается на разборе. Поэтому весь ИСПОЛНЯЕМЫЙ текст здесь — ASCII
# (сообщения/ошибки по-английски), а кириллица осталась только в комментариях:
# мусор в комментарии безвреден, мусор в строковом литерале — нет.
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Pipeline
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here

# --- поиск julia.exe: прямые бинари juliaup -> PATH-лончер (он печатает лишнее) ---
$candidates = @()
$ju = Join-Path $env:USERPROFILE '.julia\juliaup'
if (Test-Path $ju) {
    $candidates += (Get-ChildItem $ju -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'bin\julia.exe' })
}
if (Test-Path 'C:\Julia') {
    $candidates += (Get-ChildItem 'C:\Julia' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'bin\julia.exe' })
}
$cmd = Get-Command julia -ErrorAction SilentlyContinue
if ($cmd) { $candidates += $cmd.Source }
$julia = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $julia) {
    throw 'julia.exe not found: install Julia (juliaup or the installer) or add its bin to PATH.'
}
Write-Host "julia: $julia"
$env:JULIA_PKG_OFFLINE = 'true'      # зависимостей нет: сеть не нужна

$project = Join-Path $here 'Project.toml'
if (-not (Test-Path $project)) { throw 'Project.toml not found next to this script.' }

if ($Test) {
    & $julia "--project=$here" (Join-Path $here 'test\runtests.jl')
    if ($LASTEXITCODE -ne 0) { throw "tests failed with exit code $LASTEXITCODE" }
    exit 0
}
if ($Vectors) {
    & $julia "--project=$here" (Join-Path $here 'bin\conformance.jl') (Join-Path $repo 'spec\conformance\vectors')
    if ($LASTEXITCODE -ne 0) { throw "conformance vectors failed with exit code $LASTEXITCODE" }
    exit 0
}
if ($Pipeline) {
    & $julia "--project=$here" (Join-Path $here 'bin\pappa.jl') `
        --input (Join-Path $repo 'python\synthetic_data.csv') `
        --out-dir (Join-Path $repo 'samples\synthetic_sphere_julia') `
        --name synthetic_sphere
    if ($LASTEXITCODE -ne 0) { throw "pipeline failed with exit code $LASTEXITCODE" }
    Write-Host 'compare: python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_julia'
    exit 0
}

& $julia "--project=$here" -e 'using Pappa; println(:Pappa, '' '', Pappa.PORT_VERSION)'
if ($LASTEXITCODE -ne 0) { throw "package load failed with exit code $LASTEXITCODE" }

# Подсказки по ручному запуску. Зависимостей нет, поэтому julia.exe годится любой:
# и найденный здесь, и просто из PATH (см. julia/README.md).
Write-Host "resolved julia: $julia"
Write-Host 'vectors:  julia --project=julia julia\bin\conformance.jl spec\conformance\vectors'
Write-Host 'tests:    julia --project=julia julia\test\runtests.jl'
Write-Host 'pipeline: julia --project=julia julia\bin\pappa.jl --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_julia --name synthetic_sphere'
Write-Host 'compare:  python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_julia'

