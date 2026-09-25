#ifndef PAPPA_GEOMETRY_PIPELINE_H
#define PAPPA_GEOMETRY_PIPELINE_H

#include <string>
#include <vector>

#include "auto_outlier_cleaner.h"
#include "patch_approximator.h"
#include "section_model.h"

// Посекционный пайплайн порта: CSV -> очистка -> модель сечения -> документ.
//
// Порядок и параметры совпадают с Python (python/studies/build_sample.py и
// pappa/io/dataset.py), чтобы папки образцов были сравнимы:
//   1. группировка точек по section_id и сортировка по углу;
//   2. авто-очистка выбросов (метод iqr: остатки к локальному медианному уровню,
//      усы Тьюки 3.0 — см. pappa/core/outlier_cleaner.py);
//   3. обучение модели: N патчей (по умолчанию 7), общая фаза 24.75°,
//      правило степени «локоть», фичер ям (шаг 4b);
//   4. сведения для документа: число точек, сколько выброшено, время обучения.

namespace pappa {

struct PipelineOptions {
    // раскладка и правило степени (MODEL_DEFAULTS в Python)
    int n_patches = 7;
    double phase_deg = 24.75;
    int deg_min = 4;
    int deg_max = 14;
    double overlap_train = 15.0;
    double overlap_use = 5.0;
    double deg_elbow_tol = 0.05;
    double amplitude_scale = 180.0;

    // чистильщик (авто-iqr — штатный режим пайплайна)
    std::string cleaner = "iqr";
    double baseline_deg = 1.0;
    double iqr_k = 3.0;

    // фичер ям: включается только если true (иначе чистая полиномиальная модель)
    bool pits = false;
    double sigma_deg = 3.0;            // PIT_DEFAULTS
    double pit_core_sigma = 2.0;
    double pit_window_sigma = 3.2;
    double pit_min_amp = 3e-3;
    bool tapering = true;

    // детектор трещин (DETECTOR_DEFAULTS): band |уровень 1° - уровень 10°|
    std::string detector_kind = "band";
    double detector_window_deg = 1.0;
    double detector_wide_deg = 10.0;
    double detector_smooth_deg = 2.0;
    double detector_k = 5.5;
    double detector_min_zone_deg = 2.0;

    bool verbose = true;
};

class GeometryPipeline {
public:
    explicit GeometryPipeline(PipelineOptions opt = PipelineOptions{})
        : opt_(std::move(opt)) {}

    // section_ids/heights/angles/radii — все точки всех сечений.
    std::vector<SectionModel> process(const std::vector<int>& section_ids,
                                      const std::vector<double>& heights,
                                      const std::vector<double>& angles,
                                      const std::vector<double>& radii);

    const PipelineOptions& options() const { return opt_; }

private:
    PipelineOptions opt_;
};

}  // namespace pappa

#endif  // PAPPA_GEOMETRY_PIPELINE_H
