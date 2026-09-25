/* Компоновка для STM32F103C8 (Blue Pill), bare-metal.
   Cortex-M3 берёт векторную таблицу прямо из флеша 0x08000000 — никаких
   boot-стадий и контрольных сумм (в отличие от RP2040). */
MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 64K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}

_stack_top = ORIGIN(RAM) + LENGTH(RAM);

ENTRY(reset_handler)

SECTIONS
{
    .text : {
        KEEP(*(.vectors))
        *(.text*)
        *(.rodata*)
    } > FLASH

    .data : {
        *(.data*)
    } > RAM AT> FLASH
    _data_load = LOADADDR(.data);
    _data_start = ADDR(.data);
    _data_end = ADDR(.data) + SIZEOF(.data);

    .bss : {
        *(.bss*)
        *(COMMON)
    } > RAM
    _bss_start = ADDR(.bss);
    _bss_end = ADDR(.bss) + SIZEOF(.bss);

    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) }
}
