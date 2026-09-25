#ifndef PAPPA_PATCH_APPROXIMATOR_H
#define PAPPA_PATCH_APPROXIMATOR_H

#include <string>
#include <vector>

// PAPPA — Piecewise Adaptive Poly-Patch Approximation (порт, CONTEXT §27, шаг 4).
//
// Патч = полином по НОРМИРОВАННОЙ локальной координате x = (angle - center)/half_train,
// x ∈ [-1, 1] (канон координат, §8.1: без нормировки степень 14 даёт cond ~1e20).
// Степень выбирается правилом «локтя» по RMSE обучающего окна. Контур —
// нормированное smoothstep-смешивание патчей (partition of unity, C1).
// Опционально в базис патча добавляются ОКОННЫЕ гауссовы ямы (tapered gaussian),
// амплитуды которых подбирает тот же МНК — форма повторяет
// python/pappa/core/pit_feature.py.
//
// Числа обязаны совпадать с референсом: тот же базис, та же политика степени,
// тот же МНК-решатель (QR, как np.polyfit/lstsq), те же окна и веса.

namespace pappa {

struct Patch {
    double center = 0.0;              // °, глобальный угол центра патча
    double half_sector = 0.0;         // °, половина сектора (плато веса = 1)
    double half_train = 0.0;          // °, полуширина обучающего окна
    double half_use = 0.0;            // °, полуширина окна применения (blend)
    std::vector<double> coefs;        // полином, старшая степень первая
    int degree = 0;
    int n_points = 0;
    // метрики (как metrics в .pappa.json)
    double amplitude_mm = 0.0;
    double amplitude_norm = 0.0;
    double mean_radius_mm = 0.0;
    double rmse_selected_mm = 0.0;
    double rmse_best_mm = 0.0;
    // статистика по остаткам обучающего окна (как stats)
    double rmse_mm = 0.0;
    double mae_mm = 0.0;
    double max_err_mm = 0.0;
    double correlation = 0.0;
    // фичер ям: смещения центров ям в локальной системе патча и их амплитуды
    std::vector<double> pit_offsets_deg;
    std::vector<double> pit_coefs;
};

class PatchApproximator {
public:
    PatchApproximator(int n_patches = 7, int deg_min = 4, int deg_max = 14,
                      double amplitude_scale = 180.0,
                      double overlap_train = 15.0, double overlap_use = 5.0,
                      double phase_deg = 0.0, double deg_elbow_tol = 0.05,
                      std::string coord_mode = "normalized");

    // Центры ям (глобальные углы, °) — включает фичер ям в базисе.
    void set_pits(const std::vector<double>& centers_deg);
    // Форма оконного гаусса (значения по умолчанию — PIT_DEFAULTS).
    void set_pit_shape(double sigma_deg, double core_sigma, double window_sigma,
                       double pit_min_amp, bool tapering);
    // Считать степени по базису с ямами (по умолчанию false — как в Python).
    void set_degree_with_pits(bool value) { degree_with_pits_ = value; }

    void fit(const std::vector<double>& angles, const std::vector<double>& radii);
    std::vector<double> eval(const std::vector<double>& angles) const;
    // part: "total" (полином + ямы), "poly", "pit" — как eval_part в Python.
    std::vector<double> eval_part(const std::vector<double>& angles,
                                 const std::string& part) const;

    std::vector<int> get_degrees() const;

    // --- аксессоры (нужны писателю документа) ---
    int n_patches() const { return n_patches_; }
    int deg_min() const { return deg_min_; }
    int deg_max() const { return deg_max_; }
    double deg_elbow_tol() const { return deg_elbow_tol_; }
    double amplitude_scale() const { return amplitude_scale_; }
    double overlap_train() const { return overlap_train_; }
    double overlap_use() const { return overlap_use_; }
    double phase_deg() const { return phase_deg_; }
    double half_sector() const { return half_sector_; }
    double half_train() const { return half_sector_ + overlap_train_; }
    double half_use() const { return half_sector_ + overlap_use_; }
    const std::string& coord_mode() const { return coord_mode_; }
    bool has_pits() const { return !pits_.empty(); }
    const std::vector<double>& pits() const { return pits_; }
    double sigma_deg() const { return sigma_deg_; }
    double pit_core_sigma() const { return core_sigma_; }
    double pit_window_sigma() const { return window_sigma_; }
    double pit_min_amp() const { return pit_min_amp_; }
    bool tapering() const { return tapering_; }
    bool is_fitted() const { return is_fitted_; }
    const std::vector<Patch>& patches() const { return patches_; }
    const std::vector<double>& centers() const { return centers_; }

private:
    int estimate_degree(const std::vector<double>& angles,
                        const std::vector<double>& radii, double center,
                        double& out_rmse_selected, double& out_rmse_best,
                        int& out_n_train) const;
    std::vector<double> pit_offsets(double center_deg, double half_win_deg) const;
    double pit_shape_deg(double d_deg) const;
    double weight(double d_deg, double half_use) const;
    static double smoothstep(double t);

    int n_patches_;
    int deg_min_, deg_max_;
    double amplitude_scale_;
    double overlap_train_, overlap_use_;
    double phase_deg_;
    double deg_elbow_tol_;
    std::string coord_mode_;
    bool degree_with_pits_ = false;

    std::vector<double> pits_;
    double sigma_deg_ = 3.0;
    double core_sigma_ = 2.0;
    double window_sigma_ = 3.2;
    double pit_min_amp_ = 3e-3;
    bool tapering_ = true;

    double half_sector_ = 0.0;
    std::vector<double> centers_;
    std::vector<Patch> patches_;
    bool is_fitted_ = false;
};

}  // namespace pappa

#endif  // PAPPA_PATCH_APPROXIMATOR_H
