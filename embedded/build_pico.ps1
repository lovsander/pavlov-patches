# Build RP2040 (Pi Pico) firmware, bare-metal, MSYS2 arm-none-eabi toolchain.
#   powershell -File embedded/build_pico.ps1
# Two-pass link: first build the boot2 stage (its CRC depends only on itself),
# compute the CRC32 of the first 252 bytes, then link the whole image with it.
# NOTE: ASCII-only file (Windows PowerShell 5.1 reads .ps1 as ANSI).
param([string]$Source = 'pico_bringup.c', [string]$Out = 'pico_bringup')
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir = Join-Path $root 'pico'
$build = Join-Path $dir 'build'
$bin = 'C:\msys64\mingw64\bin'
New-Item -ItemType Directory -Force $build | Out-Null

$gcc = Join-Path $bin 'arm-none-eabi-gcc.exe'
$objcopy = Join-Path $bin 'arm-none-eabi-objcopy.exe'
$size = Join-Path $bin 'arm-none-eabi-size.exe'
$python = 'C:\Users\maxan\miniconda3\envs\geom-toolkit\python.exe'
foreach ($t in @($gcc, $objcopy, $size, $python)) {
    if (-not (Test-Path $t)) { throw "missing $t" }
}

$cflags = @('-mcpu=cortex-m0plus', '-mthumb', '-Os', '-Wall', '-Wextra',
            '-ffreestanding', '-fno-common', '-nostartfiles',
            '-DPP_MAX_PATCHES=7', '-DPP_MAX_DEG=10',
            "-I$root", "-I$dir")

Write-Host '--- pass 1: boot2 stage ---'
& $gcc @cflags '-c' (Join-Path $dir 'boot2_stub.S') -o (Join-Path $build 'boot2_pass1.o')
& $gcc @cflags '-nostdlib' (Join-Path $build 'boot2_pass1.o') '-T' (Join-Path $dir 'link.ld') `
    -o (Join-Path $build 'boot2_pass1.elf')
$crc = (& $python (Join-Path $dir 'pad_boot2.py') (Join-Path $build 'boot2_pass1.elf')).Trim()
if ($LASTEXITCODE -ne 0 -or -not $crc.StartsWith('0x')) { throw "CRC computation failed: $crc" }
Write-Host "    boot2 CRC32 = $crc"

Write-Host '--- pass 2: full image ---'
& $gcc @cflags "-DBOOT2_CRC=$crc" '-c' (Join-Path $dir 'boot2_stub.S') -o (Join-Path $build 'boot2.o')
& $gcc @cflags "-DBOOT2_CRC=$crc" '-c' (Join-Path $root 'pappa_int.c') -o (Join-Path $build 'pappa_int.o')
& $gcc @cflags "-DBOOT2_CRC=$crc" '-c' (Join-Path $dir 'pico_board.c') -o (Join-Path $build 'pico_board.o')
& $gcc @cflags "-DBOOT2_CRC=$crc" '-c' (Join-Path $dir $Source) -o (Join-Path $build 'app.o')
& $gcc @cflags "-DBOOT2_CRC=$crc" `
    (Join-Path $build 'boot2.o') (Join-Path $build 'pappa_int.o') `
    (Join-Path $build 'pico_board.o') (Join-Path $build 'app.o') `
    '-T' (Join-Path $dir 'link.ld') -o (Join-Path $build "$Out.elf") -lm
& $objcopy -O ihex (Join-Path $build "$Out.elf") (Join-Path $build "$Out.hex")
& $objcopy -O binary (Join-Path $build "$Out.elf") (Join-Path $build "$Out.bin")

Write-Host '--- size (RP2040: 264 KB RAM, flash через XIP) ---'
& $size (Join-Path $build "$Out.elf")
