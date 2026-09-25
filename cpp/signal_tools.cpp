#include "signal_tools.h"

#include <algorithm>
#include <cmath>

namespace pappa {

double median(std::vector<double> v) {
    if (v.empty()) return 0.0;
    const size_t n = v.size();
    const size_t mid = n / 2;
    std::nth_element(v.begin(), v.begin() + static_cast<long>(mid), v.end());
    const double hi = v[mid];
    if (n % 2 == 1) return hi;
    std::nth_element(v.begin(), v.begin() + static_cast<long>(mid - 1), v.end());
    const double lo = v[mid - 1];
    return 0.5 * (lo + hi);
}

double percentile_linear(std::vector<double> v, double q) {
    if (v.empty()) return 0.0;
    std::sort(v.begin(), v.end());
    const double pos = (q / 100.0) * static_cast<double>(v.size() - 1);
    const double lo_f = std::floor(pos);
    const double frac = pos - lo_f;
    const size_t lo = static_cast<size_t>(lo_f);
    const size_t hi = std::min(lo + 1, v.size() - 1);
    return v[lo] + frac * (v[hi] - v[lo]);
}

double mad(const std::vector<double>& x) {
    if (x.empty()) return 0.0;
    const double m = median(x);
    std::vector<double> dev(x.size());
    for (size_t i = 0; i < x.size(); ++i) dev[i] = std::abs(x[i] - m);
    return median(dev);
}

double robust_sigma(const std::vector<double>& x) { return 1.4826 * mad(x); }

double iqr(const std::vector<double>& x) {
    if (x.empty()) return 0.0;
    return percentile_linear(x, 75.0) - percentile_linear(x, 25.0);
}

double angular_step(const std::vector<double>& angles) {
    if (angles.size() < 2) return 1.0;
    std::vector<double> d;
    d.reserve(angles.size() - 1);
    for (size_t i = 1; i < angles.size(); ++i) {
        const double step = angles[i] - angles[i - 1];
        if (step > 0.0) d.push_back(step);
    }
    return d.empty() ? 1.0 : median(d);
}

int window_points(const std::vector<double>& angles, double span_deg) {
    const int n = static_cast<int>(angles.size());
    if (n < 3) return std::max(1, n);
    int w = static_cast<int>(std::llround(span_deg / angular_step(angles)));
    w = std::max(3, w | 1);                       // нечётное
    if (w > n) w = (n % 2 == 1) ? n : n - 1;
    return std::max(3, w);
}

std::vector<double> median_filter_wrap(const std::vector<double>& x, int window) {
    const int n = static_cast<int>(x.size());
    int w = std::max(3, window | 1);
    if (w > n) w = (n % 2 == 1) ? n : n - 1;
    if (w < 3 || n < 3) {
        std::vector<double> out(static_cast<size_t>(std::max(n, 0)), median(x));
        return out;
    }
    const int h = w / 2;
    std::vector<double> out(static_cast<size_t>(n), 0.0);
    std::vector<double> win(static_cast<size_t>(w), 0.0);
    for (int i = 0; i < n; ++i) {
        for (int k = 0; k < w; ++k) {
            int idx = i - h + k;
            idx = ((idx % n) + n) % n;            // замыкание кольца
            win[static_cast<size_t>(k)] = x[static_cast<size_t>(idx)];
        }
        out[static_cast<size_t>(i)] = median(win);
    }
    return out;
}

}  // namespace pappa
