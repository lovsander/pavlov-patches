# Build firmware for ATmega328P (Arduino Uno) with the MSYS2 AVR toolchain.
#   powershell -File embedded/build_uno.ps1
# Output: embedded/uno/build/firmware.elf, firmware.hex + size report.
# NOTE: ASCII only - Windows PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# text in this file would corrupt the parser.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$uno = Join-Path $root 'uno'
$build = Join-Path $uno 'build'
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

$common = @('-mmcu=atmega328p', '-DF_CPU=16000000UL', '-std=c99', '-Os', '-Wall',
            '-Wextra', '-Wno-unused-parameter', '-DPP_TIMING', "-I$root", "-I$uno")

Write-Host '--- compile ---'
& $gcc @common '-fstack-usage' -c (Join-Path $root 'pappa_int.c') -o (Join-Path $build 'pappa_int.o')
& $gcc @common '-fstack-usage' -c (Join-Path $uno 'main.c') -o (Join-Path $build 'main.o')
& $gcc @common (Join-Path $build 'pappa_int.o') (Join-Path $build 'main.o') `
    -o (Join-Path $build 'firmware.elf') -lm
& $objcopy -O ihex -R .eeprom (Join-Path $build 'firmware.elf') (Join-Path $build 'firmware.hex')

Write-Host '--- size (ATmega328P: 32 KB flash, 2 KB RAM) ---'
& $size '-C' '--mcu=atmega328p' (Join-Path $build 'firmware.elf')

Write-Host '--- stack frame per function ---'
Get-ChildItem $build -Filter '*.su' | ForEach-Object {
    $file = $_.Name
    Get-Content $_.FullName | ForEach-Object {
        if ($_ -match '^(\S+)\s+\d+\s+(\d+)\s+(\S+)') {
            '{0}: {1} {2} bytes' -f $file, $Matches[1], $Matches[2]
        }
    }
}

