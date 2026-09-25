// PAPPA на C99 — реализация (см. c/pappa.h). Зависимости: только <math.h>.
#include "pappa.h"

#include <math.h>

// ------------------------------------------------------------------ утилиты
static void pp_sort(double *v, int n) {          // шеллсорт: без рекурсии и malloc
    for (int gap = n / 2; gap > 0; gap /= 2) {
        for (int i = gap; i < n; ++i) {
            const double t = v[i];
            int j = i;
            while (j >= gap && v[j - gap] > t) {
                v[j] = v[j - gap];
                j -= gap;
            }
            v[j] = t;
        }
    }
}

// Медиана (чётное n — среднее двух центральных), как np.median/std::nth_element.
static double pp_median(const double *x, int n, double *scratch) {
    if (n <= 0) return 0.0;
    for (int i = 0; i < n; ++i) scratch[i] = x[i];
    pp_sort(scratch, n);
    return (n % 2 == 1) ? scratch[n / 2]
                        : 0.5 * (scratch[n / 2 - 1] + scratch[n / 2]);
}

// Перцентиль с линейной интерполяцией (как numpy default / numpy.percentile).
static double pp_percentile_linear(const double *x, int n, double q,
                                   double *scratch) {
    if (n <= 0) return 0.0;
    for (int i = 0; i < n; ++i) scratch[i] = x[i];
    pp_sort(scratch, n);
    const double pos = (q / 100.0) * (double)(n - 1);
    const double lo_f = floor(pos);
    const double frac = pos - lo_f;
    const int lo = (int)lo_f;
    const int hi = (lo + 1 < n) ? lo + 1 : n - 1;
    return scratch[lo] + frac * (scratch[hi] - scratch[lo]);
}

static double pp_iqr(const double *x, int n, double *s1, double *s2) {
    if (n <= 0) return 0.0;
    return pp_percentile_linear(x, n, 75.0, s1) -
           pp_percentile_linear(x, n, 25.0, s2);
}

static double pp_mad(const double *x, int n, double *scratch, double *tmp) {
    if (n <= 0) return 0.0;
    const double m = pp_median(x, n, scratch);
    for (int i = 0; i < n; ++i) tmp[i] = fabs(x[i] - m);
    return pp_median(tmp, n, scratch);
}

static double pp_robust_sigma(const double *x, int n, double *scratch,
                              double *tmp) {
    return 1.4826 * pp_mad(x, n, scratch, tmp);
}

static double pp_angular_step(const double *angles, int n, double *scratch,
                              double *d) {
    if (n < 2) return 1.0;
    int m = 0;
    for (int i = 1; i < n; ++i) {
        const double step = angles[i] - angles[i - 1];
        if (step > 0.0) d[m++] = step;
    }
    if (m == 0) return 1.0;
    return pp_median(d, m, scratch);
}

// Ширина окна в точках: llround(span/шаг), нечётная, не шире профиля.
static int pp_window_points(const double *angles, int n, double span_deg,
                            double *scratch, double *d) {
    if (n < 3) return (n > 1) ? n : 1;
    const double step = pp_angular_step(angles, n, scratch, d);
    int w = (int)llround(span_deg / step);
    w |= 1;
    if (w < 3) w = 3;
    if (w > n) w = (n % 2 == 1) ? n : n - 1;
    return (w < 3) ? 3 : w;
}

// Медианный фильтр по кольцу (окно в точках).
static void pp_median_filter_wrap(const double *x, int n, int window, double *out,
                                  double *win, double *scratch) {
    int w = window | 1;
    if (w < 3) w = 3;
    if (w > n) w = (n % 2 == 1) ? n : n - 1;
    if (w < 3 || n < 3) {
        const double m = pp_median(x, n, scratch);
        for (int i = 0; i < n; ++i) out[i] = m;
        return;
    }
    const int h = w / 2;
    for (int i = 0; i < n; ++i) {
        for (int k = 0; k < w; ++k) {
            int idx = i - h + k;
            idx = ((idx % n) + n) % n;
            win[k] = x[idx];
        }
        out[i] = pp_median(win, w, scratch);
    }
}

