#include "pappa_int.h"

#include <math.h>

// ------------------------------------------------------------------ константы
#define PP_SHIFT 24                       // Q24 для T_k
#define PP_ONE   ((int64_t)1 << PP_SHIFT)
#define PP_INV_2SHIFT 5.9604644775390625e-08f        /* 2^-24 как float */
#define PP_INV_2SHIFT2 3.55271367880050092936e-15f   /* 2^-48 как float */

// Мономиальные коэффициенты T_k(x) (целые, по убыванию степени) для k = 0..8.
// T_k — полиномы с целыми коэффициентами, поэтому переход Чебышёв -> мономы
// на устройстве ТОЧНЫЙ, без арифметики с плавающей точкой.
static const int16_t PP_TM[PP_MAX_COLS][PP_MAX_COLS] = {
    {1, 0, 0, 0, 0, 0, 0, 0, 0},
    {1, 0, 0, 0, 0, 0, 0, 0, 0},          /* T1 = x */
    {2, 0, -1, 0, 0, 0, 0, 0, 0},
    {4, 0, -3, 0, 0, 0, 0, 0, 0},
    {8, 0, -8, 0, 1, 0, 0, 0, 0},
    {16, 0, -20, 0, 5, 0, 0, 0, 0},
    {32, 0, -48, 0, 18, 0, -1, 0, 0},
    {64, 0, -112, 0, 56, 0, -7, 0, 0},
    {128, 0, -256, 0, 160, 0, -32, 0, 1},
};

// Ускоренный доступ к верхнему треугольнику Грама: индекс (a <= c).
static int pp_mi(int a, int c) { return a * PP_MAX_COLS - (a * (a - 1)) / 2 + (c - a); }
// (для PP_MAX_COLS = 9 это ровно 45 элементов)

// T_k(xq) для k = 0..deg_max, всё в Q24, значения — int32 (|T| <= 2^24).
// ВАЖНО для AVR: значения держим в int32, иначе произведение становится
// 64x64->64 (__muldi3, сотни циклов на точку) вместо 32x32->64 (__mulsi3).
static void pp_cheb_row(int32_t xq, int deg_max, int32_t *T) {
    T[0] = (int32_t)PP_ONE;
    if (deg_max >= 1) T[1] = xq;
    for (int k = 2; k <= deg_max; ++k)
        T[k] = (int32_t)(((int64_t)2 * T[k - 1] * xq) >> PP_SHIFT) - T[k - 2];
}

// Σ c_k T_k(x) по схеме Кленшоу (устойчиво, c в «единицах y_u»).
static pp_real pp_cheb_sum(const pp_real *c, int deg, pp_real x) {
    pp_real b1 = 0.0f, b2 = 0.0f;
    for (int k = deg; k >= 1; --k) {
        const pp_real b0 = 2.0f * x * b1 - b2 + c[k];
        b2 = b1;
        b1 = b0;
    }
    return x * b1 - b2 + c[0];
}

// Решить систему n x n (n <= 9) методом Гаусса с выбором главного элемента.
// A — расширенная матрица n x (n+1), перезаписывается; решение остаётся в A[i][n].
static void pp_solve(pp_real *A, int n) {
    for (int col = 0; col < n; ++col) {
        int piv = col;
        pp_real best = A[col * (n + 1) + col];
        if (best < 0) best = -best;
        for (int r = col + 1; r < n; ++r) {
            pp_real v = A[r * (n + 1) + col];
            if (v < 0) v = -v;
            if (v > best) { best = v; piv = r; }
        }
        for (int k = 0; k <= n; ++k) {
            const pp_real t = A[col * (n + 1) + k];
            A[col * (n + 1) + k] = A[piv * (n + 1) + k];
            A[piv * (n + 1) + k] = t;
        }
        const pp_real d = A[col * (n + 1) + col];
        for (int k = col; k <= n; ++k) A[col * (n + 1) + k] /= d;
        for (int r = 0; r < n; ++r) {
            if (r == col) continue;
            const pp_real f = A[r * (n + 1) + col];
            if (f == 0.0f) continue;
            for (int k = col; k <= n; ++k) A[r * (n + 1) + k] -= f * A[col * (n + 1) + k];
        }
    }
}

