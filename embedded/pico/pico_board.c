// Плата RP2040: UART0 (GP0/GP1), таймер (мкс), светодиод GPIO25, заглушки newlib.
#include "pico_board.h"

#define REG(addr) (*(volatile uint32_t *)(addr))

// Адреса периферии RP2040 (даташит, 2.2 Address map)
#define RESETS_BASE      0x4000c000u
#define RESETS_RESET_CLR 0x3000u
#define RESETS_RESET_DONE 0x0008u
#define IO_BANK0_BASE    0x40014000u
#define UART0_BASE       0x40034000u
#define TIMER_BASE       0x40054000u
#define SIO_BASE         0xd0000000u

#define RESET_UART0      (1u << 22)
#define RESET_IO_BANK0   (1u << 5)
#define RESET_PADS_BANK0 (1u << 8)

void board_init(uint32_t baud) {
    REG(RESETS_BASE + RESETS_RESET_CLR) =
        RESET_UART0 | RESET_IO_BANK0 | RESET_PADS_BANK0;
    while ((REG(RESETS_BASE + RESETS_RESET_DONE) &
            (RESET_UART0 | RESET_IO_BANK0 | RESET_PADS_BANK0)) !=
           (RESET_UART0 | RESET_IO_BANK0 | RESET_PADS_BANK0)) { }

    REG(IO_BANK0_BASE + 0x004 + 8 * 0) = 2;      // GP0 -> UART0 TX
    REG(IO_BANK0_BASE + 0x004 + 8 * 1) = 2;      // GP1 -> UART0 RX

    const uint32_t peri = 125000000u;            // clk_peri после сброса
    const uint32_t div = (peri * 4u) / baud;
    REG(UART0_BASE + 0x024) = div >> 6;          // IBRD
    REG(UART0_BASE + 0x028) = div & 0x3f;        // FBRD
    REG(UART0_BASE + 0x02c) = 0x70;              // 8N1 + FIFO
    REG(UART0_BASE + 0x030) = 0x301;             // UARTEN|TXE|RXE

    REG(SIO_BASE + 0x024) = 1u << 25;            // OE_SET: светодиод
}

void board_putc(char c) {
    if (c == '\n') board_putc('\r');
    while (REG(UART0_BASE + 0x018) & (1u << 5)) { }   // TXFF
    REG(UART0_BASE + 0x000) = (uint32_t)(uint8_t)c;
}

void board_puts(const char *s) {
    while (*s) board_putc(*s++);
}

uint32_t board_us(void) { return REG(TIMER_BASE + 0x028); }   // TIMERAWL

void board_led_toggle(void) { REG(SIO_BASE + 0x01c) = 1u << 25; }  // OUT_XOR

// ---------------------------------------------------- заглушки newlib
#include <sys/stat.h>
#include <errno.h>

int _write(int fd, const char *buf, int len) {
    (void)fd;
    for (int i = 0; i < len; ++i) board_putc(buf[i]);
    return len;
}
int _read(int fd, char *buf, int len) { (void)fd; (void)buf; (void)len; return -1; }
int _close(int fd) { (void)fd; return -1; }
int _fstat(int fd, struct stat *st) { (void)fd; st->st_mode = S_IFCHR; return 0; }
int _isatty(int fd) { (void)fd; return 1; }
int _lseek(int fd, int off, int whence) { (void)fd; (void)off; (void)whence; return 0; }
int _getpid(void) { return 1; }
int _kill(int pid, int sig) { (void)pid; (void)sig; errno = EINVAL; return -1; }
void _exit(int code) { (void)code; for (;;) { } }

extern char _bss_end;
static char *g_heap = 0;
void *_sbrk(int incr) {
    if (!g_heap) g_heap = &_bss_end;
    char *prev = g_heap;
    g_heap += incr;
    return prev;                      // куча растёт вверх до стека (не проверяем)
}
