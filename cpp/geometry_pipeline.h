#ifndef GEOMETRY_PIPELINE_H
#define GEOMETRY_PIPELINE_H

#include "outlier_cleaner.h"
#include <vector>

struct SectionResult {
    int section_id;
    double height_mm;
    std::vector<double> angles;        // углы, на которых считалось
    std::vector<double> radii_clean;   // чистые радиусы (в том же порядке)
    std::vector<bool>   outlier_mask;  // маска выбросов для углов
    std::vector<double> fitted_fine;
    std::vector<double> fitted_coarse;
    std::vector<int>    degrees;
};

class GeometryPipeline {
private:
    OutlierCleaner cleaner;

public:
    GeometryPipeline(double threshold_deriv = 0.5,
                     double mad_k = 9.5,
                     double z_threshold = 3.5);

    std::vector<SectionResult> process_batch(
        const std::vector<int>&    section_ids,
        const std::vector<double>& heights,
        const std::vector<double>& angles,
        const std::vector<double>& radii
    );
};

#endif