#include "outlier_cleaner.h"
#include <cmath>
#include <algorithm>
#include <stdexcept>

OutlierCleaner::OutlierCleaner(double threshold_deriv, double mad_k, double z_threshold)
    : threshold_deriv(threshold_deriv), mad_k(mad_k), z_threshold(z_threshold) {}

double OutlierCleaner::calculate_median(std::vector<double> v) const {
    if (v.empty()) return 0.0;
    size_t n = v.size();
    size_t mid = n / 2;
    if (n % 2 == 1) {
        std::nth_element(v.begin(), v.begin() + mid, v.end());
        return v[mid];
    } else {
        size_t mid1 = mid - 1;
        std::nth_element(v.begin(), v.begin() + mid1, v.end());
        double val1 = v[mid1];
        std::nth_element(v.begin(), v.begin() + mid, v.end());
        double val2 = v[mid];
        return (val1 + val2) / 2.0;
    }
}

std::vector<bool> OutlierCleaner::clean(const std::vector<double>& radii) const {
    size_t n = radii.size();
    std::vector<bool> mask(n, false);
    if (n < 3) return mask;

    double median_r = calculate_median(radii);
    std::vector<double> abs_dev(n);
    for (size_t i = 0; i < n; ++i) abs_dev[i] = std::abs(radii[i] - median_r);
    double mad = calculate_median(abs_dev);

    for (size_t i = 0; i < n; ++i) {
        double dr = (i == 0) ? (radii[i] - radii[n - 1]) : (radii[i] - radii[i - 1]);
        bool mask_deriv = std::abs(dr) > threshold_deriv;
        bool mask_mad = false;
        bool mask_z = false;
        
        if (mad > 0.0) {
            mask_mad = abs_dev[i] > (mad_k * mad);
            mask_z = (0.6745 * abs_dev[i] / mad) > z_threshold;
        }
        mask[i] = mask_deriv || mask_mad || mask_z;
    }
    return mask;
}

CleanerStats OutlierCleaner::stats(const std::vector<double>& angles, const std::vector<double>& radii) const {
    if (angles.size() != radii.size()) throw std::invalid_argument("Размеры массивов не совпадают.");
    size_t n = angles.size();
    int n_deriv = 0, n_mad = 0, n_z = 0, n_total_outliers = 0;

    double median_r = calculate_median(radii);
    std::vector<double> abs_dev(n);
    for (size_t i = 0; i < n; ++i) abs_dev[i] = std::abs(radii[i] - median_r);
    double mad = calculate_median(abs_dev);

    for (size_t i = 0; i < n; ++i) {
        double dr = (i == 0) ? (radii[i] - radii[n - 1]) : (radii[i] - radii[i - 1]);
        bool mask_deriv = std::abs(dr) > threshold_deriv;
        bool mask_mad = (mad > 0.0) && (abs_dev[i] > (mad_k * mad));
        bool mask_z = (mad > 0.0) && ((0.6745 * abs_dev[i] / mad) > z_threshold);

        if (mask_deriv) n_deriv++;
        if (mask_mad) n_mad++;
        if (mask_z) n_z++;
        if (mask_deriv || mask_mad || mask_z) n_total_outliers++;
    }
    double percent = n > 0 ? (100.0 * n_total_outliers / n) : 0.0;
    return CleanerStats{n, n_deriv, n_mad, n_z, n_total_outliers, percent, mad};
}

void OutlierCleaner::apply(const std::vector<double>& angles, const std::vector<double>& radii, 
                           std::vector<double>& angles_clean, std::vector<double>& radii_clean) const {
    std::vector<bool> mask = clean(radii);
    angles_clean.clear(); radii_clean.clear();
    for (size_t i = 0; i < angles.size(); ++i) {
        if (!mask[i]) {
            angles_clean.push_back(angles[i]); radii_clean.push_back(radii[i]);
        }
    }
}