// Скользящее среднее по кольцу (окно в точках).
static void pp_smooth_wrap(const double *x, int n, int window, double *out) {
    int w = window | 1;
    if (w < 3) w = 3;
    if (n < 3 || w > n) {
        if (n % 2 == 0) w = n - 1;
        else w = n;
    }
    if (w < 3) {
        for (int i = 0; i < n; ++i) out[i] = x[i];
        return;
    }
    const int h = w / 2;
    for (int i = 0; i < n; ++i) {
        double s = 0.0;
        for (int k = -h; k <= h; ++k) {
            int idx = ((i + k) % n + n) % n;
            s += x[idx];
        }
        out[i] = s / (double)w;
    }
}

// Кратчайшее расстояние по кольцу и локальная координата (как circ_dist/circ_local).
static double pp_circ_dist(double a, double b) {
    double d = fmod(a - b + 180.0, 360.0);
    if (d < 0.0) d += 360.0;
    return fabs(d - 180.0);
}

static double pp_circ_local(double a, double b) {
    double d = fmod(a - b + 180.0, 360.0);
    if (d < 0.0) d += 360.0;
    return d - 180.0;
}

static double pp_smoothstep(double t) {
    if (t < 0.0) return 0.0;
    if (t > 1.0) return 1.0;
    return t * t * (3.0 - 2.0 * t);
}

// Оконный гаусс как функция расстояния от центра ямы (pit_shape_deg).
static double pp_pit_shape_deg(const pp_model *m, double d_deg) {
    const double d = fabs(d_deg);
    const double val = exp(-d * d / (2.0 * m->sigma_deg * m->sigma_deg));
    if (!m->tapering) return val;
    const double core = m->core_sigma * m->sigma_deg;
    const double edge = m->window_sigma * m->sigma_deg;
    if (edge <= core) return val;
    double t = (edge - d) / (edge - core);
    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;
    return val * t * t * (3.0 - 2.0 * t);
}

// ------------------------------------------------------------------ линейка
// МНК через QR отражениями Хаусхолдера (как np.polyfit/lstsq): A — m×n, m >= n.
static int pp_lstsq_qr(double *A, int m, int n, double *b, double *x, double *v) {
    if (m < n) return -1;
    for (int k = 0; k < n; ++k) {
        double norm = 0.0;
        for (int i = k; i < m; ++i) norm += A[i * n + k] * A[i * n + k];
        norm = sqrt(norm);
        if (norm < 1e-300) continue;
        const double alpha = (A[k * n + k] > 0.0) ? -norm : norm;
        for (int i = k; i < m; ++i) v[i] = A[i * n + k];
        v[k] -= alpha;
        double vnorm2 = 0.0;
        for (int i = k; i < m; ++i) vnorm2 += v[i] * v[i];
        if (vnorm2 < 1e-300) continue;
        for (int j = k; j < n; ++j) {
            double s = 0.0;
            for (int i = k; i < m; ++i) s += v[i] * A[i * n + j];
            const double c = 2.0 * s / vnorm2;
            for (int i = k; i < m; ++i) A[i * n + j] -= c * v[i];
        }
        double sb = 0.0;
        for (int i = k; i < m; ++i) sb += v[i] * b[i];
        const double cb = 2.0 * sb / vnorm2;
        for (int i = k; i < m; ++i) b[i] -= cb * v[i];
    }
    for (int i = n - 1; i >= 0; --i) {
        double s = b[i];
        for (int j = i + 1; j < n; ++j) s -= A[i * n + j] * x[j];
        const double d = A[i * n + i];
        if (fabs(d) < 1e-300) return -1;
        x[i] = s / d;
    }
    return 0;
}

