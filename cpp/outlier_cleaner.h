// LEGACY: ручной чистильщик выбросов (fixed thresholds) — так работал
// исторический пайплайн. НЕ входит в сборку (см. cpp/CMakeLists.txt): штатный
// режим порта — авто-iqr (cpp/auto_outlier_cleaner.h).
//
// Почему оставлен: нужен для сверки с историческими числами и для повторения
// старых замеров (CONTEXT §13). В ручном режиме отклонение считается от
// ГЛОБАЛЬНОЙ медианы, поэтому дно глубокой ямы выглядит как выброс — именно
// поэтому в Python пайплайн перешёл на авто-режим.

#ifndef OUTLIER_CLEANER_H
#define OUTLIER_CLEANER_H

#include <vector>

struct CleanerStats {
    size_t n_total;
    int n_deriv;
    int n_mad;
    int n_z;
    int n_total_outliers;
    double percent_outliers;
    double mad_value;
};

class OutlierCleaner {
private:
    double threshold_deriv;
    double mad_k;
    double z_threshold;

    double calculate_median(std::vector<double> v) const;

public:
    OutlierCleaner(double threshold_deriv = 0.5, double mad_k = 9.5, double z_threshold = 3.5);

    std::vector<bool> clean(const std::vector<double>& radii) const;
    CleanerStats stats(const std::vector<double>& angles, const std::vector<double>& radii) const;
    void apply(const std::vector<double>& angles, const std::vector<double>& radii, 
               std::vector<double>& angles_clean, std::vector<double>& radii_clean) const;
};

#endif // OUTLIER_CLEANER_H
