#ifndef PAPPA_AUTO_OUTLIER_CLEANER_H
#define PAPPA_AUTO_OUTLIER_CLEANER_H

#include <string>
#include <vector>

// Авто-очиститель выбросов порта — повторение AutoOutlierCleaner (метод "iqr")
// из python/pappa/core/outlier_cleaner.py. Это ШТАТНЫЙ режим пайплайна
// (CONFIG["cleaner"] = {"mode": "auto", "auto": {"method": "iqr"}}).
//
// Логика: снимаем форму профиля скользящей медианой по кольцу, считаем остаток
// res = r - baseline и его робастный масштаб; порог — усы Тьюки iqr_k * IQR(res),
// центр — медиана остатка. Дно глубокой ямы перестаёт быть выбросом, потому что
// остаток считается от ЛОКАЛЬНОГО уровня, а не от глобальной медианы
// (в ручном режиме яма выглядела как выброс — см. CONTEXT §13).
//
// Ручной OutlierCleaner оставлен в cpp/outlier_cleaner.{h,cpp} как LEGACY и в
// пайплайне не используется.

namespace pappa {

struct CleanerInfo {
    int baseline_window_points = 0;   // ширина окна снятия формы, точек
    double baseline_window_deg = 0.0;
    double sigma_res_mm = 0.0;        // 1.4826 * MAD остатка
    double iqr_res_mm = 0.0;
    double threshold_mm = 0.0;        // iqr_k * IQR
    double iqr_k = 3.0;
    int n_total = 0;
    int n_outliers = 0;
};

class AutoOutlierCleaner {
public:
    AutoOutlierCleaner(double baseline_deg = 1.0, double iqr_k = 3.0,
                       double max_removed_frac = 0.5, int min_points = 20)
        : baseline_deg_(baseline_deg), iqr_k_(iqr_k),
          max_removed_frac_(max_removed_frac), min_points_(min_points) {}

    // Маска выбросов по профилю (angles — отсортированы по возрастанию).
    std::vector<bool> clean(const std::vector<double>& angles,
                            const std::vector<double>& radii);

    const CleanerInfo& info() const { return info_; }
    const std::string& method() const { return method_; }

private:
    double baseline_deg_;
    double iqr_k_;
    double max_removed_frac_;
    int min_points_;
    std::string method_ = "iqr";
    CleanerInfo info_;
};

}  // namespace pappa

#endif  // PAPPA_AUTO_OUTLIER_CLEANER_H