// Полином по нормированной координате: коэффициенты убывают по степени.
static double pp_polyval(const double *coefs, int n, double x) {
    double r = 0.0;
    for (int i = 0; i < n; ++i) r = r * x + coefs[i];
    return r;
}

// T_k(x) рекуррентно (базис Чебышёва, x ∈ [-1, 1]).
static void pp_cheb_row(double x, int deg_max, double *T) {
    T[0] = 1.0;
    if (deg_max >= 1) T[1] = x;
    for (int k = 2; k <= deg_max; ++k) T[k] = 2.0 * x * T[k - 1] - T[k - 2];
}

// Сумма Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
static double pp_cheb_sum(const double *c, int deg, double x) {
    double b1 = 0.0, b2 = 0.0;
    for (int k = deg; k >= 1; --k) {
        const double b0 = 2.0 * x * b1 - b2 + c[k];
        b2 = b1;
        b1 = b0;
    }
    return x * b1 - b2 + c[0];
}

// --------------------------------------------------------------- авто-очистка
int pp_clean_iqr(const double *angles, const double *radii, int n,
                 double baseline_deg, double iqr_k, unsigned char *mask,
                 int *n_outliers) {
    for (int i = 0; i < n; ++i) mask[i] = 0;
    if (n_outliers) *n_outliers = 0;
    if (n < 20 || n > PP_MAX_POINTS) return -1;   // min_points = 20

    static double scr[PP_MAX_POINTS];
    static double win[PP_MAX_POINTS], base[PP_MAX_POINTS];
    static double res[PP_MAX_POINTS], sev[PP_MAX_POINTS], tmp[PP_MAX_POINTS];
    static double d[PP_MAX_POINTS];

    const int w = pp_window_points(angles, n, baseline_deg, scr, d);
    pp_median_filter_wrap(radii, n, w, base, win, scr);
    for (int i = 0; i < n; ++i) res[i] = radii[i] - base[i];

    const double center = pp_median(res, n, scr);
    const double spread = pp_iqr(res, n, scr, tmp);
    const double denom = (spread > 1e-12) ? spread : 1.0;
    for (int i = 0; i < n; ++i) sev[i] = fabs(res[i] - center) / denom;
    for (int i = 0; i < n; ++i) mask[i] = (sev[i] > iqr_k) ? 1u : 0u;

    // Предохранитель: не выбрасываем больше max_removed_frac = 0.5 точек.
    const double max_removed_frac = 0.5;
    const int cap = (int)floor(max_removed_frac * (double)n);
    int n_flagged = 0;
    for (int i = 0; i < n; ++i) n_flagged += mask[i];
    if (cap > 0 && cap < n && n_flagged > cap) {
        int m = 0;
        for (int i = 0; i < n; ++i)
            if (mask[i]) tmp[m++] = sev[i];
        pp_sort(tmp, m);
        const double keep_level = tmp[m - cap];
        for (int i = 0; i < n; ++i)
            mask[i] = (mask[i] && sev[i] >= keep_level) ? 1u : 0u;
    }
    int cnt = 0;
    for (int i = 0; i < n; ++i) cnt += mask[i];
    if (n_outliers) *n_outliers = cnt;
    return 0;
}



// --------------------------------------------------------------- детектор ям
void pp_detector_defaults(pp_detector_cfg *c) {
    c->window_deg = 1.0;
    c->wide_deg = 10.0;
    c->smooth_deg = 2.0;
    c->k = 5.5;
    c->min_zone_deg = 2.0;
}

