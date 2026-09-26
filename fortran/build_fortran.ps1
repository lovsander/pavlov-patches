# Сборка Fortran-порта PAPPA на gfortran. Компилятор ищем в PATH, затем в MSYS2
# (C:\msys64\*\bin) и в TDM-GCC — отдельная настройка не нужна. Внешних
# библиотек у порта нет, только рантайм компилятора, поэтому линкуем -static
# (иначе .exe требует libgfortran-*.dll рядом с собой или в PATH).
#
#   powershell -File fortran/build_fortran.ps1            собрать модули и программы
#   powershell -File fortran/build_fortran.ps1 -Test      + тесты (tests/test_json.f90)
#   powershell -File fortran/build_fortran.ps1 -Vectors   + конформанс-векторы
#   powershell -File fortran/build_fortran.ps1 -Clean     пересобрать с нуля
# ВАЖНО ПРО КОДИРОВКУ: файл сохранён как UTF-8 БЕЗ BOM (как и остальные .ps1 в
# репозитории). Windows PowerShell 5.1 читает такой файл в кодировке ANSI, и
# кириллица превращается в мусор; байт 0x82 декодируется в «умную кавычку»
# U+201A, которую токенайзер считает разделителем строки — скрипт ломается на
# разборе (подробности в julia/build_julia.ps1). Поэтому весь ИСПОЛНЯЕМЫЙ текст
# здесь ASCII, а кириллица осталась только в комментариях.
param(
    [switch]$Test,
    [switch]$Vectors,
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$src = Join-Path $here 'src'
$build = Join-Path $here 'build'
$bin = Join-Path $here 'bin'

# --- поиск gfortran.exe: PATH, затем MSYS2 (mingw64/ucrt64), затем TDM-GCC ---
$candidates = @()
$cmd = Get-Command gfortran -ErrorAction SilentlyContinue
if ($cmd) { $candidates += $cmd.Source }
foreach ($sub in @('mingw64', 'ucrt64', 'clang64', 'mingw32')) {
    $candidates += (Join-Path 'C:\msys64' "$sub\bin\gfortran.exe")
}
foreach ($root in @('C:\TDM-GCC-64', 'C:\TDM-GCC-32', 'C:\Program Files\TDM-GCC-64',
                    "$env:LOCALAPPDATA\Programs\TDM-GCC-64")) {
    $candidates += (Join-Path $root 'bin\gfortran.exe')
}
# TDM-GCC из установщика лежит в каталоге с версией в имени: C:\TDM-GCC-<версия>
$candidates += @(Get-ChildItem 'C:\' -Directory -Filter 'TDM-GCC-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'bin\gfortran.exe' })
$gfortran = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gfortran) {
    throw 'gfortran.exe not found: install TDM-GCC (tdm-gcc.tdragon.net) or MSYS2, or add it to PATH.'
}
Write-Host "gfortran: $gfortran"

# Порядок = порядок зависимостей (use): kinds -> signal -> linalg -> json ->
# model -> cleaner -> detector -> csv -> document -> conformance.
# Модуля, которого ещё нет, просто пропускается: порт переносится по частям.
$modules = @('pappa_kinds', 'pappa_signal', 'pappa_linalg', 'pappa_json',
             'pappa_model', 'pappa_cleaner', 'pappa_detector', 'pappa_csv',
             'pappa_document', 'pappa_conformance')
$programs = @('pappa', 'selftest', 'conformance')

# -fcheck=bounds остаётся и в обычной сборке: арифметика порта индексирует
# массивы по данным CSV, и промах мимо массива должен ломать прогон, а не тихо
# портить числа. Тестовый прогон собирается строже -- с -fcheck=all (он ловит
# ещё и неинициализированные переменные, и потерю RECURSIVE в подпрограммах).
$check = if ($Test) { '-fcheck=all' } else { '-fcheck=bounds' }
$flags = @('-std=f2018', '-O2', '-Wall', $check, '-static', '-J.', '-I.')

