// Хост-обвязка: тот же код ядра, что и в прошивке, только данные в RAM.
// Нужна, чтобы сверять «числа на чипе» с «числами на хосте» бит-в-бит,
// а числа на хосте — с референсом на Python (embedded/tools/check.py).
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "pappa_int.h"
#include "pp_report.h"
#include "section_data.h"

int main(void) {
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

    const clock_t t0 = clock();
    const int rc = pp_fit(&m);
    const double dt = (double)(clock() - t0) * 1.0e6 / (double)CLOCKS_PER_SEC;

    pp_print_report(&m, (unsigned long)dt, rc);
    return rc;
}
