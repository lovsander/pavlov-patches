// PAPPA на ATmega328P (Arduino Uno) — «младший брат»: только целые числа и
// 1.9 КБ RAM. Bare-metal (без ядра Arduino), сечение лежит во ФЛЕШЕ.
//
// Что показывает прогон в Wokwi:
//   * помещается ли целочисленное ядро в Uno (флеш/RAM, отчёт avr-size),
//   * сколько ЦИКЛОВ/микросекунд реально занимает обучение на 16 МГц
//     (TIME_US — измерено таймером на чипе, а не прикидка),
//   * совпадают ли числа на AVR и на хосте бит-в-бит (check.py).
#include <avr/io.h>
#include <avr/interrupt.h>
#include <stdio.h>
#include <string.h>

#include "pappa_int.h"
#include "pp_report.h"
#include "section_data.h"

#define F_CPU_HZ 16000000UL

// ---------------------------------------------------------------- UART (9600)
static int uart_putc(char c, FILE *stream) {
    (void)stream;
    if (c == '\n') uart_putc('\r', stream);
    while (!(UCSR0A & (1 << UDRE0))) { }
    UDR0 = (uint8_t)c;
    return 0;
}
static FILE uart_out = FDEV_SETUP_STREAM(uart_putc, NULL, _FDEV_SETUP_WRITE);

// ------------------------------------------------- таймер 1: 4 мкс на тик
static volatile uint16_t g_ovf = 0;
ISR(TIMER1_OVF_vect) { ++g_ovf; }

static void timer_start(void) {
    TCCR1A = 0;
    TCCR1B = (1 << CS11) | (1 << CS10);   // /64 -> 4 мкс при 16 МГц
    TCNT1 = 0;
    g_ovf = 0;
    TIMSK1 = (1 << TOIE1);
}
static unsigned long timer_us(void) {
    uint16_t ovf, cnt;
    const uint8_t sreg = SREG;
    cli();
    ovf = g_ovf;
    cnt = TCNT1;
    SREG = sreg;                          // читаем пару атомарно
    return ((unsigned long)ovf * 65536UL + (unsigned long)cnt) * 4UL;
}

int main(void) {
    UBRR0 = (uint16_t)(F_CPU_HZ / (16UL * 9600UL) - 1);
    UCSR0B = (1 << TXEN0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);
    stdout = &uart_out;

    DDRB |= (1 << 5);                    // светодиод на PB5 (pin 13)

    pp_model m;
    memset(&m, 0, sizeof(m));
    m.n = PP_SECTION_N;
    m.y_u = pp_section_u;
    m.n_patches = PP_N_PATCHES;
    m.half_train_pts = PP_HALF_TRAIN_PTS;
    m.deg_min = PP_DEG_MIN;
    m.deg_max = PP_DEG_MAX;
    m.floor_u = PP_FLOOR_U;
    for (int p = 0; p < PP_N_PATCHES; ++p) m.center_pt[p] = pp_center_pt[p];

    printf("PAPPA AVR: atmtga328p @16MHz, RAM 2KB\n");
    timer_start();
    sei();                               // без этого ISR таймера не работает
    const int rc = pp_fit(&m);
    const unsigned long dt = timer_us();

    pp_print_report(&m, dt, rc);

    for (;;) {                           // дальше мигаем: видно на скриншоте
        PORTB ^= (1 << 5);
        for (volatile uint32_t i = 0; i < 200000UL; ++i) { }
    }
    return 0;
}
