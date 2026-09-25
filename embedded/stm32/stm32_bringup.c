// Bring-up STM32 Blue Pill: проверяем, что симулятор грузит наш образ и что
// UART/DWT/printf работают. Дальше на эту же плату ставится ядро PAPPA.
#include <stdio.h>

#include "stm32_board.h"

extern uint32_t _stack_top;
extern uint32_t _data_load, _data_start, _data_end, _bss_start, _bss_end;

void reset_handler(void);

__attribute__((section(".vectors"), used))
const uint32_t g_vectors[64] = {
    (uint32_t)&_stack_top,          // 0: начальный SP
    (uint32_t)reset_handler,        // 4: Reset
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
};

void reset_handler(void) {
    uint32_t *src = &_data_load, *dst = &_data_start;
    while (dst < &_data_end) *dst++ = *src++;
    for (dst = &_bss_start; dst < &_bss_end; ) *dst++ = 0;

    board_init(115200);
    board_led_set(1);                       // светодиод ВКЛ — признак жизни

    board_puts("STM32_BOOT\n");             // без printf
    const uint32_t c0 = board_cycles();
    volatile uint32_t x = 0;
    for (uint32_t i = 0; i < 100000u; ++i) x += i;
    printf("BUSY_100K_CYCLES %lu\n", (unsigned long)(board_cycles() - c0));
    printf("STM32_OK sysclk=%lu Hz\n", (unsigned long)BOARD_SYSCLK_HZ);

    for (;;) {
        board_puts("STM32_ALIVE\n");
        board_led_set(0);
        for (volatile uint32_t i = 0; i < 2000000u; ++i) { }
        board_led_set(1);
        for (volatile uint32_t i = 0; i < 2000000u; ++i) { }
    }
}
