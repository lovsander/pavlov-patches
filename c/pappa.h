// PAPPA на C99 — порт метода «как референс»: тот же базис, те же окна, тот же МНК
// (QR Хаусхолдера), тот же фичер оконных гауссовых ям, тот же детектор трещин и
// авто-очистка. Числа обязаны совпадать с Python/C++/Go в пределах допусков
// spec/conformance (контур 1e-6 мм, коэффициенты max(1e-8, 1e-9·|c|)).
//
// Зависимостей нет (только <math.h>): размеры — фиксированные массивы, никакого
// malloc, никакого JSON/файлового ввода-вывода. Векторы конформанса подаются
// генератором python/studies/make_conformance_c.py как статические массивы
// (см. c/vectors_data.h), поэтому C-проверка читает уже готовые числа.
//
// Внутри — наработки из embedded-экспериментов: свип степеней сделан ОДНИМ
// накоплением матрицы Грама в базисе Чебышёва (префиксное свойство), RMSE по
// явным остаткам (Кленшоу), данные центрируются. Легаси-режим coord_mode="raw"
// оставлен на прежнем пути (базис Чебышёва требует x ∈ [-1, 1]).
#ifndef PAPPA_C_H
#define PAPPA_C_H

#include <stddef.h>

#define PP_MAX_POINTS  4096
#define PP_MAX_WINDOW  1024      // точек в обучающем окне патча (хватает с запасом)
#define PP_MAX_EXT     (3 * PP_MAX_POINTS)   // кольцо, развёрнутое на ±360°
#define PP_MAX_PATCHES 32
#define PP_MAX_DEG     20
#define PP_MAX_PITS    16
#define PP_MAX_ZONES   64

// ------------------------------------------------------------------ модель
typedef struct {
    double center;                    // °, глобальный угол центра патча
    double half_sector, half_train, half_use;
    double coefs[PP_MAX_DEG + 1];     // полином, старшая степень первая
    int degree, n_points;
    double pit_off[PP_MAX_PITS];      // смещения видимых ям, ° (в системе патча)
    double pit_amp[PP_MAX_PITS];
    int n_pit;
    // метрики документа
    double amplitude_mm, amplitude_norm, mean_radius_mm;
    double rmse_selected_mm, rmse_best_mm;
    double rmse_mm, mae_mm, max_err_mm, correlation;
} pp_patch;

typedef struct {
    int n_patches, deg_min, deg_max;
    double amplitude_scale, overlap_train, overlap_use, phase_deg, deg_elbow_tol;
    const char *coord_mode;           // "normalized" (по умолчанию) или "raw"
    // фичер ям
    double pits[PP_MAX_PITS];
    int n_pits;
    double sigma_deg, core_sigma, window_sigma, pit_min_amp;
    int tapering;
    // выход
    pp_patch patches[PP_MAX_PATCHES];
    int is_fitted;
} pp_model;

void pp_model_defaults(pp_model *m);
void pp_model_set_pits(pp_model *m, const double *centers, int n);
void pp_model_set_pit_shape(pp_model *m, double sigma_deg, double core_sigma,
                            double window_sigma, double pit_min_amp, int tapering);
// Обучение по точкам сечения (порядок — как пришёл; функция сама не сортирует).
void pp_model_fit(pp_model *m, const double *angles, const double *radii, int n);
// Контур: нормированное smoothstep-смешивание патчей (partition of unity).
void pp_model_eval(const pp_model *m, const double *angles, int n, double *out);

// ------------------------------------------------------------- детектор ям
typedef struct {
    double window_deg;      // узкая медиана (1.0)
    double wide_deg;        // широкая медиана (10.0)
    double smooth_deg;      // сглаживание индикатора (2.0)
    double k;               // порог в MAD-ах (5.5)
    double min_zone_deg;    // минимальная длина зоны (2.0)
} pp_detector_cfg;

void pp_detector_defaults(pp_detector_cfg *c);
// Индикатор band (безразмерный, MAD-единицы) в out (длина n).
void pp_detector_band(const pp_detector_cfg *c, const double *angles,
                      const double *radii, int n, double *out);
// Зоны (пары «начало, конец» в °) и их число.
int pp_detector_zones(const pp_detector_cfg *c, const double *angles,
                      const double *values, int n, double *zones_out);
// Центры ям (°) — середины зон.
int pp_detector_pits(const pp_detector_cfg *c, const double *angles,
                     const double *radii, int n, double *pits_out);

// --------------------------------------------------------------- очистка
// Авто-очистка по IQR (Tukey): маска длиной n (1 = выброс).
int pp_clean_iqr(const double *angles, const double *radii, int n,
                 double baseline_deg, double iqr_k, unsigned char *mask,
                 int *n_outliers);

// ------------------------------- плоский API для внешней проверки (ctypes)
void pp_model_config(pp_model *m, int n_patches, int deg_min, int deg_max,
                     double phase_deg, double overlap_train, double overlap_use,
                     double deg_elbow_tol, int raw_mode);
void pp_detector_config(pp_detector_cfg *c, double window_deg, double wide_deg,
                        double smooth_deg, double k, double min_zone_deg);
long pp_model_size(void);
long pp_detector_cfg_size(void);
int pp_model_n_patches(const pp_model *m);
int pp_patch_degree(const pp_model *m, int i);
int pp_patch_n_points(const pp_model *m, int i);
double pp_patch_center(const pp_model *m, int i);
double pp_patch_coef(const pp_model *m, int i, int k);
int pp_patch_n_pit(const pp_model *m, int i);
double pp_patch_pit_off(const pp_model *m, int i, int j);
double pp_patch_pit_amp(const pp_model *m, int i, int j);

#endif  // PAPPA_C_H
