"""CRC32 для boot2-стадии RP2040.

bootrom считает CRC32 первых 252 байт флеша и сравнивает с 4 байтами по
смещению 252 (little-endian). Вариант алгоритма задаётся переменной окружения
PP_CRC_VARIANT, чтобы можно было перебором найти тот, который принимает
конкретный загрузчик/симулятор:
    zlib        — отражённый, init 0xFFFFFFFF, xorout 0xFFFFFFFF (IEEE)
    mpeg2       — неотражённый, init 0xFFFFFFFF, xorout 0
    mpeg2_xor   — неотражённый, init 0xFFFFFFFF, xorout 0xFFFFFFFF
    mpeg2_init0 — неотражённый, init 0, xorout 0
По умолчанию — zlib.
"""
import os
import subprocess
import sys
import tempfile
import zlib

OBJCOPY = r'C:\msys64\mingw64\bin\arm-none-eabi-objcopy.exe'


def crc32_nonreflected(data, init=0xFFFFFFFF, xorout=0):
    crc = init
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if (crc & 0x80000000) \
                else (crc << 1) & 0xFFFFFFFF
    return crc ^ xorout


def compute(data, variant):
    if variant == 'zlib':
        return zlib.crc32(data) & 0xFFFFFFFF
    if variant == 'mpeg2':
        return crc32_nonreflected(data)
    if variant == 'mpeg2_xor':
        return crc32_nonreflected(data, xorout=0xFFFFFFFF)
    if variant == 'mpeg2_init0':
        return crc32_nonreflected(data, init=0, xorout=0)
    raise SystemExit(f'неизвестный вариант CRC: {variant}')


def section_data(elf, section):
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
        tmp = f.name
    try:
        subprocess.run([OBJCOPY, '-O', 'binary', '--only-section', section, elf, tmp],
                       check=True, capture_output=True)
        return open(tmp, 'rb').read()
    finally:
        os.unlink(tmp)


def main():
    elf = sys.argv[1]
    variant = os.environ.get('PP_CRC_VARIANT', 'zlib')
    blob = section_data(elf, '.boot2')
    if len(blob) != 256:
        print(f'ОШИБКА: .boot2 длиной {len(blob)} байт, ожидалось 256', file=sys.stderr)
        return 1
    crc = compute(blob[:252], variant)
    print(f'0x{crc:08X}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

