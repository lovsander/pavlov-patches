#include "auto_outlier_cleaner.h"

#include <algorithm>
#include <cmath>

#include "signal_tools.h"

namespace pappa {

std::vector<bool> AutoOutlierCleaner::clean(const std::vector<double>& angles,
                                            const std::vector<double>& radii) {
    const size_t n = radii.size();
    std::vector<bool> mask(n, false);
    info_ = CleanerInfo{};
    info_.iqr_k = iqr_k_;
    info_.n_total = static_cast<int>(n);

    const size_t min_pts = static_cast<size_t>(std::max(3, min_points_));
    if (n < min_pts) {
        info_.n_outliers = 0;
        return mask;
    }

    const int w = window_points(angles, baseline_deg_);
    const std::vector<double> baseline = median_filter_wrap(radii, w);
    std::vector<double> res(n, 0.0);
    for (size_t i = 0; i < n; ++i) res[i] = radii[i] - baseline[i];

    const double center = median(res);
    const double spread = iqr(res);
    const double sigma = robust_sigma(res);
    const double denom = (spread > 1e-12) ? spread : 1.0;

    std::vector<double> severity(n, 0.0);
    for (size_t i = 0; i < n; ++i) severity[i] = std::abs(res[i] - center) / denom;
    for (size_t i = 0; i < n; ++i) mask[i] = severity[i] > iqr_k_;

    // предохранитель: не отбрасываем больше max_removed_frac точек
    const size_t cap = static_cast<size_t>(std::floor(max_removed_frac_ * static_cast<double>(n)));
    size_t n_flagged = static_cast<size_t>(std::count(mask.begin(), mask.end(), true));
    if (cap > 0 && cap < n && n_flagged > cap) {
        std::vector<double> flagged;
        flagged.reserve(n_flagged);
        for (size_t i = 0; i < n; ++i) if (mask[i]) flagged.push_back(severity[i]);
        std::sort(flagged.begin(), flagged.end(), std::greater<double>());
        const double keep_level = flagged[cap - 1];
        for (size_t i = 0; i < n; ++i) mask[i] = mask[i] && (severity[i] >= keep_level);
    }

    info_.baseline_window_points = w;
    info_.baseline_window_deg = w * angular_step(angles);
    info_.sigma_res_mm = sigma;
    info_.iqr_res_mm = spread;
    info_.threshold_mm = iqr_k_ * spread;
    info_.n_outliers = static_cast<int>(std::count(mask.begin(), mask.end(), true));
    return mask;
}

}  // namespace pappa
