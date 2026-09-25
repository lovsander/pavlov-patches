// PAPPA: C-пайплайн (CSV -> числа модели по сечениям).
//
// Печатает ПЛОСКИЙ текст: конфиг, по сечениям — метаданные и по патчам —
// степень/метрики/коэффициенты/термины фичера. Документ .pappa.json из этих
// чисел собирает хост (та же архитектура, что рекомендована для MCU в
// docs/embedded.md §7: устройство отдаёт числа, формат — на хосте).
//
// Запуск: pappa_c --input FILE.csv [--out FILE.txt]
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "pappa.h"

#define MAX_SECTIONS 64
#define MAX_COLS 32
#define LINE_MAX 4096

typedef struct {
    int id;
    double height;
    double angles[PP_MAX_POINTS];
    double radii[PP_MAX_POINTS];
    int n;
} pp_section;

static pp_section g_sec[MAX_SECTIONS];
static int g_nsec = 0;

// Разбор CSV по заголовку: нужны section_id, height_mm, angle_deg, radius_mm.
static int load_csv(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    char line[LINE_MAX];
    if (!fgets(line, sizeof(line), f)) { fclose(f); return -1; }
    int i_sec = -1, i_h = -1, i_a = -1, i_r = -1, ncol = 0;
    char *cols[MAX_COLS];
    {
        char *p = line, *tok = line;
        while (*p) {
            if (*p == ',' || *p == '\n' || *p == '\r') {
                *p = 0;
                if (ncol < MAX_COLS) cols[ncol++] = tok;
                tok = p + 1;
            }
            ++p;
        }
        if (ncol < MAX_COLS) cols[ncol++] = tok;
    }
    for (int i = 0; i < ncol; ++i) {
        if (!strncmp(cols[i], "section_id", 10)) i_sec = i;
        else if (!strncmp(cols[i], "height_mm", 9)) i_h = i;
        else if (!strncmp(cols[i], "angle_deg", 9)) i_a = i;
        else if (!strncmp(cols[i], "radius_mm", 9)) i_r = i;
    }
    if (i_sec < 0 || i_h < 0 || i_a < 0 || i_r < 0) { fclose(f); return -2; }

    while (fgets(line, sizeof(line), f)) {
        char *fld[MAX_COLS];
        int n = 0;
        char *p = line, *tok = line;
        while (*p) {
            if (*p == ',' || *p == '\n' || *p == '\r') {
                *p = 0;
                if (n < MAX_COLS) fld[n++] = tok;
                tok = p + 1;
            }
            ++p;
        }
        if (n == 0 || fld[0][0] == 0) continue;
        if (i_sec >= n || i_h >= n || i_a >= n || i_r >= n) continue;
        const int sid = atoi(fld[i_sec]);
        int idx = -1;
        for (int i = 0; i < g_nsec; ++i)
            if (g_sec[i].id == sid) { idx = i; break; }
        if (idx < 0) {
            if (g_nsec >= MAX_SECTIONS) continue;
            idx = g_nsec++;
            g_sec[idx].id = sid;
            g_sec[idx].height = atof(fld[i_h]);
            g_sec[idx].n = 0;
        }
        if (g_sec[idx].n < PP_MAX_POINTS) {
            g_sec[idx].angles[g_sec[idx].n] = atof(fld[i_a]);
            g_sec[idx].radii[g_sec[idx].n] = atof(fld[i_r]);
            ++g_sec[idx].n;
        }
    }
    fclose(f);
    return g_nsec;
}

// Сортировка точек сечения по углу (как sort_values в пайплайне).
static void sort_section(pp_section *s) {
    for (int i = 1; i < s->n; ++i) {
        const double ka = s->angles[i], kr = s->radii[i];
        int j = i - 1;
        while (j >= 0 && s->angles[j] > ka) {
            s->angles[j + 1] = s->angles[j];
            s->radii[j + 1] = s->radii[j];
            --j;
        }
        s->angles[j + 1] = ka;
        s->radii[j + 1] = kr;
    }
}


