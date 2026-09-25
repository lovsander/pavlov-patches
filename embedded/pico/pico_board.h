// Плата RP2040 (Pi Pico), bare-metal: UART0, микросекундный таймер, светодиод,
// заглушки newlib (чтобы работали printf/sqrtf и был один общий формат отчёта).
#ifndef PICO_BOARD_H
#define PICO_BOARD_H

#include <stdint.h>

void board_init(uint32_t baud);
void board_putc(char c);
void board_puts(const char *s);
uint32_t board_us(void);          // микросекунды (аппаратный таймер RP2040)
void board_led_toggle(void);

#endif  // PICO_BOARD_H
