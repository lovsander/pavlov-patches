// Единый формат отчёта для хоста и для AVR. Печатаются ТОЛЬКО целые числа
// (без float-printf): на AVR это экономит килобайты флеша, а сравнение с
// референсом получается точным «в цифрах», без разбора текстовых дробей.
//
//   PATCH <патч> deg=<степень>
//   COEF  <патч> <c_i * 1e7 мм> ...   (от x^0; точность печати 1e-7 мм)
//   RMSE  <патч> <rmse * 1e9 мм> ...  (пикометры; таблица по степеням 4,6,8)
//   N_TRAIN <точек в окне>
//   TIME_US <время обучения на этом чипе, мкс>
//   PAPPA_DONE | PAPPA_FAIL
#ifndef PP_REPORT_H
#define PP_REPORT_H

#include <stdio.h>

#include "pappa_int.h"

// Коэффициент в единицах 1e-8 мм (0.1 нм). int32 вмещает |c| <= 21.47 мм;
// если больше — печатаем «переполнение» и это будет видно в отчёте.
static inline long pp_q_c(pp_real v) {
    const pp_real s = v * 1.0e8f;
    if (s > 2.0e9f) return 2000000000L;
    if (s < -2.0e9f) return -2000000000L;
    return (long)(s + (v < 0.0f ? -0.5f : 0.5f));
}
static inline long pp_q_r(pp_real v) { return (long)(v * 1.0e9f + 0.5f); }

static inline void pp_print_report(const pp_model *m, unsigned long time_us, int rc) {
    printf("SECTION n=%d half_train=%d floor_u=%ld\n", m->n, m->half_train_pts,
           (long)m->floor_u);
    for (int p = 0; p < m->n_patches; ++p) {
        printf("PATCH %d deg=%d\n", p, m->deg[p]);
        printf("YREF %d %ld\n", p, (long)m->yref_u[p]);
        printf("COEF %d", p);
        for (int j = 0; j <= m->deg[p]; ++j) printf(" %ld", pp_q_c(m->coef[p][j]));
        printf("\nRMSE %d", p);
        for (int t = 0; t < m->n_rmse[p]; ++t) printf(" %ld", pp_q_r(m->rmse[p][t]));
        printf("\n");
        // Коэффициенты Чебышёва (мм, k = 0..deg) — УСТОЙЧИВАЯ форма для сверки
        // кривой: мономиальные коэффициенты при большой степени плохо
        // обусловлены, и float32 в них теряет точность (см. docs/embedded.md §12).
        printf("CHEB %d", p);
        for (int k = 0; k < m->n_cheb[p]; ++k) printf(" %ld", pp_q_c(m->cheb[p][k]));
        printf("\n");
    }
    printf("N_TRAIN %d\n", m->n_train);
    printf("PHASE acc=%lu elbow=%lu final=%lu\n", (unsigned long)m->t_us[PP_PH_ACC],
           (unsigned long)m->t_us[PP_PH_ELBOW], (unsigned long)m->t_us[PP_PH_FINAL]);
    printf("TIME_US %lu\n", time_us);
    printf(rc == 0 ? "PAPPA_DONE\n" : "PAPPA_FAIL\n");
}

#endif  // PP_REPORT_H
