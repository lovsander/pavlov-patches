# Build STM32F103 (Blue Pill) firmware, bare-metal, MSYS2 arm-none-eabi toolchain.
#   powershell -File embedded/build_stm32.ps1
# NOTE: ASCII-only file (Windows PowerShell 5.1 reads .ps1 as ANSI).
param([string]$Source = 'stm32_bringup.c', [string]$Out = 'stm32_bringup')
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir = Join-Path $root 'stm32'
$build = Join-Path $dir 'build'
$bin = 'C:\msys64\mingw64\bin'
New-Item -ItemType Directory -Force $build | Out-Null

$gcc = Join-Path $bin 'arm-none-eabi-gcc.exe'
$objcopy = Join-Path $bin 'arm-none-eabi-objcopy.exe'
$size = Join-Path $bin 'arm-none-eabi-size.exe'
foreach ($t in @($gcc, $objcopy, $size)) {
    if (-not (Test-Path $t)) { throw "missing $t" }
}

$cflags = @('-mcpu=cortex-m3', '-mthumb', '-Os', '-Wall', '-Wextra',
            '-ffreestanding', '-fno-common', '-nostartfiles',
            '-DPP_MAX_PATCHES=4', '-DPP_MAX_DEG=10',
            "-I$root", "-I$dir")

Write-Host '--- compile (STM32F103C8, Cortex-M3, PLL 64 MHz) ---'
& $gcc @cflags '-c' (Join-Path $root 'pappa_int.c') -o (Join-Path $build 'pappa_int.o')
& $gcc @cflags '-c' (Join-Path $dir 'stm32_board.c') -o (Join-Path $build 'stm32_board.o')
& $gcc @cflags '-c' (Join-Path $dir $Source) -o (Join-Path $build 'app.o')
& $gcc @cflags (Join-Path $build 'pappa_int.o') (Join-Path $build 'stm32_board.o') `
    (Join-Path $build 'app.o') '-T' (Join-Path $dir 'link.ld') `
    -o (Join-Path $build "$Out.elf") -lm
& $objcopy -O ihex (Join-Path $build "$Out.elf") (Join-Path $build "$Out.hex")
& $objcopy -O binary (Join-Path $build "$Out.elf") (Join-Path $build "$Out.bin")

Write-Host '--- size (STM32F103C8: 64 KB flash, 20 KB RAM) ---'
& $size (Join-Path $build "$Out.elf")
