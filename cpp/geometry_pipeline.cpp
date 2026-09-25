#include "geometry_pipeline.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <map>

namespace pappa {

std::vector<SectionModel> GeometryPipeline::process(
    const std::vector<int>& section_ids, const std::vector<double>& heights,
    const std::vector<double>& angles, const std::vector<double>& radii) {
    const size_t n = section_ids.size();
    if (heights.size() != n || angles.size() != n || radii.size() != n) {
        throw std::invalid_argument("process: размеры массивов не совпадают");
    }
    if (opt_.pits) {
        throw std::runtime_error(
            "фичер ям в порту ещё не реализован (шаг 4b): запустите с --no-pits");
    }

    // Группировка по сечению
    std::map<int, std::vector<size_t>> by_section;
    for (size_t i = 0; i < n; ++i) by_section[section_ids[i]].push_back(i);

    std::vector<SectionModel> out;
    out.reserve(by_section.size());

    for (const auto& kv : by_section) {
        const int sid = kv.first;
        const std::vector<size_t>& idx = kv.second;

        // Сортировка по углу (кольцо считается замкнутым)
        std::vector<std::pair<double, double>> pts;
        pts.reserve(idx.size());
        for (size_t j : idx) pts.emplace_back(angles[j], radii[j]);
        std::sort(pts.begin(), pts.end(),
                  [](const std::pair<double, double>& a,
                     const std::pair<double, double>& b) { return a.first < b.first; });

        std::vector<double> a(pts.size()), r(pts.size());
        for (size_t j = 0; j < pts.size(); ++j) { a[j] = pts[j].first; r[j] = pts[j].second; }

        AutoOutlierCleaner cleaner(opt_.baseline_deg, opt_.iqr_k);
        const std::vector<bool> mask = cleaner.clean(a, r);

        std::vector<double> a_clean, r_clean;
        a_clean.reserve(a.size());
        r_clean.reserve(a.size());
        for (size_t j = 0; j < a.size(); ++j) {
            if (!mask[j]) { a_clean.push_back(a[j]); r_clean.push_back(r[j]); }
        }

        SectionModel section;
        section.section_id = sid;
        section.height_mm = heights[idx.front()];
        section.n_points_total = static_cast<int>(a.size());
        section.n_outliers = cleaner.info().n_outliers;

        const auto t0 = std::chrono::steady_clock::now();
        PatchApproximator model(opt_.n_patches, opt_.deg_min, opt_.deg_max,
                                opt_.amplitude_scale, opt_.overlap_train,
                                opt_.overlap_use, opt_.phase_deg,
                                opt_.deg_elbow_tol, "normalized");
        model.fit(a_clean, r_clean);
        section.fit_time_ms =
            std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0)
                .count();
        section.model = std::move(model);

        if (opt_.verbose) {
            std::cout << "  секция " << sid << " (h=" << section.height_mm
                      << " мм): точек " << section.n_points_total
                      << ", выброшено " << section.n_outliers
                      << ", окно очистки " << cleaner.info().baseline_window_points
                      << " точек, степени [";
            const std::vector<int> degs = section.model.get_degrees();
            for (size_t k = 0; k < degs.size(); ++k) {
                std::cout << degs[k] << (k + 1 == degs.size() ? "" : ", ");
            }
            std::cout << "], обучение " << section.fit_time_ms << " мс\n";
        }

        out.push_back(std::move(section));
    }
    return out;
}

}  // namespace pappa
