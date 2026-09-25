# Сборка/запуск Octave-порта PAPPA. Компиляции нет (Octave — интерпретатор),
# нужен путь к octave-cli.exe: установщик кладёт его в
# %LOCALAPPDATA%\Programs\GNU Octave\Octave-<версия>\mingw64\bin (или в
# C:\Program Files\GNU Octave\...). PATH-лончер 'octave' берётся как запасной.
#
#   powershell -File octave/build_octave.ps1             проверить, что порт грузится
#   powershell -File octave/build_octave.ps1 -Test       + самопроверка (bin/selftest.m)
#   powershell -File octave/build_octave.ps1 -Vectors    + конформанс-векторы
#   powershell -File octave/build_octave.ps1 -Pipeline   + пайплайн и подсказка со сверкой
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

# --- поиск octave-cli.exe: свежие версии приоритетнее, затем PATH ---
$candidates = @()
foreach ($root in @("$env:LOCALAPPDATA\Programs\GNU Octave",
                    "$env:ProgramFiles\GNU Octave",
                    "${env:ProgramFiles(x86)}\GNU Octave",
                    "$env:USERPROFILE\scoop\apps\octave",
                    'C:\Octave')) {
    if (Test-Path $root) {
        $candidates += (Get-ChildItem $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                foreach ($sub in @('mingw64', 'mingw32', 'ucrt64', 'clang64')) {
                    Join-Path $_.FullName "$sub\bin\octave-cli.exe"
                }
                Join-Path $_.FullName 'bin\octave-cli.exe'
            })
    }
}
foreach ($probe in @('octave-cli', 'octave')) {
    $cmd = Get-Command $probe -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
}
$octave = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $octave) {
    throw 'octave-cli.exe not found: install GNU Octave (octave.org/download) or add its bin folder to PATH.'
}
Write-Host "octave: $octave"

# --no-init-file: пользовательский ~/.octaverc не влияет на прогон (пакетов у
# порта нет, поэтому выключение настроек безопасно и делает запуск воспроизводимым).
$octaveArgs = @('--no-gui', '--quiet', '--no-init-file')

if ($Test) {
    & $octave @octaveArgs (Join-Path $here 'bin\selftest.m') (Join-Path $repo 'spec\conformance\vectors')
    if ($LASTEXITCODE -ne 0) { throw "self-test failed with exit code $LASTEXITCODE" }
    exit 0
}
if ($Vectors) {
    & $octave @octaveArgs (Join-Path $here 'bin\conformance.m') (Join-Path $repo 'spec\conformance\vectors')
    if ($LASTEXITCODE -ne 0) { throw "conformance vectors failed with exit code $LASTEXITCODE" }
    exit 0
}
if ($Pipeline) {
    & $octave @octaveArgs (Join-Path $here 'bin\pipeline.m') `
        --input (Join-Path $repo 'python\synthetic_data.csv') `
        --out-dir (Join-Path $repo 'samples\synthetic_sphere_octave') `
        --name synthetic_sphere
    if ($LASTEXITCODE -ne 0) { throw "pipeline failed with exit code $LASTEXITCODE" }
    Write-Host 'compare: python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_octave'
    exit 0
}

# Проверка загрузки: выражение кладём во временный .m-файл, а путь к src/
# передаём через переменную окружения. Так в аргументах нативной программы нет
# ни кириллицы, ни лишних кавычек (PowerShell 5.1 их съедает — см. julia-порт).
$env:PAPPA_OCTAVE_SRC = Join-Path $here 'src'
$smoke = Join-Path $env:TEMP 'pappa_octave_smoke.m'
Set-Content -Path $smoke -Encoding ASCII -Value @(
    '1;',
    'src = getenv(''PAPPA_OCTAVE_SRC'');',
    'addpath(src);',
    'printf(''Octave port PAPPA: language octave, pappa 0.1.0\n'');',
    'printf(''  modules: %d .m files in src\n'', numel(what(src).m));',
    'a = 0:359;',
    'prof = 50 + 0.4 * sin(a * pi / 180);',
    'm = model_new();',
    'm = model_fit(m, a, prof);',
    'printf(''  smoke fit: %d patches, max|d| %.3g mm\n'', numel(m.patches), max(abs(model_eval(m, a)'' - prof)));',
    'printf(''  vector reader: %d vectors\n'', numel(conformance_read_vectors(getenv(''PAPPA_OCTAVE_VECTORS''))));',
    'printf(''  created stamp: %s\n'', document_iso_now());'
)
$env:PAPPA_OCTAVE_VECTORS = Join-Path $repo 'spec\conformance\vectors'
& $octave @octaveArgs $smoke
$code = $LASTEXITCODE
Remove-Item $smoke -ErrorAction SilentlyContinue
if ($code -ne 0) { throw "port load failed with exit code $code" }

Write-Host 'vectors:  octave-cli --no-gui --quiet --no-init-file octave/bin/conformance.m spec/conformance/vectors'
Write-Host 'selftest: octave-cli --no-gui --quiet --no-init-file octave/bin/selftest.m spec/conformance/vectors'
Write-Host 'pipeline: octave-cli --no-gui --quiet --no-init-file octave/bin/pipeline.m --input python/synthetic_data.csv --out-dir samples/synthetic_sphere_octave --name synthetic_sphere'
Write-Host 'compare:  python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_octave'