foreach ($d in @($build, $bin)) {
    if ($Clean -and (Test-Path $d)) { Remove-Item -Recurse -Force $d }
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
$log = Join-Path $build 'compile.log'
Set-Content -Path $log -Value 'PAPPA Fortran compile log' -Encoding ASCII

# Компилируем ИЗ build/: gfortran кладёт .mod и .o в текущий каталог, поэтому
# они оказываются рядом с логом и подхватываются флагами -J. -I.
Push-Location $build
try {
    $failed = 0
    foreach ($m in $modules) {
        $file = Join-Path $src "$m.f90"
        if (-not (Test-Path $file)) {
            Write-Host "[skip] $m (not ported yet)"
            continue
        }
        # Диагностика gfortran идёт в stderr: оба потока сохраняем по отдельности,
        # чтобы разбор падения не требовал повторного запуска компиляции.
        & $gfortran @flags -c $file 1> (Join-Path $build "$m.out") 2> (Join-Path $build "$m.err")
        $code = $LASTEXITCODE
        Add-Content -Path $log -Value "=== $m exit=$code" -Encoding ASCII
        if ($code -ne 0) {
            $failed = $failed + 1
            Write-Host "[fail] $m"
            Get-Content (Join-Path $build "$m.err") -ErrorAction SilentlyContinue | Write-Host
        } else {
            Write-Host "[ok]   $m"
        }
    }
    if ($failed -gt 0) { throw "$failed module(s) failed to compile: see fortran/build/*.err" }

    # Программы линкуем с объектными файлами всех готовых модулей.
    $objs = @(Get-ChildItem $build -Filter '*.o' -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName)
    foreach ($p in $programs) {
        $file = Join-Path $src "$p.f90"
        if (-not (Test-Path $file)) {
            Write-Host "[skip] $p (not ported yet)"
            continue
        }
        & $gfortran @flags -o (Join-Path $bin "$p.exe") $file @objs `
            1> (Join-Path $build "$p.link.out") 2> (Join-Path $build "$p.link.err")
        $code = $LASTEXITCODE
        Add-Content -Path $log -Value "=== $p (program) exit=$code" -Encoding ASCII
        if ($code -ne 0) {
            Get-Content (Join-Path $build "$p.link.err") -ErrorAction SilentlyContinue | Write-Host
            throw "program $p failed to build (see fortran/build/$p.link.err)"
        }
        Write-Host "[ok]   $p"
    }

    # Тест JSON-модуля лежит отдельно в tests/: он не зависит от остальных
    # модулей порта и обязан проходить с самого начала работы над портом.
    if ($Test) {
        & $gfortran @flags -o (Join-Path $bin 'test_json.exe') `
            (Join-Path $here 'tests\test_json.f90') @objs `
            1> (Join-Path $build 'test_json.out') 2> (Join-Path $build 'test_json.err')
        $code = $LASTEXITCODE
        Add-Content -Path $log -Value "=== test_json (program) exit=$code" -Encoding ASCII
        if ($code -ne 0) {
            Get-Content (Join-Path $build 'test_json.err') -ErrorAction SilentlyContinue | Write-Host
            throw 'tests/test_json.f90 did not compile (see fortran/build/test_json.err)'
        }
        Write-Host '[ok]   test_json'
    }
} finally {
    Pop-Location
}
Write-Host "built: $bin"

if ($Test) {
    # Тесту передаём корень репозитория: он ищет в нём samples/ (round-trip
    # эталона и обход всех папок образцов), а без аргумента взял бы текущий
    # каталог и просто пропустил эти проверки.
    & (Join-Path $bin 'test_json.exe') $repo
    if ($LASTEXITCODE -ne 0) { throw "JSON test failed with exit code $LASTEXITCODE" }
    if (Test-Path (Join-Path $bin 'selftest.exe')) {
        & (Join-Path $bin 'selftest.exe') (Join-Path $repo 'spec\conformance\vectors')
        if ($LASTEXITCODE -ne 0) { throw "self-test failed with exit code $LASTEXITCODE" }
    } else {
        Write-Host 'selftest: not ported yet (fortran/src/selftest.f90)'
    }
    exit 0
}
if ($Vectors) {
    $exe = Join-Path $bin 'conformance.exe'
    if (-not (Test-Path $exe)) { throw 'conformance not ported yet (fortran/src/conformance.f90)' }
    & $exe (Join-Path $repo 'spec\conformance\vectors')
    if ($LASTEXITCODE -ne 0) { throw "conformance vectors failed with exit code $LASTEXITCODE" }
    exit 0
}

Write-Host ''
Write-Host 'tests:    powershell -File fortran/build_fortran.ps1 -Test'
Write-Host 'vectors:  powershell -File fortran/build_fortran.ps1 -Vectors'
Write-Host 'pipeline: .\fortran\bin\pappa.exe --input python\synthetic_data.csv --out-dir samples\synthetic_sphere_fortran --name synthetic_sphere'
Write-Host 'compare:  python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_fortran'
