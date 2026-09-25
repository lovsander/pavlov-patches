/* Компоновка для RP2040 (bare-metal, без Pico SDK).
   Образ лежит во флеше XIP: 0x10000000, RAM: 0x20000000 (264 КБ).
   Первый сектор — векторная таблица Cortex-M0+ (SP, Reset, ...). */
MEMORY
{
    FLASH (rx)  : ORIGIN = 0x10000000, LENGTH = 2048K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 264K
}

_stack_top = ORIGIN(RAM) + LENGTH(RAM);

ENTRY(reset_handler)

SECTIONS
{
    .boot2 0x10000000 : {
        KEEP(*(.boot2))
    } > FLASH

    .text : {                     /* bootrom прыгает сюда после boot2-стадии */
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