void pp_detector_band(const pp_detector_cfg *c, const double *angles,
                      const double *radii, int n, double *out) {
    static double scr[PP_MAX_POINTS], d[PP_MAX_POINTS], win[PP_MAX_POINTS];
    static double narrow[PP_MAX_POINTS], wide[PP_MAX_POINTS], band[PP_MAX_POINTS];
    const int w_narrow = pp_window_points(angles, n, c->window_deg, scr, d);
    const int w_wide = pp_window_points(angles, n, c->wide_deg, scr, d);
    const int w_smooth = pp_window_points(angles, n, c->smooth_deg, scr, d);

    pp_median_filter_wrap(radii, n, w_narrow, narrow, win, scr);
    pp_median_filter_wrap(radii, n, w_wide, wide, win, scr);
    for (int i = 0; i < n; ++i) band[i] = fabs(narrow[i] - wide[i]);
    pp_smooth_wrap(band, n, w_smooth, out);

    // Нормировка на собственную робастную sigma (безразмерная шкала в «MAD-ах»).
    const double s = pp_robust_sigma(out, n, scr, win);
    if (s > 1e-12) {
        for (int i = 0; i < n; ++i) out[i] /= s;
    } else {
        for (int i = 0; i < n; ++i) out[i] = 0.0;
    }
}

// Непрерывные зоны по маске: интервалы [начало, конец] в °.
static int pp_mask_to_zones(const pp_detector_cfg *c, const double *angles,
                            const unsigned char *mask, int n, double *zones) {
    int nz = 0, any = 0;
    for (int i = 0; i < n; ++i) any |= mask[i];
    if (!any) return 0;

    static double scr[PP_MAX_POINTS], diffs[PP_MAX_POINTS];
    int m = 0;
    for (int i = 1; i < n; ++i) diffs[m++] = angles[i] - angles[i - 1];
    const double step = (m > 0) ? pp_median(diffs, m, scr) : 1.0;

    int i = 0;
    while (i < n) {
        if (!mask[i]) { ++i; continue; }
        int j = i;
        while (j + 1 < n && mask[j + 1]) ++j;
        if (nz < PP_MAX_ZONES) {
            zones[2 * nz] = angles[i] - step / 2.0;
            zones[2 * nz + 1] = angles[j] + step / 2.0;
            ++nz;
        }
        i = j + 1;
    }

    // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
    if (nz > 1 && mask[0] && mask[n - 1]) {
        const double first_b = zones[1];
        const double last_a = zones[2 * (nz - 1)];
        for (int k = 0; k < 2 * (nz - 1); ++k) zones[k] = zones[k + 2];
        --nz;
        for (int k = 2 * nz; k > 2; --k) zones[k] = zones[k - 2];
        zones[0] = last_a - 360.0;
        zones[1] = first_b;
        ++nz;
    }

    int kept = 0;
    for (int k = 0; k < nz; ++k) {
        if (zones[2 * k + 1] - zones[2 * k] >= c->min_zone_deg) {
            zones[2 * kept] = zones[2 * k];
            zones[2 * kept + 1] = zones[2 * k + 1];
            ++kept;
        }
    }
    return kept;
}

int pp_detector_zones(const pp_detector_cfg *c, const double *angles,
                      const double *values, int n, double *zones_out) {
    static unsigned char mask[PP_MAX_POINTS];
    for (int i = 0; i < n; ++i) mask[i] = (values[i] > c->k) ? 1u : 0u;
    return pp_mask_to_zones(c, angles, mask, n, zones_out);
}

int pp_detector_pits(const pp_detector_cfg *c, const double *angles,
                     const double *radii, int n, double *pits_out) {
    static double band[PP_MAX_POINTS], zones[2 * PP_MAX_ZONES];
    pp_detector_band(c, angles, radii, n, band);
    const int nz = pp_detector_zones(c, angles, band, n, zones);
    for (int k = 0; k < nz; ++k)
        pits_out[k] = 0.5 * (zones[2 * k] + zones[2 * k + 1]);
    return nz;
}


// ------------------------------------------------------------------- модель
void pp_model_defaults(pp_model *m) {
    m->n_patches = 7;
    m->deg_min = 4;
    m->deg_max = 14;
    m->amplitude_scale = 180.0;
    m->overlap_train = 15.0;
    m->overlap_use = 5.0;
    m->phase_deg = 0.0;
    m->deg_elbow_tol = 0.05;
    m->coord_mode = "normalized";
    m->n_pits = 0;
    m->sigma_deg = 3.0;
    m->core_sigma = 2.0;
    m->window_sigma = 3.2;
    m->pit_min_amp = 3e-3;
    m->tapering = 1;
    m->is_fitted = 0;
}