int main(int argc, char **argv) {
    const char *input = NULL, *out = NULL;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--input") && i + 1 < argc) input = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
    }
    if (!input) {
        printf("PAPPA (C): нужен --input FILE.csv [--out FILE.txt]\n");
        return 2;
    }
    if (load_csv(input) < 0) {
        printf("не прочитать CSV: %s\n", input);
        return 2;
    }
    FILE *fo = out ? fopen(out, "wb") : stdout;
    if (!fo) return 2;

    fprintf(fo, "CONFIG n_patches=7 phase_deg=24.75 deg_min=4 deg_max=14 "
                "overlap_train=15 overlap_use=5 deg_elbow_tol=0.05 "
                "baseline_deg=1 iqr_k=3 "
                "detector_window=1 wide=10 smooth=2 k=5.5 min_zone=2\n");

    static unsigned char mask[PP_MAX_POINTS];
    static double ca[PP_MAX_POINTS], cr[PP_MAX_POINTS], pits[PP_MAX_PITS];
    static pp_model model;
    static pp_detector_cfg det;

    for (int si = 0; si < g_nsec; ++si) {
        pp_section *s = &g_sec[si];
        sort_section(s);

        int n_out = 0;
        pp_clean_iqr(s->angles, s->radii, s->n, 1.0, 3.0, mask, &n_out);
        int cn = 0;
        for (int i = 0; i < s->n && cn < PP_MAX_POINTS; ++i) {
            if (!mask[i]) {
                ca[cn] = s->angles[i];
                cr[cn] = s->radii[i];
                ++cn;
            }
        }

        pp_detector_config(&det, 1.0, 10.0, 2.0, 5.5, 2.0);
        const int npits = pp_detector_pits(&det, ca, cr, cn, pits);

        pp_model_config(&model, 7, 4, 14, 24.75, 15.0, 5.0, 0.05, 0);
        if (npits > 0) {
            pp_model_set_pit_shape(&model, 3.0, 2.0, 3.2, 3e-3, 1);
            pp_model_set_pits(&model, pits, npits);
        }
        pp_model_fit(&model, ca, cr, cn);

        fprintf(fo, "SECTION id=%d height=%.17g n_points=%d n_used=%d n_outliers=%d "
                    "n_pits=%d", s->id, s->height, s->n, cn, n_out, npits);
        for (int k = 0; k < npits; ++k) fprintf(fo, " pit=%.17g", pits[k]);
        fprintf(fo, "\n");

        for (int p = 0; p < model.n_patches; ++p) {
            const pp_patch *pt = &model.patches[p];
            fprintf(fo, "PATCH sec=%d idx=%d center=%.17g half_train=%.17g half_use=%.17g "
                        "degree=%d n_points=%d rmse_sel=%.17g rmse_best=%.17g rmse=%.17g "
                        "mae=%.17g max_err=%.17g corr=%.17g amp=%.17g amp_norm=%.17g "
                        "mean_r=%.17g\n",
                    s->id, p, pt->center, pt->half_train, pt->half_use, pt->degree,
                    pt->n_points, pt->rmse_selected_mm, pt->rmse_best_mm, pt->rmse_mm,
                    pt->mae_mm, pt->max_err_mm, pt->correlation, pt->amplitude_mm,
                    pt->amplitude_norm, pt->mean_radius_mm);
            fprintf(fo, "COEF sec=%d idx=%d", s->id, p);
            for (int k = 0; k <= pt->degree; ++k)
                fprintf(fo, " %.17g", pt->coefs[k]);
            fprintf(fo, "\nPIT sec=%d idx=%d n=%d", s->id, p, pt->n_pit);
            for (int k = 0; k < pt->n_pit; ++k)
                fprintf(fo, " %.17g %.17g", pt->pit_off[k], pt->pit_amp[k]);
            fprintf(fo, "\n");
        }
    }
    if (fo != stdout) fclose(fo);
    printf("сечений: %d\n", g_nsec);
    return 0;
}
