// PAPPA, целочисленное ядро для микроконтроллеров (переносимое: AVR и x86).
//
// Идея (см. docs/embedded.md): вместо 6 факторизаций QR на патч — ОДНО накопление
// матрицы Грама в базисе Чебышёва. Работа падает ~15x, окно обучения хранить не
// надо, память O(p^2) на патч и не зависит от длины профиля.
//
// Целочисленность: T_k(x) считаются в Q24 (int32) по рекуррентной формуле,
// произведения — int64 (T_i*T_j <= 2^48, yc <= 3e5 в единицах 1e-5 мм), так что
// один 32x32->64 умножитель (umull/mull) на точку-столбец. Маленькая система
// (<= 9x9) решается во float: на AVR это soft-float, но это ~p^3/3 ~ 240 операций,
// на фоне накопления ничто. IEEE-754 single одинаков и на AVR, и на x86, поэтому
// результаты обязаны совпадать бит-в-бит.
//
// Важно (урок эксперимента): RMSE считается по ЯВНЫМ остаткам (Clenshaw), а не
// через Q - c^T b: иначе правило «локтя» принимает решения по вычитанию больших
// чисел. Плюс абсолютный пол floor_u: на гладких окнах RMSE уходит ниже любого
// разумного уровня, и без пола степень выбирает разрядность решателя, а не данные.
#ifndef PAPPA_INT_H
#define PAPPA_INT_H

#include <stdint.h>

// Чтение радиуса: на AVR сечение лежит во ФЛЕШЕ (экономия RAM), на хосте — в RAM.
#ifdef __AVR__
#include <avr/pgmspace.h>
#define PP_READ_U(p, i) ((int32_t)pgm_read_dword((p) + (i)))
#define PP_CONST        PROGMEM
#else
#define PP_READ_U(p, i) ((p)[i])
#define PP_CONST
#endif

#define PP_MAX_PATCHES 3
#define PP_MAX_DEG 8
#define PP_MAX_COLS (PP_MAX_DEG + 1)
#define PP_N_RMSE (PP_MAX_DEG / 2)  /* 4,6,8 -> 3 значения */

// Единицы: радиус хранится как int32 в единицах 1e-5 мм (0.01 мкм),
// угол неявный (равномерная сетка), координата окна x = (i - center)/half_train.
typedef float pp_real;

typedef struct {
    int n;                 // точек в сечении
    const int32_t *y_u;    // радиус, единицы 1e-5 мм
    int n_patches;         // 1..PP_MAX_PATCHES
    int center_pt[PP_MAX_PATCHES];   // центр патча в точках
    int half_train_pts;    // полуширина обучающего окна в точках
    int deg_min, deg_max;  // чётные степени
    int32_t floor_u;       // абсолютный пол RMSE (единицы 1e-5 мм)

    // выход
    int deg[PP_MAX_PATCHES];
    pp_real coef[PP_MAX_PATCHES][PP_MAX_COLS];   // ОТНОСИТЕЛЬНО yref_u; индексы x^j
    int32_t yref_u[PP_MAX_PATCHES];              // опорный радиус патча (единицы 1e-5 мм)
    pp_real rmse[PP_MAX_PATCHES][PP_N_RMSE];     // таблица RMSE по степеням, мм
    int n_rmse[PP_MAX_PATCHES];                  // сколько RMSE реально посчитано
    int n_train;                                 // точек в окне (для отчёта)
} pp_model;

// Обучить все патчи. Возврат: 0 — ок, <0 — ошибка параметров.
int pp_fit(pp_model *m);

#endif  // PAPPA_INT_H