void pp_model_set_pits(pp_model *m, const double *centers, int n) {
    m->n_pits = (n > PP_MAX_PITS) ? PP_MAX_PITS : n;
    for (int i = 0; i < m->n_pits; ++i) {
        double v = fmod(centers[i], 360.0);
        if (v < 0.0) v += 360.0;
        m->pits[i] = v;
    }
}

void pp_model_set_pit_shape(pp_model *m, double sigma_deg, double core_sigma,
                            double window_sigma, double pit_min_amp, int tapering) {
    m->sigma_deg = sigma_deg;
    m->core_sigma = core_sigma;
    m->window_sigma = window_sigma;
    m->pit_min_amp = pit_min_amp;
    m->tapering = tapering ? 1 : 0;
}

static double pp_half_sector(const pp_model *m) { return 180.0 / m->n_patches; }

static double pp_weight(const pp_model *m, double d_deg, double half_use) {
    const double hs = pp_half_sector(m);
    if (d_deg <= hs) return 1.0;
    if (d_deg <= half_use) {
        const double t = 1.0 - (d_deg - hs) / (half_use - hs);
        return pp_smoothstep(t);
    }
    return 0.0;
}

// Смещения видимых ям в локальной системе патча (°).
static int pp_pit_offsets(const pp_model *m, double center, double half_win,
                          double *out) {
    int n = 0;
    for (int i = 0; i < m->n_pits; ++i) {
        const double dx = pp_circ_local(m->pits[i], center);
        if (fabs(dx) <= half_win && n < PP_MAX_PITS) out[n++] = dx;
    }
    return n;
}

// Полином по x (коэффициенты убывают по степени) через QR — легаси raw-режим.
static int pp_polyfit(const double *x, const double *y, int n, int deg, double *out) {
    static double A[PP_MAX_WINDOW * (PP_MAX_DEG + 1)];
    static double b[PP_MAX_WINDOW], v[PP_MAX_WINDOW];
    if (n > PP_MAX_WINDOW) return -1;
    const int nn = deg + 1;
    for (int i = 0; i < n; ++i) {
        double p = 1.0;
        for (int j = 0; j < nn; ++j) {
            A[i * nn + (nn - 1 - j)] = p;
            p *= x[i];
        }
        b[i] = y[i];
    }
    return pp_lstsq_qr(A, n, nn, b, out, v);
}


// Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна не
// хуже лучшей более чем на deg_elbow_tol. Свип — одним накоплением Грама в
// базисе Чебышёва + явные остатки (быстрая ветка для coord_mode="normalized").
static int pp_estimate_degree(const pp_model *m, const double *angles,
                              const double *radii, int n, double center,
                              double *out_sel, double *out_best, int *out_ntrain) {
    static double xs[PP_MAX_POINTS], ys[PP_MAX_POINTS];
    const double half_train = pp_half_sector(m) + m->overlap_train;
    const int raw = (m->coord_mode && m->coord_mode[0] == 'r');

    int cnt = 0;
    for (int s = -1; s <= 1; ++s) {
        const double shift = 360.0 * (double)s;
        for (int i = 0; i < n; ++i) {
            const double dx = angles[i] + shift - center;
            if (dx >= -half_train && dx <= half_train && cnt < PP_MAX_POINTS) {
                xs[cnt] = raw ? dx : dx / half_train;
                ys[cnt] = radii[i];
                ++cnt;
            }
        }
    }
    *out_ntrain = cnt;
    *out_sel = 0.0;
    *out_best = 0.0;
    if (cnt < 5) return m->deg_min;

    int best_deg = m->deg_min, best_set = 0;
    double best = 0.0;
    int nres = 0;
    static int res_deg[PP_MAX_DEG + 1];
    static double res_rmse[PP_MAX_DEG + 1];

    if (raw) {
        static double coefs[PP_MAX_DEG + 1];
        for (int deg = m->deg_min; deg <= m->deg_max; deg += 2) {
            if (pp_polyfit(xs, ys, cnt, deg, coefs) != 0) continue;
            double sse = 0.0;
            for (int i = 0; i < cnt; ++i) {
                const double e = pp_polyval(coefs, deg + 1, xs[i]) - ys[i];
                sse += e * e;
            }
            const double r = sqrt(sse / (double)cnt);
            res_deg[nres] = deg;
            res_rmse[nres] = r;
            ++nres;
            if (!best_set || r < best) { best = r; best_deg = deg; best_set = 1; }
        }
    } else {
        const int dmax = m->deg_max;
        const int p = dmax + 1;
        static double gram[(PP_MAX_DEG + 1) * (PP_MAX_DEG + 1)];
        static double rhs[PP_MAX_DEG + 1], T[PP_MAX_DEG + 1];
        static double A[(PP_MAX_DEG + 1) * (PP_MAX_DEG + 1)];
        static double bv[PP_MAX_DEG + 1], v[PP_MAX_WINDOW];
        double yref = 0.0;
        for (int i = 0; i < cnt; ++i) yref += ys[i];
        yref /= (double)cnt;
        for (int i = 0; i < p * p; ++i) gram[i] = 0.0;
        for (int i = 0; i < p; ++i) rhs[i] = 0.0;
        for (int i = 0; i < cnt; ++i) {
            pp_cheb_row(xs[i], dmax, T);
            const double yc = ys[i] - yref;
            for (int a = 0; a < p; ++a) {
                rhs[a] += T[a] * yc;
                for (int c = a; c < p; ++c) gram[a * p + c] += T[a] * T[c];
            }
        }
        for (int a = 0; a < p; ++a)
            for (int c = a + 1; c < p; ++c) gram[c * p + a] = gram[a * p + c];

        for (int deg = m->deg_min; deg <= dmax; deg += 2) {
            const int nn = deg + 1;
            for (int r = 0; r < nn; ++r) {
                for (int c = 0; c < nn; ++c) A[r * nn + c] = gram[r * p + c];
                bv[r] = rhs[r];
            }
            if (pp_lstsq_qr(A, nn, nn, bv, T, v) != 0) continue;
            double sse = 0.0;
            for (int i = 0; i < cnt; ++i) {
                const double e = pp_cheb_sum(T, deg, xs[i]) - (ys[i] - yref);
                sse += e * e;
            }
            const double r = sqrt(sse / (double)cnt);
            res_deg[nres] = deg;
            res_rmse[nres] = r;
            ++nres;
            if (!best_set || r < best) { best = r; best_deg = deg; best_set = 1; }
        }
    }

    const double limit = best * (1.0 + m->deg_elbow_tol);
    int sel = best_deg;
    for (int k = 0; k < nres; ++k) {
        if (res_rmse[k] <= limit) { sel = res_deg[k]; break; }
    }
    *out_best = best;
    *out_sel = best;
    for (int k = 0; k < nres; ++k)
        if (res_deg[k] == sel) *out_sel = res_rmse[k];
    return sel;
}


