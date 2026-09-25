#ifndef PAPPA_SECTION_MODEL_H
#define PAPPA_SECTION_MODEL_H

#include <string>

#include "patch_approximator.h"

// Описание одного сечения: обученная модель + сведения о данных.
// Общий тип для пайплайна (geometry_pipeline) и писателя образца (sample_writer)
// — чтобы структурой не приходилось делиться через заголовок писателя.

namespace pappa {

struct SectionModel {
    int section_id = 0;
    double height_mm = 0.0;
    PatchApproximator model;         // уже обученная
    int n_points_total = 0;          // точек в сечении (до очистки)
    int n_outliers = 0;              // отброшено очисткой
    std::string source;              // откуда данные (имя CSV)
    std::string description;
    double fit_time_ms = 0.0;
};

}  // namespace pappa

#endif  // PAPPA_SECTION_MODEL_H
