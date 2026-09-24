#include "geometry_pipeline.h"
#include "patch_approximator.h"
#include <map>
#include <algorithm>
#include <iostream>
#include <iomanip>

GeometryPipeline::GeometryPipeline(double threshold_deriv,
                                   double mad_k,
                                   double z_threshold)
    : cleaner(threshold_deriv, mad_k, z_threshold) {}

std::vector<SectionResult> GeometryPipeline::process_batch(
    const std::vector<int>& section_ids,
    const std::vector<double>& heights,
    const std::vector<double>& angles,
    const std::vector<double>& radii)
{
    // Группируем индексы по section_id
    std::map<int, std::vector<size_t>> section_map;
    for (size_t i = 0; i < section_ids.size(); ++i) {
        section_map[section_ids[i]].push_back(i);
    }

    std::vector<SectionResult> batch_results;

    std::cout << "\n==================================================\n";
    std::cout << "СТАРТ ПОСЕКЦИОННОГО РАСЧЕТА ГЕОМЕТРИИ\n";
    std::cout << "==================================================\n";

    for (auto it = section_map.begin(); it != section_map.end(); ++it) {
        int sid = it->first;
        const std::vector<size_t>& indices = it->second;
        size_t n_points = indices.size();
        double height = heights[indices[0]];

        // Собираем (angle, radius, is_ideal?) в пары и СОРТИРУЕМ по углу
        std::vector<std::pair<double,double>> pts;
        pts.reserve(n_points);
        for (size_t j = 0; j < n_points; ++j) {
            pts.emplace_back(angles[indices[j]], radii[indices[j]]);
        }
        std::sort(pts.begin(), pts.end(),
                  [](const auto& a, const auto& b){ return a.first < b.first; });

std::cerr << "[gp] sec=" << sid
          << " n_points=" << n_points
          << " pts[0]=(" << pts[0].first << "," << pts[0].second << ")"
          << " pts[1]=(" << pts[1].first << "," << pts[1].second << ")"
          << " pts[2]=(" << pts[2].first << "," << pts[2].second << ")"
          << "\n";


        std::vector<double> sec_angles(n_points), sec_radii(n_points);
        for (size_t j = 0; j < n_points; ++j) {
            sec_angles[j] = pts[j].first;
            sec_radii[j]  = pts[j].second;
        }

        // Очистка
        std::vector<bool> outliers = cleaner.clean(sec_radii);
        size_t n_out = std::count(outliers.begin(), outliers.end(), true);

        std::vector<double> a_clean, r_clean;
        a_clean.reserve(n_points);
        r_clean.reserve(n_points);
        for (size_t j = 0; j < n_points; ++j) {
            if (!outliers[j]) {
                a_clean.push_back(sec_angles[j]);
                r_clean.push_back(sec_radii[j]);
            }
        }

        std::cout << "\n-> Сечение ID: " << sid << " (Высота: " << height << " мм)\n";
        std::cout << "   [Cleaner] Удалено выбросов: " << n_out << " из " << n_points
                  << " (" << std::fixed << std::setprecision(1)
                  << (100.0 * n_out / n_points) << "%)\n";

        if (a_clean.size() < 20) {
            std::cout << "   [Ошибка] Мало чистых точек, сечение пропущено.\n";
            continue;
        }

        // Fine
        PatchApproximator approx_fine(8, 4, 14, 180.0, 15.0, 5.0);
        approx_fine.fit(a_clean, r_clean);
        std::vector<double> fitted_fine = approx_fine.eval(sec_angles);
        std::vector<int> fine_degrees = approx_fine.get_degrees();

        // Coarse
        PatchApproximator approx_coarse(8, 4, 4, 180.0, 15.0, 5.0);
        approx_coarse.fit(a_clean, r_clean);
        std::vector<double> fitted_coarse = approx_coarse.eval(sec_angles);

        std::cout << "   [Fine] Степени патчей: [";
        for (size_t k = 0; k < fine_degrees.size(); ++k) {
            std::cout << fine_degrees[k] << (k + 1 == fine_degrees.size() ? "" : ", ");
        }
        std::cout << "]\n";

        SectionResult res;
        res.section_id   = sid;
        res.height_mm    = height;
        res.angles       = sec_angles;          // все углы (по порядку)
        res.radii_clean  = r_clean;             // только чистые (в том же порядке) — для совместимости
        res.outlier_mask = outliers;
        res.fitted_fine  = fitted_fine;         // НА sec_angles
        res.fitted_coarse= fitted_coarse;       // НА sec_angles
        res.degrees      = fine_degrees;

        batch_results.push_back(std::move(res));

        std::cout << "   [OK] Сечение рассчитано.\n";
    }
    std::cout << "==================================================\n";
    return batch_results;
}