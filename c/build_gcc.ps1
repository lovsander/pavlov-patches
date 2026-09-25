# Build the C port: vectors checker (DLL) and the full pipeline (EXE).
#   powershell -File embedded/../c/build_gcc.ps1      # из корня репозитория
# Host caps are raised: a 6000-point section needs a 1357-point training window.
# NOTE: ASCII-only file (Windows PowerShell 5.1 reads .ps1 as ANSI).
$ErrorActionPreference = 'Stop'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bin = 'C:\msys64\mingw64\bin'
$gcc = Join-Path $bin 'gcc.exe'
if (-not (Test-Path $gcc)) { throw "missing $gcc (MSYS2)" }

$defs = @('-DPP_MAX_POINTS=8192', '-DPP_MAX_PATCHES=16', '-DPP_MAX_WINDOW=4096')
$common = @('-std=c99', '-O2', '-Wall', '-Wextra') + $defs

Write-Host '--- pipeline (pappa_c.exe) ---'
& $gcc @common -o (Join-Path $dir 'pappa_c.exe') `
    (Join-Path $dir 'emit.c') (Join-Path $dir 'pappa.c') `
    (Join-Path $dir 'document.c') -lm
Write-Host '--- core DLL for the vectors checker (pappa.dll) ---'
& $gcc @common -shared -o (Join-Path $dir 'pappa.dll') (Join-Path $dir 'pappa.c')

Write-Host ''
Write-Host 'Проверка векторов: python python/studies/check_c_port.py'
Write-Host 'Пайплайн:          c\pappa_c.exe --input <csv> --out-dir <dir> --name <name>'
Write-Host 'Числовая сверка:   python python/studies/verify_port.py --py-dir <python-образец> --cpp-dir <c-образец>'
