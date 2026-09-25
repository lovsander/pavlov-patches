#ifndef PAPPA_SIGNAL_TOOLS_H
#define PAPPA_SIGNAL_TOOLS_H

#include <vector>

// Сигнальные хелперы порта — ТОЧНОЕ повторение python/pappa/core/signal_tools.py.
//
// Критично для паритета: медиана и перцентили считаются как в numpy
// (линейная интерполяция для percentile, среднее двух центральных для чётной
// медианы). Если заменить их на «ближайший ранг», маска очистки сдвинется на
// несколько точек, степени патчей могут измениться, и сверка порта разойдётся
// — см. CONTEXT §8 и §27.

namespace pappa {

// Медиана (как np.median: для чётного n — среднее двух центральных).
double median(std::vector<double> v);

// Перцентиль с линейной интерполяцией (как np.percentile, метод "linear").
double percentile_linear(std::vector<double> v, double q);

// MAD = median(|x - median(x)|).
double mad(const std::vector<double>& x);

// Робастная sigma = 1.4826 * MAD.
double robust_sigma(const std::vector<double>& x);

// Межквартильный размах Q75 - Q25 (np.percentile).
double iqr(const std::vector<double>& x);

// Медианный шаг по углу, ° (перевод окон из градусов в точки).
double angular_step(const std::vector<double>& angles);

// Нечётное число точек, ближайшее к span_deg (>= 3, <= длины массива).
int window_points(const std::vector<double>& angles, double span_deg);

// Скользящая медиана по КОЛЬЦУ (профиль 0..360 замкнут).
std::vector<double> median_filter_wrap(const std::vector<double>& x, int window);

}  // namespace pappa

#endif  // PAPPA_SIGNAL_TOOLS_H