// Обучение модели. Метрики документа (amplitude/mean/rmse_stats/correlation) в
// этой версии не считаются: конформанс-векторы проверяют степени, коэффициенты,
// термины фичера и контур — они и есть контракт метода. Метрики добавим вместе с
// писателем документа (следующий шаг C-порта).
void pp_model_fit(pp_model *m, const double *angles, const double *radii, int n) {
    static double ang_ext[PP_MAX_EXT], rad_ext[PP_MAX_EXT];
    static double xs[PP_MAX_WINDOW], ys[PP_MAX_WINDOW];
    static double A[PP_MAX_WINDOW * (PP_MAX_DEG + 1 + PP_MAX_PITS)];
    static double b[PP_MAX_WINDOW], v[PP_MAX_WINDOW];
    static double offs[PP_MAX_PITS], pcoef[PP_MAX_DEG + 1 + PP_MAX_PITS];
    static double keep_off[PP_MAX_PITS], keep_amp[PP_MAX_PITS];

    m->is_fitted = 0;
    if (n < 10 || n > PP_MAX_POINTS) return;

    const double sector = 360.0 / (double)m->n_patches;
    const double half_sector = sector / 2.0;
    const double half_train = half_sector + m->overlap_train;
    const double half_use = half_sector + m->overlap_use;
    const int raw = (m->coord_mode && m->coord_mode[0] == 'r');

    double centers[PP_MAX_PATCHES];
    for (int i = 0; i < m->n_patches; ++i) {
        double c = fmod((double)i * sector + half_sector + m->phase_deg, 360.0);
        if (c < 0.0) c += 360.0;
        centers[i] = c;
    }

    // Кольцо разворачиваем на ±360°, чтобы окна не рвались на 0/360.
    int ne = 0;
    for (int s = -1; s <= 1; ++s) {
        const double shift = 360.0 * (double)s;
        for (int i = 0; i < n && ne < PP_MAX_EXT; ++i) {
            ang_ext[ne] = angles[i] + shift;
            rad_ext[ne] = radii[i];
            ++ne;
        }
    }

    for (int p = 0; p < m->n_patches; ++p) {
        const double c = centers[p];
        double rmse_sel = 0.0, rmse_best = 0.0;
        int n_train = 0;
        const int deg = pp_estimate_degree(m, angles, radii, n, c, &rmse_sel,
                                           &rmse_best, &n_train);
        pp_patch *patch = &m->patches[p];
        patch->center = c;
        patch->half_sector = half_sector;
        patch->half_train = half_train;
        patch->half_use = half_use;
        patch->degree = deg;
        patch->n_pit = 0;
        patch->rmse_selected_mm = rmse_sel;
        patch->rmse_best_mm = rmse_best;

        int cnt = 0;
        for (int i = 0; i < ne && cnt < PP_MAX_WINDOW; ++i) {
            const double dx = ang_ext[i] - c;
            if (dx >= -half_train && dx <= half_train) {
                xs[cnt] = raw ? dx : dx / half_train;
                ys[cnt] = rad_ext[i];
                ++cnt;
            }
        }
        patch->n_points = cnt;
        if (cnt < 5) continue;

        const int npit = pp_pit_offsets(m, c, half_train, offs);
        const int ncol = deg + 1 + npit;
        for (int i = 0; i < cnt; ++i) {
            double pw = 1.0;
            for (int k = deg; k >= 0; --k) {
                A[i * ncol + k] = pw;
                pw *= xs[i];
            }
            for (int j = 0; j < npit; ++j) {
                const double dd = fabs(xs[i] - offs[j] / half_train) * half_train;
                A[i * ncol + deg + 1 + j] = pp_pit_shape_deg(m, dd);
            }
            b[i] = ys[i];
        }
        if (pp_lstsq_qr(A, cnt, ncol, b, pcoef, v) != 0) continue;

        // Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
        int nkeep = 0;
        for (int j = 0; j < npit; ++j) {
            double max_abs = 0.0;
            for (int i = 0; i < cnt; ++i) {
                const double dd = fabs(xs[i] - offs[j] / half_train) * half_train;
                const double t = fabs(pcoef[deg + 1 + j] * pp_pit_shape_deg(m, dd));
                if (t > max_abs) max_abs = t;
            }
            if (max_abs >= m->pit_min_amp) {
                keep_off[nkeep] = offs[j];
                keep_amp[nkeep] = pcoef[deg + 1 + j];
                ++nkeep;
            }
        }
        patch->n_pit = nkeep;
        for (int j = 0; j < nkeep; ++j) {
            patch->pit_off[j] = keep_off[j];
            patch->pit_amp[j] = keep_amp[j];
        }
        for (int k = 0; k <= deg; ++k) patch->coefs[k] = pcoef[k];
        for (int k = deg + 1; k <= PP_MAX_DEG; ++k) patch->coefs[k] = 0.0;
    }
    m->is_fitted = 1;
}


