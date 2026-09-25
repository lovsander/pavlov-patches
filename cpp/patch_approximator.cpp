#include "patch_approximator.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "linalg.h"
#include "signal_tools.h"

namespace pappa {

namespace {
// Кратчайшее расстояние по кольцу (градусы).
inline double circ_dist(double a, double b) {
    double d = std::fmod(a - b + 180.0, 360.0);
    if (d < 0.0) d += 360.0;
    return std::abs(d - 180.0);
}

// Локальная координата: смещение по кольцу в (-180, 180].
inline double circ_local(double a, double b) {
    double d = std::fmod(a - b + 180.0, 360.0);
    if (d < 0.0) d += 360.0;
    return d - 180.0;
}
}  // namespace

PatchApproximator::PatchApproximator(int n_patches, int deg_min, int deg_max,
                                     double amplitude_scale, double overlap_train,
                                     double overlap_use, double phase_deg,
                                     double deg_elbow_tol, std::string coord_mode)
    : n_patches_(n_patches), deg_min_(deg_min), deg_max_(deg_max),
      amplitude_scale_(amplitude_scale), overlap_train_(overlap_train),
      overlap_use_(overlap_use), phase_deg_(std::fmod(phase_deg, 360.0)),
      deg_elbow_tol_(deg_elbow_tol), coord_mode_(std::move(coord_mode)) {
    if (n_patches_ <= 0) throw std::invalid_argument("n_patches должен быть > 0");
    if (deg_min_ % 2 != 0) ++deg_min_;
    if (deg_max_ % 2 != 0) ++deg_max_;
    if (coord_mode_ != "normalized" && coord_mode_ != "raw") {
        throw std::invalid_argument("coord_mode: ожидается 'normalized' или 'raw'");
    }
    if (phase_deg_ < 0.0) phase_deg_ += 360.0;
}

void PatchApproximator::set_pits(const std::vector<double>& centers_deg) {
    pits_.clear();
    pits_.reserve(centers_deg.size());
    for (double c : centers_deg) {
        double v = std::fmod(c, 360.0);
        if (v < 0.0) v += 360.0;
        pits_.push_back(v);
    }
}

void PatchApproximator::set_pit_shape(double sigma_deg, double core_sigma,
                                      double window_sigma, double pit_min_amp,
                                      bool tapering) {
    if (sigma_deg <= 0.0) throw std::invalid_argument("sigma_deg должен быть > 0");
    if (window_sigma * sigma_deg < core_sigma * sigma_deg) {
        throw std::invalid_argument("окно фичера уже ядра");
    }
    sigma_deg_ = sigma_deg;
    core_sigma_ = core_sigma;
    window_sigma_ = window_sigma;
    pit_min_amp_ = pit_min_amp;
    tapering_ = tapering;
}

double PatchApproximator::smoothstep(double t) {
    if (t < 0.0) return 0.0;
    if (t > 1.0) return 1.0;
    return t * t * (3.0 - 2.0 * t);
}

double PatchApproximator::weight(double d_deg, double half_use) const {
    if (d_deg <= half_sector_) return 1.0;
    if (d_deg <= half_use) {
        const double t = 1.0 - (d_deg - half_sector_) / (half_use - half_sector_);
        return smoothstep(t);
    }
    return 0.0;
}

// Оконный гаусс как функция расстояния от центра ямы (совпадает с
// pit_shape_deg в python/pappa/core/pit_feature.py).
double PatchApproximator::pit_shape_deg(double d_deg) const {
    const double d = std::abs(d_deg);
    const double val = std::exp(-d * d / (2.0 * sigma_deg_ * sigma_deg_));
    if (!tapering_) return val;
    const double core = core_sigma_ * sigma_deg_;
    const double edge = window_sigma_ * sigma_deg_;
    if (edge <= core) return val;
    double t = (edge - d) / (edge - core);
    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;
    return val * t * t * (3.0 - 2.0 * t);
}

// Смещения видимых ям в локальной системе патча (градусы).
std::vector<double> PatchApproximator::pit_offsets(double center_deg,
                                                   double half_win_deg) const {
    std::vector<double> out;
    for (double p : pits_) {
        const double dx = circ_local(p, center_deg);
        if (std::abs(dx) <= half_win_deg) out.push_back(dx);
    }
    return out;
}


// Политика степени: НАИМЕНЬШАЯ чётная степень, на которой RMSE обучающего окна
// не хуже лучшей более чем на deg_elbow_tol. Поиск ведётся на том же базисе и
// том же наборе точек, что и финальный МНК (иначе допуск оказался бы свободнее).
int PatchApproximator::estimate_degree(const std::vector<double>& angles,
                                       const std::vector<double>& radii,
                                       double center,
                                       double& out_rmse_selected,
                                       double& out_rmse_best,
                                       int& out_n_train) const {
    const double half_train = half_sector_ + overlap_train_;

    std::vector<double> xs, ys;
    for (int shift : {-360, 0, 360}) {
        for (size_t i = 0; i < angles.size(); ++i) {
            const double dx = angles[i] + shift - center;
            if (dx >= -half_train && dx <= half_train) {
                xs.push_back((coord_mode_ == "raw") ? dx : dx / half_train);
                ys.push_back(radii[i]);
            }
        }
    }
    const size_t n = xs.size();
    out_n_train = static_cast<int>(n);
    out_rmse_selected = 0.0;
    out_rmse_best = 0.0;
    if (n < 5) return deg_min_;

    int best_deg = deg_min_;
    double best_rmse = 0.0;
    bool best_set = false;
    std::vector<std::pair<int, double>> rows;
    rows.reserve(static_cast<size_t>(deg_max_ - deg_min_) / 2 + 1);
    for (int deg = deg_min_; deg <= deg_max_; deg += 2) {
        const std::vector<double> coefs = polyfit(xs, ys, deg);
        double sse = 0.0;
        for (size_t k = 0; k < n; ++k) {
            const double e = polyval(coefs, xs[k]) - ys[k];
            sse += e * e;
        }
        const double rmse = std::sqrt(sse / static_cast<double>(n));
        rows.emplace_back(deg, rmse);
        if (!best_set || rmse < best_rmse) { best_rmse = rmse; best_deg = deg; best_set = true; }
    }

    out_rmse_best = best_rmse;
    int selected_deg = best_deg;
    double selected_rmse = best_rmse;
    const double limit = best_rmse * (1.0 + deg_elbow_tol_);
    for (const auto& kv : rows) {
        if (kv.second <= limit) {                    // строки идут по возрастанию степени
            selected_deg = kv.first;
            selected_rmse = kv.second;
            break;
        }
    }
    out_rmse_selected = selected_rmse;
    return selected_deg;
}


void PatchApproximator::fit(const std::vector<double>& angles,
                            const std::vector<double>& radii) {
    if (angles.size() != radii.size()) {
        throw std::invalid_argument("fit: размеры массивов не совпадают");
    }
    if (angles.size() < 10) throw std::invalid_argument("fit: слишком мало точек");

    const double sector = 360.0 / static_cast<double>(n_patches_);
    half_sector_ = sector / 2.0;
    centers_.clear();
    centers_.reserve(static_cast<size_t>(n_patches_));
    for (int i = 0; i < n_patches_; ++i) {
        double c = i * sector + half_sector_ + phase_deg_;
        c = std::fmod(c, 360.0);
        if (c < 0.0) c += 360.0;
        centers_.push_back(c);
    }

    // Кольцо разворачиваем на ±360°, чтобы окна не рвались на 0/360.
    std::vector<double> angles_ext, radii_ext;
    angles_ext.reserve(angles.size() * 3);
    radii_ext.reserve(radii.size() * 3);
    for (int shift : {-360, 0, 360}) {
        for (size_t i = 0; i < angles.size(); ++i) {
            angles_ext.push_back(angles[i] + shift);
            radii_ext.push_back(radii[i]);
        }
    }

    const double half_train = half_sector_ + overlap_train_;
    const double half_use = half_sector_ + overlap_use_;

    patches_.clear();
    patches_.reserve(static_cast<size_t>(n_patches_));

    for (double c : centers_) {
        double rmse_selected = 0.0, rmse_best = 0.0;
        int n_train = 0;
        const int deg = estimate_degree(angles, radii, c, rmse_selected,
                                        rmse_best, n_train);

        // Точки обучающего окна (локальная координата в каноне).
        std::vector<double> xs, ys;
        for (size_t i = 0; i < angles_ext.size(); ++i) {
            const double dx = angles_ext[i] - c;
            if (dx >= -half_train && dx <= half_train) {
                xs.push_back((coord_mode_ == "raw") ? dx : dx / half_train);
                ys.push_back(radii_ext[i]);
            }
        }
        if (xs.size() < 5) continue;

        const std::vector<double> offs_deg = pit_offsets(c, half_train);

        // Матрица базиса: полином (старшая степень первая) + оконные гауссы.
        const size_t ncol = static_cast<size_t>(deg) + 1 + offs_deg.size();
        Matrix A(xs.size(), std::vector<double>(ncol, 0.0));
        for (size_t i = 0; i < xs.size(); ++i) {
            double p = 1.0;
            for (int k = deg; k >= 0; --k) {          // A[i][k] = xs^(deg-k)
                A[i][static_cast<size_t>(k)] = p;
                p *= xs[i];
            }
            for (size_t j = 0; j < offs_deg.size(); ++j) {
                const double d_deg =
                    std::abs(xs[i] - offs_deg[j] / half_train) * half_train;
                A[i][static_cast<size_t>(deg) + 1 + j] = pit_shape_deg(d_deg);
            }
        }
        const std::vector<double> coef = lstsq_qr(std::move(A), ys);

        std::vector<double> poly_coef(coef.begin(), coef.begin() + deg + 1);
        std::vector<double> pit_coef(coef.begin() + deg + 1, coef.end());

        // Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
        std::vector<double> kept_offsets, kept_coefs;
        for (size_t j = 0; j < offs_deg.size(); ++j) {
            double max_abs = 0.0;
            for (size_t i = 0; i < xs.size(); ++i) {
                const double d_deg =
                    std::abs(xs[i] - offs_deg[j] / half_train) * half_train;
                max_abs = std::max(max_abs,
                                   std::abs(pit_coef[j] * pit_shape_deg(d_deg)));
            }
            if (max_abs >= pit_min_amp_) {
                kept_offsets.push_back(offs_deg[j]);
                kept_coefs.push_back(pit_coef[j]);
            }
        }


        // Статистика по остаткам обучающего окна (по полному базису).
        std::vector<double> fit_vals(xs.size(), 0.0);
        for (size_t i = 0; i < xs.size(); ++i) {
            double v = polyval(poly_coef, xs[i]);
            for (size_t j = 0; j < kept_offsets.size(); ++j) {
                const double d_deg =
                    std::abs(xs[i] - kept_offsets[j] / half_train) * half_train;
                v += kept_coefs[j] * pit_shape_deg(d_deg);
            }
            fit_vals[i] = v;
        }
        double sse = 0.0, sae = 0.0, mx = 0.0;
        for (size_t i = 0; i < xs.size(); ++i) {
            const double e = fit_vals[i] - ys[i];
            sse += e * e;
            sae += std::abs(e);
            mx = std::max(mx, std::abs(e));
        }
        const double npt = static_cast<double>(xs.size());
        const double rmse = std::sqrt(sse / npt);
        const double mae = sae / npt;

        // Справочные метрики сектора (P95 - P5 по точкам своего сектора).
        std::vector<double> r_sec;
        for (size_t i = 0; i < angles.size(); ++i) {
            if (circ_dist(angles[i], c) <= half_sector_) r_sec.push_back(radii[i]);
        }
        double amp = 0.0, mean_sec = 0.0;
        if (r_sec.size() >= 5) {
            amp = percentile_linear(r_sec, 95.0) - percentile_linear(r_sec, 5.0);
            double sum = 0.0;
            for (double v : r_sec) sum += v;
            mean_sec = sum / static_cast<double>(r_sec.size());
        }
        const double amp_norm = (mean_sec > 0.0) ? amp / mean_sec : 0.0;

        double corr = 0.0;
        {
            double mf = 0.0, my = 0.0;
            for (size_t i = 0; i < xs.size(); ++i) { mf += fit_vals[i]; my += ys[i]; }
            mf /= npt;
            my /= npt;
            double cov = 0.0, vf = 0.0, vy = 0.0;
            for (size_t i = 0; i < xs.size(); ++i) {
                const double df = fit_vals[i] - mf, dy = ys[i] - my;
                cov += df * dy;
                vf += df * df;
                vy += dy * dy;
            }
            if (vf > 0.0 && vy > 0.0) corr = cov / std::sqrt(vf * vy);
        }

        Patch patch;
        patch.center = c;
        patch.half_sector = half_sector_;
        patch.half_train = half_train;
        patch.half_use = half_use;
        patch.coefs = poly_coef;
        patch.degree = deg;
        patch.n_points = static_cast<int>(xs.size());
        patch.amplitude_mm = amp;
        patch.amplitude_norm = amp_norm;
        patch.mean_radius_mm = mean_sec;
        patch.rmse_selected_mm = rmse_selected;
        patch.rmse_best_mm = rmse_best;
        patch.rmse_mm = rmse;
        patch.mae_mm = mae;
        patch.max_err_mm = mx;
        patch.correlation = corr;
        patch.pit_offsets_deg = kept_offsets;
        patch.pit_coefs = kept_coefs;
        patches_.push_back(std::move(patch));
    }

    is_fitted_ = true;
}

std::vector<double> PatchApproximator::eval_part(const std::vector<double>& angles,
                                                 const std::string& part) const {
    if (!is_fitted_) throw std::runtime_error("Сначала вызовите fit()");
    const double half_use = half_sector_ + overlap_use_;
    std::vector<double> out(angles.size(), 0.0);

    for (size_t i = 0; i < angles.size(); ++i) {
        const double a = angles[i];
        double sum_wv = 0.0, sum_w = 0.0;
        for (const Patch& p : patches_) {
            const double d = circ_dist(a, p.center);
            const double w = weight(d, half_use);
            if (w <= 0.0) continue;

            const double dx = circ_local(a, p.center);
            const double xs = (coord_mode_ == "raw") ? dx : dx / p.half_train;

            double v = 0.0;
            if (part != "pit") v += polyval(p.coefs, xs);
            if (part != "poly") {
                for (size_t j = 0; j < p.pit_offsets_deg.size(); ++j) {
                    const double d_deg =
                        std::abs(xs - p.pit_offsets_deg[j] / p.half_train) * p.half_train;
                    v += p.pit_coefs[j] * pit_shape_deg(d_deg);
                }
            }
            sum_wv += w * v;
            sum_w += w;
        }
        out[i] = (sum_w > 0.0) ? (sum_wv / sum_w) : 0.0;
    }
    return out;
}

std::vector<double> PatchApproximator::eval(const std::vector<double>& angles) const {
    return eval_part(angles, "total");
}

std::vector<int> PatchApproximator::get_degrees() const {
    std::vector<int> degs;
    degs.reserve(patches_.size());
    for (const Patch& p : patches_) degs.push_back(p.degree);
    return degs;
}

}  // namespace pappa

