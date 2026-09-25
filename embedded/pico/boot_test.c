// Минимальный bring-up RP2040 (без Pico SDK): векторная таблица, UART0 на GP0/GP1,
// светодиод на GPIO25. Нужен, чтобы выяснить: грузит ли симулятор Wokwi образ
// без boot2-стадии и как принимает прошивку (elf/hex/uf2).
#include <stdint.h>

#define REG(addr) (*(volatile uint32_t *)(addr))

// ---- адреса периферии RP2040 (см. даташит, раздел 2.2 Address map)
#define RESETS_BASE     0x4000c000u
#define RESETS_RESET    0x0000u
#define RESETS_RESET_CLR 0x3000u
#define RESETS_RESET_DONE 0x0008u
#define IO_BANK0_BASE   0x40014000u
#define PADS_BANK0_BASE 0x4001c000u
#define UART0_BASE      0x40034000u
#define TIMER_BASE      0x40054000u
#define SIO_BASE        0xd0000000u

#define RESET_UART0    (1u << 22)
#define RESET_IO_BANK0 (1u << 5)
#define RESET_PADS_BANK0 (1u << 8)

extern uint32_t _stack_top;
extern uint32_t _data_load, _data_start, _data_end, _bss_start, _bss_end;

void reset_handler(void);

__attribute__((section(".vectors"), used))
const uint32_t g_vectors[48] = {
    (uint32_t)&_stack_top,          // 0: начальный SP (грузит железо)
    (uint32_t)reset_handler,        // 4: Reset
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,   // + прочие обработчики
};

static void uart0_init(uint32_t baud) {
    // снять сброс с UART0 / IO_BANK0 / PADS_BANK0
    REG(RESETS_BASE + RESETS_RESET_CLR) = RESET_UART0 | RESET_IO_BANK0 | RESET_PADS_BANK0;
    while ((REG(RESETS_BASE + RESETS_RESET_DONE) &
            (RESET_UART0 | RESET_IO_BANK0 | RESET_PADS_BANK0)) !=
           (RESET_UART0 | RESET_IO_BANK0 | RESET_PADS_BANK0)) { }
    // GP0 -> UART0 TX, GP1 -> UART0 RX (FUNCSEL = 2)
    REG(IO_BANK0_BASE + 0x004 + 8 * 0) = 2;
    REG(IO_BANK0_BASE + 0x004 + 8 * 1) = 2;
    // pad: сбросное значение 0x56 (IE=1, pull-up, 4 мА) годится и для RX, и для TX
    // clk_peri по умолчанию 125 МГц
    const uint32_t peri = 125000000u;
    const uint32_t div = (peri * 4u) / baud;         // (peri*4)/baud -> IBRD.frac
    REG(UART0_BASE + 0x024) = div >> 6;              // UARTIBRD
    REG(UART0_BASE + 0x028) = div & 0x3f;            // UARTFBRD
    REG(UART0_BASE + 0x02c) = 0x70;                  // LCR_H: 8 бит, FIFO
    REG(UART0_BASE + 0x030) = 0x301;                 // CR: UARTEN|TXE|RXE
}

static void uart_putc(char c) {
    while (REG(UART0_BASE + 0x018) & (1u << 5)) { }  // FR.TXFF
    REG(UART0_BASE + 0x000) = (uint32_t)c;           // DR
}

static void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

static void led_init(void) {
    REG(SIO_BASE + 0x024) = 1u << 25;                // OE_SET: GPIO25 на выход
}

static uint32_t timer_us(void) {
    return REG(TIMER_BASE + 0x028);                  // TIMERAWL (мкс)
}

void reset_handler(void) {
    uint32_t *src = &_data_load, *dst = &_data_start;
    while (dst < &_data_end) *dst++ = *src++;
    for (dst = &_bss_start; dst < &_bss_end; ) *dst++ = 0;

    uart0_init(115200);
    led_init();

    uart_puts("PICO bring-up: RP2040 @125MHz, no boot2\r\n");
    const uint32_t t0 = timer_us();
    volatile uint32_t x = 0;
    for (uint32_t i = 0; i < 100000u; ++i) x += i;   // короткая нагрузка
    const uint32_t dt = timer_us() - t0;
    uart_puts("BUSY_100K_US ");
    // печать целого
    char buf[12];
    int n = 0;
    uint32_t v = dt;
    if (!v) buf[n++] = '0';
    while (v) { buf[n++] = (char)('0' + (v % 10)); v /= 10; }
    while (n--) uart_putc(buf[n]);
    uart_puts("\r\nPICO_OK\r\n");

    for (;;) {
        REG(SIO_BASE + 0x01c) = 1u << 25;            // OUT_XOR: мигаем
        for (volatile uint32_t i = 0; i < 2000000u; ++i) { }
    }
}
