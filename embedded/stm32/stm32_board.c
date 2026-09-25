// STM32F103C8 (Blue Pill): RCC/GPIO/USART1 + DWT-счётчик тактов + заглушки newlib.
#include "stm32_board.h"

#define REG(addr) (*(volatile uint32_t *)(addr))

// Адреса периферии STM32F103 (RM0008, Table 3)
#define RCC_BASE     0x40021000u
#define FLASH_ACR    0x40022000u
#define GPIOA_BASE   0x40010800u
#define GPIOC_BASE   0x40011000u
#define USART1_BASE  0x40013800u
#define AFIO_BASE    0x40010000u

// RCC
#define RCC_CR       (RCC_BASE + 0x00u)
#define RCC_CFGR     (RCC_BASE + 0x04u)
#define RCC_APB2ENR  (RCC_BASE + 0x18u)
#define RCC_APB2RSTR (RCC_BASE + 0x0Cu)
#define APB2_AFIOEN   (1u << 0)
#define APB2_IOPAEN   (1u << 2)
#define APB2_IOPCEN   (1u << 4)
#define APB2_USART1EN (1u << 14)

// USART1
#define USART_SR  0x00u
#define USART_DR  0x04u
#define USART_BRR 0x08u
#define USART_CR1 0x0Cu
#define USART_TXE (1u << 7)

// DWT (ядро Cortex-M3)
#define DEMCR     0xE000EDFCu
#define DWT_CTRL  0xE0001000u
#define DWT_CYCCNT 0xE0001004u

void board_init(uint32_t baud) {
    // 1) часы: HSI (8 МГц) -> PLL: HSI/2 * 16 = 64 МГц
    REG(RCC_CR) |= (1u << 0);                       // HSION
    while (!(REG(RCC_CR) & (1u << 1))) { }          // HSIRDY
    REG(FLASH_ACR) = 0x12;                          // 2 wait state + prefetch
    REG(RCC_CFGR) &= ~(0xFu << 18);                 // PLLMUL = x16
    REG(RCC_CFGR) |= (0xEu << 18);
    REG(RCC_CFGR) &= ~(1u << 16);                   // PLLSRC = HSI/2
    REG(RCC_CFGR) &= ~((0xFu << 4) | (0x7u << 8) | (0x7u << 11));   // HPRE=1, PPRE=1
    REG(RCC_CR) |= (1u << 24);                      // PLLON
    while (!(REG(RCC_CR) & (1u << 25))) { }         // PLLRDY
    REG(RCC_CFGR) = (REG(RCC_CFGR) & ~0x3u) | 0x2u; // SW = PLL
    while (((REG(RCC_CFGR) >> 2) & 0x3u) != 0x2u) { }

    // 2) питание GPIO и USART
    REG(RCC_APB2ENR) |= APB2_AFIOEN | APB2_IOPAEN | APB2_IOPCEN | APB2_USART1EN;

    // 3) PA9 = USART1_TX (AF push-pull 50 МГц), PA10 = USART1_RX (floating input)
    uint32_t crh = REG(GPIOA_BASE + 0x04u);
    crh &= ~(0xFu << 4);
    crh |= (0xBu << 4);
    crh &= ~(0xFu << 8);
    crh |= (0x4u << 8);
    REG(GPIOA_BASE + 0x04u) = crh;

    // 4) PC13 = светодиод (выход push-pull 2 МГц, активен низким уровнем)
    uint32_t pcrh = REG(GPIOC_BASE + 0x04u);
    pcrh &= ~(0xFu << 20);
    pcrh |= (0x2u << 20);
    REG(GPIOC_BASE + 0x04u) = pcrh;
    board_led_set(0);

    // 5) USART1: 8N1
    const uint32_t div = (BOARD_SYSCLK_HZ + baud / 2u) / baud;   // BRR: mant<<4|frac
    REG(USART1_BASE + USART_BRR) = div;
    REG(USART1_BASE + USART_CR1) = (1u << 13) | (1u << 3) | (1u << 2);  // UE|TE|RE

    // 6) DWT: счётчик тактов
    REG(DEMCR) |= (1u << 24);
    REG(DWT_CYCCNT) = 0;
    REG(DWT_CTRL) |= 1u;
}

void board_putc(char c) {
    if (c == '\n') board_putc('\r');
    while (!(REG(USART1_BASE + USART_SR) & USART_TXE)) { }
    REG(USART1_BASE + USART_DR) = (uint32_t)(uint8_t)c;
}

void board_puts(const char *s) { while (*s) board_putc(*s++); }

void board_led_set(int on) {
    if (on) REG(GPIOC_BASE + 0x0Cu) &= ~(1u << 13);   // PC13 низкий = светит
    else    REG(GPIOC_BASE + 0x0Cu) |= (1u << 13);
}

uint32_t board_cycles(void) { return REG(DWT_CYCCNT); }

// ---------------------------------------------------- заглушки newlib
#include <errno.h>
#include <sys/stat.h>

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
    return prev;
}
