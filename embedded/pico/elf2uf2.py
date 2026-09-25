"""Упаковка образа флеша RP2040 в UF2 (для прошивки и для симулятора Wokwi).

UF2: блоки по 512 байт, в каждом заголовок 32 байта + 256 байт данных + 4 байта
familyID (RP2040 = 0xE48BFF56) + magic-константы. Адрес блока = база флеша
(0x10000000) + смещение.
"""
import os
import struct
import subprocess
import sys

OBJCOPY = r'C:\msys64\mingw64\bin\arm-none-eabi-objcopy.exe'

MAGIC_START0 = 0x0A324655
MAGIC_START1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
FAMILY_RP2040 = 0xE48BFF56
FLASH_BASE = 0x10000000
PAYLOAD = 256


def elf_to_bin(elf, bin_path):
    subprocess.run([OBJCOPY, '-O', 'binary', elf, bin_path], check=True)
    return open(bin_path, 'rb').read()


def pack_uf2(image, base=FLASH_BASE):
    blocks = []
    n = (len(image) + PAYLOAD - 1) // PAYLOAD
    for i in range(n):
        chunk = image[i * PAYLOAD:(i + 1) * PAYLOAD]
        chunk = chunk + b'\xff' * (PAYLOAD - len(chunk))
        hdr = struct.pack('<8I',
                          MAGIC_START0, MAGIC_START1, 0x00002000,
                          base + i * PAYLOAD, PAYLOAD, i, n, FAMILY_RP2040)
        blocks.append(hdr + chunk + b'\x00' * (476 - len(chunk)) +
                      struct.pack('<I', MAGIC_END))
    return b''.join(blocks)


def main():
    elf, out = sys.argv[1], sys.argv[2]
    tmp_bin = out + '.bin.tmp'
    image = elf_to_bin(elf, tmp_bin)
    os.unlink(tmp_bin)
    uf2 = pack_uf2(image)
    open(out, 'wb').write(uf2)
    print(f'UF2: {out} — образ {len(image)} байт, блоков {len(uf2) // 512}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
