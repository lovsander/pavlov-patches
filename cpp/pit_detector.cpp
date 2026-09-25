#include "pit_detector.h"

#include <algorithm>
#include <cmath>
#include <numeric>

#include "signal_tools.h"

namespace pappa {

std::vector<double> PitDetector::smooth_wrap(const std::vector<double>& x, int window) {
    const int n = static_cast<int>(x.size());
    int w = std::max(3, window | 1);
    if (n < 3 || w > n) w = (n % 2 == 1) ? n : std::max(1, n - 1);
    if (w < 3) return x;

    const int h = w / 2;
    std::vector<double> out(static_cast<size_t>(n), 0.0);
    for (int i = 0; i < n; ++i) {
        double s = 0.0;
        for (int k = -h; k <= h; ++k) {
            int idx = ((i + k) % n + n) % n;          // замыкание кольца
            s += x[static_cast<size_t>(idx)];
        }
        out[static_cast<size_t>(i)] = s / static_cast<double>(w);
    }
    return out;
}

std::vector<double> PitDetector::wrap_diff_abs(const std::vector<double>& x) {
    const size_t n = x.size();
    std::vector<double> out(n, 0.0);
    for (size_t i = 0; i < n; ++i) {
        const double next = x[(i + 1) % n];           // кольцо: последняя -> первая
        out[i] = std::abs(next - x[i]);
    }
    return out;
}

std::vector<double> PitDetector::band_indicator(const std::vector<double>& angles,
                                                const std::vector<double>& radii) const {
    const int w_narrow = window_points(angles, opt_.baseline_deg);
    const int w_wide = window_points(angles, opt_.wide_deg);
    const int w_smooth = window_points(angles, opt_.smooth_deg);

    const std::vector<double> baseline = median_filter_wrap(radii, w_narrow);
    const std::vector<double> wide = median_filter_wrap(radii, w_wide);

    std::vector<double> band(radii.size(), 0.0);
    for (size_t i = 0; i < radii.size(); ++i) {
        band[i] = std::abs(baseline[i] - wide[i]);
    }
    band = smooth_wrap(band, w_smooth);

    // нормировка на собственную робастную sigma (безразмерная шкала, «MAD-ы»)
    const double s = robust_sigma(band);
    if (s > 1e-12) {
        for (double& v : band) v /= s;
    } else {
        std::fill(band.begin(), band.end(), 0.0);
    }
    return band;
}

std::vector<std::pair<double, double>> PitDetector::mask_to_zones(
    const std::vector<double>& angles, const std::vector<bool>& mask) const {
    std::vector<std::pair<double, double>> zones;
    const size_t n = angles.size();
    if (n == 0 || std::none_of(mask.begin(), mask.end(), [](bool b) { return b; })) {
        return zones;
    }

    std::vector<double> diffs;
    diffs.reserve(n > 0 ? n - 1 : 0);
    for (size_t i = 1; i < n; ++i) diffs.push_back(angles[i] - angles[i - 1]);
    const double step = diffs.empty() ? 1.0 : median(diffs);

    size_t i = 0;
    while (i < n) {
        if (!mask[i]) { ++i; continue; }
        size_t j = i;
        while (j + 1 < n && mask[j + 1]) ++j;
        zones.emplace_back(angles[i] - step / 2.0, angles[j] + step / 2.0);
        i = j + 1;
    }

    // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
    if (zones.size() > 1 && mask.front() && mask.back()) {
        const std::pair<double, double> first = zones.front();
        const std::pair<double, double> last = zones.back();
        zones.erase(zones.begin());
        zones.pop_back();
        zones.insert(zones.begin(), {last.first - 360.0, first.second});
    }

    std::vector<std::pair<double, double>> out;
    for (const auto& z : zones) {
        if (z.second - z.first >= opt_.min_zone_deg) out.push_back(z);
    }
    return out;
}

std::vector<std::pair<double, double>> PitDetector::zones(
    const std::vector<double>& angles, const std::vector<double>& values) const {
    std::vector<bool> mask(values.size(), false);
    for (size_t i = 0; i < values.size(); ++i) mask[i] = values[i] > opt_.k;
    return mask_to_zones(angles, mask);
}

std::vector<double> PitDetector::pits(const std::vector<double>& angles,
                                      const std::vector<double>& radii) const {
    const std::vector<double> band = band_indicator(angles, radii);
    std::vector<double> out;
    for (const auto& z : zones(angles, band)) {
        out.push_back(0.5 * (z.first + z.second));
    }
    return out;
}

}  // namespace pappa
