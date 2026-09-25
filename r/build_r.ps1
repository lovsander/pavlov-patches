# Сборка/запуск R-порта PAPPA. Компиляции нет (R — интерпретатор), нужен путь к
# Rscript.exe: CRAN-инсталлятор кладёт его в C:\Program Files\R\R-<версия>\bin,
# пользовательская установка — в %LOCALAPPDATA%\Programs\R.
#
#   powershell -File r/build_r.ps1             проверить, что порт грузится
#   powershell -File r/build_r.ps1 -Test       + тесты (r/tests/runtests.R)
#   powershell -File r/build_r.ps1 -Vectors    + конформанс-векторы
#   powershell -File r/build_r.ps1 -Pipeline   + пайплайн и подсказка со сверкой
# ВАЖНО ПРО КОДИРОВКУ: файл сохранён как UTF-8 БЕЗ BOM (как и остальные .ps1 в
# репозитории). Windows PowerShell 5.1 читает такой файл в кодировке ANSI, и
# кириллица превращается в мусор; байт 0x82 декодируется в «умную кавычку»
# U+201A, которую токенайзер считает разделителем строки — скрипт ломается на
# разборе (подробности в julia/build_julia.ps1). Поэтому весь ИСПОЛНЯЕМЫЙ текст
# здесь ASCII, а кириллица осталась только в комментариях.
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Pipeline
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here

# --- поиск Rscript.exe: свежие версии R приоритетнее, затем PATH ---
$candidates = @()
foreach ($root in @("$env:ProgramFiles\R", "${env:ProgramFiles(x86)}\R",
                    "$env:LOCALAPPDATA\Programs\R", "$env:USERPROFILE\scoop\apps\r",
                    'C:\R')) {
    if (Test-Path $root) {
        $candidates += (Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'bin\Rscript.exe' })
    }
}
$cmd = Get-Command Rscript -ErrorAction SilentlyContinue
if ($cmd) { $candidates += $cmd.Source }
$rscript = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $rscript) {
    throw 'Rscript.exe not found: install R from CRAN or add its bin folder to PATH.'
}
Write-Host "Rscript: $rscript"

if ($Test) {
    & $rscript --vanilla (Join-Path $here 'tests\runtests.R')
    if ($LASTEXITCODE -ne 0) { throw "tests failed with exit code $LASTEXITCODE" }
    exit 0
}
if ($Vectors) {
    & $rscript --vanilla (Join-Path $here 'bin\conformance.R') (Join-Path $repo 'spec\conformance\vectors')
    if ($LASTEXITCODE -ne 0) { throw "conformance vectors failed with exit code $LASTEXITCODE" }
    exit 0
}
if ($Pipeline) {
    & $rscript --vanilla (Join-Path $here 'bin\pappa.R') `
        --input (Join-Path $repo 'python\synthetic_data.csv') `
        --out-dir (Join-Path $repo 'samples\synthetic_sphere_r') `
        --name synthetic_sphere
    if ($LASTEXITCODE -ne 0) { throw "pipeline failed with exit code $LASTEXITCODE" }
    Write-Host 'compare: python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_r'
    exit 0
}

# Проверка загрузки: выражение кладём во временный .R-файл, а путь к src/
# передаём через переменную окружения. Так в аргументах нативной программы нет
# ни двойных кавычек, ни кириллицы (PowerShell 5.1 их съедает — см. julia-порт).
$env:PAPPA_R_SRC = Join-Path $here 'src'
$smoke = Join-Path $env:TEMP 'pappa_r_smoke.R'
Set-Content -Path $smoke -Encoding ASCII -Value @(
    'src <- Sys.getenv("PAPPA_R_SRC")',
    'source(file.path(src, "pappa.R"))',
    'Pappa$load(src)',
    'cat("Pappa", Pappa$PORT_LANGUAGE, Pappa$PORT_VERSION, "loaded\n")'
)
& $rscript --vanilla $smoke
$code = $LASTEXITCODE
Remove-Item $smoke -ErrorAction SilentlyContinue
if ($code -ne 0) { throw "port load failed with exit code $code" }

Write-Host 'vectors:  Rscript --vanilla r/bin/conformance.R spec/conformance/vectors'
Write-Host 'tests:    Rscript --vanilla r/tests/runtests.R'
Write-Host 'pipeline: Rscript --vanilla r/bin/pappa.R --input python/synthetic_data.csv --out-dir samples/synthetic_sphere_r --name synthetic_sphere'
Write-Host 'compare:  python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_r'
