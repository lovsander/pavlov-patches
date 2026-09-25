// Bring-up RP2040: печатает отчёт и мигает светодиодом — проверка, что Wokwi
// грузит наш образ с boot2-стадией и что UART/таймер/printf работают.
#include <stdio.h>

#include "pappa_int.h"
#include "pico_board.h"

extern uint32_t _stack_top;
extern uint32_t _data_load, _data_start, _data_end, _bss_start, _bss_end;

void reset_handler(void);

__attribute__((section(".vectors"), used))
const uint32_t g_vectors[48] = {
    (uint32_t)&_stack_top,          // 0: начальный SP (грузит железо)
    (uint32_t)reset_handler,        // 4: Reset
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
};

void reset_handler(void) {
    uint32_t *src = &_data_load, *dst = &_data_start;
    while (dst < &_data_end) *dst++ = *src++;
    for (dst = &_bss_start; dst < &_bss_end; ) *dst++ = 0;

    board_init(115200);
    board_led_toggle();                    // СВЕТОДИОД ВКЛ — признак жизни
    board_puts("PICO_BOOT\n");             // без printf: просто UART

    const uint32_t t0 = board_us();
    volatile uint32_t x = 0;
    for (uint32_t i = 0; i < 100000u; ++i) x += i;
    printf("BUSY_100K_US %lu\n", (unsigned long)(board_us() - t0));
    board_puts("PICO_OK\n");

    for (;;) {                             // дальше повторяем: видно и в логе, и глазом
        board_puts("PICO_ALIVE\n");
        for (volatile uint32_t i = 0; i < 4000000u; ++i) { }
    }
}
