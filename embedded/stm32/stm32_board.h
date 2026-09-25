// Плата STM32F103C8 (Blue Pill), bare-metal: RCC (PLL 64 МГц), USART1 на PA9/PA10,
// светодиод PC13, счётчик тактов DWT (для честного замера времени), заглушки newlib.
#ifndef STM32_BOARD_H
#define STM32_BOARD_H

#include <stdint.h>

#define BOARD_SYSCLK_HZ 64000000u     // HSI/2 * 16 (см. board_init)

void board_init(uint32_t baud);
void board_putc(char c);
void board_puts(const char *s);
void board_led_set(int on);
uint32_t board_cycles(void);          // DWT->CYCCNT: такты CPU

#endif  // STM32_BOARD_H