void pp_model_eval(const pp_model *m, const double *angles, int n, double *out) {
    const double half_use = pp_half_sector(m) + m->overlap_use;
    const int raw = (m->coord_mode && m->coord_mode[0] == 'r');
    for (int i = 0; i < n; ++i) {
        const double a = angles[i];
        double sum_wv = 0.0, sum_w = 0.0;
        for (int p = 0; p < m->n_patches; ++p) {
            const pp_patch *pt = &m->patches[p];
            const double w = pp_weight(m, pp_circ_dist(a, pt->center), half_use);
            if (w <= 0.0) continue;
            const double dx = pp_circ_local(a, pt->center);
            const double x = raw ? dx : dx / pt->half_train;
            double val = pp_polyval(pt->coefs, pt->degree + 1, x);
            for (int j = 0; j < pt->n_pit; ++j) {
                const double dd = fabs(x - pt->pit_off[j] / pt->half_train) *
                                  pt->half_train;
                val += pt->pit_amp[j] * pp_pit_shape_deg(m, dd);
            }
            sum_wv += w * val;
            sum_w += w;
        }
        out[i] = (sum_w > 0.0) ? (sum_wv / sum_w) : 0.0;
    }
}

// --------------------------------------------- плоский API для внешней проверки
// Проверка векторов идёт из Python через ctypes (python/studies/check_c_port.py):
// так не нужно маршалить структуры — только настроить конфиг и прочитать выход.
void pp_model_config(pp_model *m, int n_patches, int deg_min, int deg_max,
                     double phase_deg, double overlap_train, double overlap_use,
                     double deg_elbow_tol, int raw_mode) {
    pp_model_defaults(m);
    m->n_patches = n_patches;
    m->deg_min = deg_min;
    m->deg_max = deg_max;
    m->phase_deg = phase_deg;
    m->overlap_train = overlap_train;
    m->overlap_use = overlap_use;
    m->deg_elbow_tol = deg_elbow_tol;
    m->coord_mode = raw_mode ? "raw" : "normalized";
}

void pp_detector_config(pp_detector_cfg *c, double window_deg, double wide_deg,
                        double smooth_deg, double k, double min_zone_deg) {
    pp_detector_defaults(c);
    c->window_deg = window_deg;
    c->wide_deg = wide_deg;
    c->smooth_deg = smooth_deg;
    c->k = k;
    c->min_zone_deg = min_zone_deg;
}

// Сколько байт выделять под структуры (Python не знает их размеров).
long pp_model_size(void) { return (long)sizeof(pp_model); }
long pp_detector_cfg_size(void) { return (long)sizeof(pp_detector_cfg); }

// Чтение результатов без структур — по одному числу.
int pp_model_n_patches(const pp_model *m) { return m->n_patches; }
int pp_patch_degree(const pp_model *m, int i) { return m->patches[i].degree; }
int pp_patch_n_points(const pp_model *m, int i) { return m->patches[i].n_points; }
double pp_patch_center(const pp_model *m, int i) { return m->patches[i].center; }
double pp_patch_coef(const pp_model *m, int i, int k) {
    return m->patches[i].coefs[k];
}
int pp_patch_n_pit(const pp_model *m, int i) { return m->patches[i].n_pit; }
double pp_patch_pit_off(const pp_model *m, int i, int j) {
    return m->patches[i].pit_off[j];
}
double pp_patch_pit_amp(const pp_model *m, int i, int j) {
    return m->patches[i].pit_amp[j];
}
