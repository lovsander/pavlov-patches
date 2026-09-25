# Build firmware for an Arduino board with the MSYS2 AVR toolchain.
#   powershell -File embedded/build_uno.ps1                 # Uno  (ATmega328P)
#   powershell -File embedded/build_uno.ps1 -Board mega      # Mega (ATmega2560)
# Output: embedded/<board>/build/firmware.elf, firmware.hex + size report.
# NOTE: ASCII only - Windows PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# text in this file would corrupt the parser.
param([ValidateSet('uno', 'mega')][string]$Board = 'uno')
$ErrorActionPreference = 'Stop'

$boards = @{
    uno  = @{ mcu = 'atmega328p'; patches = 3; deg = 8;  pts = 360 }
    mega = @{ mcu = 'atmega2560'; patches = 7; deg = 10; pts = 720 }
}
$cfg = $boards[$Board]

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir = Join-Path $root $Board
$build = Join-Path $dir 'build'
New-Item -ItemType Directory -Force $build | Out-Null

$bin = 'C:\msys64\mingw64\bin'
$gcc = Join-Path $bin 'avr-gcc.exe'
$objcopy = Join-Path $bin 'avr-objcopy.exe'
$size = Join-Path $bin 'avr-size.exe'
foreach ($t in @($gcc, $objcopy, $size)) {
    if (-not (Test-Path $t)) {
        throw "missing $t (install: pacman -S mingw-w64-x86_64-avr-gcc mingw-w64-x86_64-avr-libc)"
    }
}

$common = @("-mmcu=$($cfg.mcu)", '-DF_CPU=16000000UL', '-std=c99', '-Os', '-Wall',
            '-Wextra', '-Wno-unused-parameter', '-DPP_TIMING',
            "-DPP_MAX_PATCHES=$($cfg.patches)", "-DPP_MAX_DEG=$($cfg.deg)",
            "-I$root", "-I$dir")

Write-Host "--- compile ($Board, $($cfg.mcu), $($cfg.patches) patches, deg<=$($cfg.deg)) ---"
& $gcc @common '-fstack-usage' -c (Join-Path $root 'pappa_int.c') -o (Join-Path $build 'pappa_int.o')
& $gcc @common '-fstack-usage' -c (Join-Path $root 'board_main.c') -o (Join-Path $build 'board_main.o')
& $gcc @common (Join-Path $build 'pappa_int.o') (Join-Path $build 'board_main.o') `
    -o (Join-Path $build 'firmware.elf') -lm
& $objcopy -O ihex -R .eeprom (Join-Path $build 'firmware.elf') (Join-Path $build 'firmware.hex')

Write-Host "--- size ($($cfg.mcu)) ---"
& $size '-C' "--mcu=$($cfg.mcu)" (Join-Path $build 'firmware.elf')

Write-Host '--- stack frame per function ---'
Get-ChildItem $build -Filter '*.su' | ForEach-Object {
    $file = $_.Name
    Get-Content $_.FullName | ForEach-Object {
        if ($_ -match '^(\S+)\s+\d+\s+(\d+)\s+(\S+)') {
            '{0}: {1} {2} bytes' -f $file, $Matches[1], $Matches[2]
        }
    }
}