int pp_fit(pp_model *m) {
    if (!m || m->n <= 0 || m->half_train_pts <= 0) return -1;
    if (m->deg_min < 2 || m->deg_max > PP_MAX_DEG || (m->deg_max % 2) != 0) return -1;
    if (m->n_patches <= 0 || m->n_patches > PP_MAX_PATCHES) return -1;

    const int half = m->half_train_pts;
    const int ncol = m->deg_max + 1;
    m->n_train = 2 * half + 1;
    for (int i = 0; i < PP_N_PHASES; ++i) m->t_us[i] = 0;

    for (int p = 0; p < m->n_patches; ++p) {
        const int center = m->center_pt[p];

        // --- опорный радиус окна (для центрирования: иначе SSE теряет разряды)
        const int32_t yref = PP_READ_U(m->y_u, center);

        // --- накопление Грама и правой части
        int64_t M[(PP_MAX_COLS * (PP_MAX_COLS + 1)) / 2];
        int64_t b[PP_MAX_COLS];
        for (int k = 0; k < (PP_MAX_COLS * (PP_MAX_COLS + 1)) / 2; ++k) M[k] = 0;
        for (int k = 0; k < PP_MAX_COLS; ++k) b[k] = 0;

        const int nwin = 2 * half + 1;
        const uint32_t t_acc0 = PP_TICK();
        int32_t T[PP_MAX_COLS];
        for (int k = 0; k < nwin; ++k) {
            const int off = k - half;
            int i = center + off;
            while (i < 0) i += m->n;
            while (i >= m->n) i -= m->n;
            const int32_t xq = (int32_t)(((int64_t)off << PP_SHIFT) / half);  // Q24
            pp_cheb_row(xq, m->deg_max, T);
            const int32_t yc = (int32_t)(PP_READ_U(m->y_u, i) - yref);
            // Накопление БЕЗ сдвига: T <= 2^24, T*T <= 2^48, yc <= ~3e5,
            // T*yc <= ~5e12; при nwin <= 4096 суммы < 2^60 — int64 хватает.
            // Операнды int32 -> на AVR это 32x32->64 (одна пара mul), а не
            // 64x64->64 (__muldi3): разница на Uno примерно 50x.
            for (int a = 0; a < ncol; ++a) {
                b[a] += (int64_t)T[a] * yc;
                for (int c = a; c < ncol; ++c) M[pp_mi(a, c)] += (int64_t)T[a] * T[c];
            }
        }

        // --- правило «локтя»: RMSE по ЯВНЫМ остаткам (Clenshaw) + абсолютный пол
        m->t_us[PP_PH_ACC] += PP_TICK() - t_acc0;
        const uint32_t t_elb0 = PP_TICK();
        pp_real cf[PP_MAX_COLS];
        pp_real rmse_tab[PP_N_RMSE];
        for (int t = 0; t < PP_N_RMSE; ++t) rmse_tab[t] = 0.0f;
        int best_deg = m->deg_min;
        (void)best_deg;
        pp_real best = -1.0f;
        int sel = m->deg_min;
        int hit_floor = 0;
        int nr = 0;

        for (int deg = m->deg_min; deg <= m->deg_max; deg += 2) {
            const int nn = deg + 1;
            pp_real A[PP_MAX_COLS * (PP_MAX_COLS + 1)];
            for (int r = 0; r < nn; ++r) {
                for (int c = 0; c < nn; ++c) {
                    const int a = (r < c) ? r : c;
                    const int cc = (r < c) ? c : r;
                    A[r * (nn + 1) + c] = (pp_real)M[pp_mi(a, cc)] * PP_INV_2SHIFT2;
                }
                // b — уже в единицах y (шкала Q24 есть только у Грама)
                A[r * (nn + 1) + nn] = (pp_real)b[r] * PP_INV_2SHIFT;
            }
            pp_solve(A, nn);
            for (int k = 0; k < nn; ++k) cf[k] = A[k * (nn + 1) + nn];

            // явные остатки по точкам окна
            pp_real sse = 0.0f;
            for (int k = 0; k < nwin; ++k) {
                const int off = k - half;
                int i = center + off;
                while (i < 0) i += m->n;
                while (i >= m->n) i -= m->n;
                const pp_real x = (pp_real)off / (pp_real)half;
                const pp_real e =
                    pp_cheb_sum(cf, deg, x) - (pp_real)((int64_t)PP_READ_U(m->y_u, i) - yref);
                sse += e * e;
            }
            const pp_real rmse_u = sqrtf(sse / (pp_real)nwin);      // в единицах y_u
            rmse_tab[nr++] = rmse_u * 1.0e-5f;                     // в мм
            if (best < 0.0f || rmse_u < best) { best = rmse_u; best_deg = deg; }

            // абсолютный пол: «идеально точно» -> дальше степень не наращиваем
            if (rmse_u <= (pp_real)m->floor_u) { sel = deg; hit_floor = 1; break; }
        }

        if (!hit_floor) {
            const pp_real limit = best * 1.05f;   // допуск «локтя» 0.05
            for (int t = 0; t < nr; ++t) {
                if (rmse_tab[t] * 1.0e5f <= limit) { sel = m->deg_min + 2 * t; break; }
            }
        }

        // финальные коэффициенты выбранной степени (базис Чебышёва, единицы y_u)
        m->t_us[PP_PH_ELBOW] += PP_TICK() - t_elb0;
        const uint32_t t_fin0 = PP_TICK();
        {
            const int nn = sel + 1;
            pp_real A[PP_MAX_COLS * (PP_MAX_COLS + 1)];
            for (int r = 0; r < nn; ++r) {
                for (int c = 0; c < nn; ++c) {
                    const int a = (r < c) ? r : c;
                    const int cc = (r < c) ? c : r;
                    A[r * (nn + 1) + c] = (pp_real)M[pp_mi(a, cc)] * PP_INV_2SHIFT2;
                }
                A[r * (nn + 1) + nn] = (pp_real)b[r] * PP_INV_2SHIFT;
            }
            pp_solve(A, nn);
            for (int k = 0; k < nn; ++k) cf[k] = A[k * (nn + 1) + nn];
        }

        // Чебышёв -> мономиальные коэффициенты: T_k имеет ЦЕЛЫЕ коэффициенты,
        // поэтому переход точный (без плавающей точки на этом шаге).
        // ВАЖНО: коэффициенты — ОТНОСИТЕЛЬНО опорного радиуса yref. Если
        // прибавить сюда 15 мм, то ULP float32 при 15 мм равен ~1e-6 мм и
        // результат упрётся ровно в допуск метода; абсолютный радиус отдаётся
        // отдельным целым полем yref_u (его прибавляет хост в double).
        for (int j = 0; j <= sel; ++j) {
            pp_real acc = 0.0f;
            for (int k = j; k <= sel; ++k) acc += cf[k] * (pp_real)PP_TM[k][k - j];
            m->coef[p][j] = acc * 1.0e-5f;      // единицы 1e-5 мм -> мм
        }
        m->yref_u[p] = yref;
        m->n_cheb[p] = sel + 1;
        for (int k = 0; k <= sel; ++k) m->cheb[p][k] = cf[k] * 1.0e-5f;
        m->t_us[PP_PH_FINAL] += PP_TICK() - t_fin0;
        m->deg[p] = sel;
        m->n_rmse[p] = nr;
        for (int t = 0; t < PP_N_RMSE; ++t) m->rmse[p][t] = rmse_tab[t];
    }
    return 0;
}

