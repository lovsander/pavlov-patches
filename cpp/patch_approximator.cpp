#include "patch_approximator.h"
#include <cmath>
#include <algorithm>
#include <numeric>
#include <stdexcept>
#include <utility>

PatchApproximator::PatchApproximator(int n_patches, int deg_min, int deg_max,
                                     double amplitude_scale,
                                     double overlap_train, double overlap_use,
                                     double deg_elbow_tol)
    : n_patches(n_patches), deg_min(deg_min), deg_max(deg_max),
      amplitude_scale(amplitude_scale),
      overlap_train(overlap_train), overlap_use(overlap_use),
      deg_elbow_tol(deg_elbow_tol) {
    if (this->deg_min % 2 != 0) this->deg_min++;
    if (this->deg_max % 2 != 0) this->deg_max++;
}

double PatchApproximator::smoothstep(double t) const {
    if (t < 0.0) return 0.0;
    if (t > 1.0) return 1.0;
    return t * t * (3.0 - 2.0 * t);
}

double PatchApproximator::polyval(const std::vector<double>& coefs, double x_norm) const {
    // Схема Горнера. coefs[0] — старшая степень, coefs.back() — младшая.
    double result = 0.0;
    for (double c : coefs) {
        result = result * x_norm + c;
    }
    return result;
}

double PatchApproximator::percentile(std::vector<double> v, double p) const {
    if (v.empty()) return 0.0;
    size_t idx = static_cast<size_t>(std::round((p / 100.0) * (v.size() - 1)));
    if (idx >= v.size()) idx = v.size() - 1;
    std::nth_element(v.begin(), v.begin() + idx, v.end());
    return v[idx];
}

// МНК на нормированном x ∈ [-1, 1].
// Нормировка снимает обусловленность матрицы Вандермонда.
std::vector<double> PatchApproximator::polyfit(const std::vector<double>& x_norm,
                                               const std::vector<double>& y,
                                               int deg) const {
    int n = deg + 1;
    std::vector<std::vector<double>> A(n, std::vector<double>(n, 0.0));
    std::vector<double> B(n, 0.0);

    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            double s = 0.0;
            for (double xv : x_norm) s += std::pow(xv, i + j);
            A[i][j] = s;
        }
        double sy = 0.0;
        for (size_t k = 0; k < x_norm.size(); ++k) {
            sy += y[k] * std::pow(x_norm[k], i);
        }
        B[i] = sy;
    }

    // Гаусс с частичным выбором главного элемента
    for (int i = 0; i < n; ++i) {
        int max_row = i;
        for (int k = i + 1; k < n; ++k) {
            if (std::abs(A[k][i]) > std::abs(A[max_row][i])) max_row = k;
        }
        std::swap(A[i], A[max_row]);
        std::swap(B[i], B[max_row]);

        if (std::abs(A[i][i]) < 1e-14) {
            throw std::runtime_error("polyfit: матрица МНК вырождена");
        }
        for (int k = i + 1; k < n; ++k) {
            double c = -A[k][i] / A[i][i];
            for (int j = i; j < n; ++j) A[k][j] += c * A[i][j];
            B[k] += c * B[i];
        }
    }

    std::vector<double> coefs(n, 0.0);
    for (int i = n - 1; i >= 0; --i) {
        double s = B[i];
        for (int j = i + 1; j < n; ++j) s -= A[i][j] * coefs[j];
        coefs[i] = s / A[i][i];
    }

    // Разворачиваем: coefs[0] — старшая степень
    std::reverse(coefs.begin(), coefs.end());
    return coefs;
}

// Политика степени: НАИМЕНЬШАЯ чётная степень, на которой RMSE обучающего окна
// (half_sector + overlap_train) не хуже лучшей более чем на deg_elbow_tol.
// Амплитудная шкала (P95-P5)/mean*amplitude_scale измеряла размах, а не
// сложность формы, поэтому недооценивала узкие глубокие ямы и переоценивала
// пологие широкие секторы — оставлена только как историческая метрика в Python.
int PatchApproximator::estimate_degree(const std::vector<double>& angles,
                                       const std::vector<double>& radii,
                                       double center) const {
    double half_train = half_sector + overlap_train;

    // Окно строим так же, как в fit(): кольцо, развёрнутое на ±360°.
    std::vector<double> local_x_norm, local_y;
    for (int shift : {-360, 0, 360}) {
        for (size_t i = 0; i < angles.size(); ++i) {
            double dx = angles[i] + shift - center;
            if (dx >= -half_train && dx <= half_train) {
                local_x_norm.push_back(dx / half_train);   // ∈ [-1, 1]
                local_y.push_back(radii[i]);
            }
        }
    }
    size_t n_pts = local_x_norm.size();
    if (n_pts < 5) return deg_min;

    int deg_max_allowed = static_cast<int>(n_pts) - 2;
    if (deg_max_allowed % 2 != 0) deg_max_allowed--;
    if (deg_max_allowed < deg_min) deg_max_allowed = deg_min;
    int deg_hi = std::min(deg_max, deg_max_allowed);

    double best_rmse = 0.0, selected_rmse = 0.0;
    int best_deg = deg_min, selected_deg = -1;
    std::vector<std::pair<int, double>> rmse_by_deg;   // (deg, rmse)
    for (int deg = deg_min; deg <= deg_hi; deg += 2) {
        std::vector<double> coefs = polyfit(local_x_norm, local_y, deg);
        double sse = 0.0;
        for (size_t k = 0; k < n_pts; ++k) {
            double e = polyval(coefs, local_x_norm[k]) - local_y[k];
            sse += e * e;
        }
        double rmse = std::sqrt(sse / static_cast<double>(n_pts));
        rmse_by_deg.emplace_back(deg, rmse);
        if (deg == deg_min || rmse < best_rmse) { best_rmse = rmse; best_deg = deg; }
    }
    // Лучший берём по ВСЕМУ диапазону (как в Python), иначе допуск окажется
    // слишком свободным на первых степенях.
    for (const auto& kv : rmse_by_deg) {
        if (kv.second <= best_rmse * (1.0 + deg_elbow_tol)) {
            selected_deg = kv.first;
            selected_rmse = kv.second;
            break;
        }
    }
    (void)selected_rmse;
    return selected_deg < 0 ? best_deg : selected_deg;
}

void PatchApproximator::fit(const std::vector<double>& angles,
                            const std::vector<double>& radii) {
    if (angles.size() != radii.size()) {
        throw std::invalid_argument("fit: размеры массивов не совпадают");
    }
    if (angles.size() < 10) {
        throw std::invalid_argument("fit: недостаточно точек");
    }

    double sector = 360.0 / n_patches;
    half_sector = sector / 2.0;

    centers.clear();
    for (int i = 0; i < n_patches; ++i) {
        centers.push_back(i * sector + half_sector);
    }

    // Обёртка 0/360
    std::vector<double> angles_ext, radii_ext;
    angles_ext.reserve(angles.size() * 3);
    radii_ext.reserve(radii.size() * 3);
    for (int shift : {-360, 0, 360}) {
        for (size_t i = 0; i < angles.size(); ++i) {
            angles_ext.push_back(angles[i] + shift);
            radii_ext.push_back(radii[i]);
        }
    }

    patches.clear();
    patches.reserve(n_patches);

    for (double c : centers) {
        int deg = estimate_degree(angles, radii, c);

        double half_train = half_sector + overlap_train;
        double half_use   = half_sector + overlap_use;

        std::vector<double> local_x_norm, local_y;
        for (size_t i = 0; i < angles_ext.size(); ++i) {
            double dx = angles_ext[i] - c;
            if (dx >= -half_train && dx <= half_train) {
                local_x_norm.push_back(dx / half_train); // ∈ [-1, 1]
                local_y.push_back(radii_ext[i]);
            }
        }

        // Защита: степень не должна превышать число точек - 1
        int max_deg_allowed = static_cast<int>(local_x_norm.size()) - 2;
        if (max_deg_allowed % 2 != 0) max_deg_allowed--;
        if (max_deg_allowed < deg_min) max_deg_allowed = deg_min;
        if (deg > max_deg_allowed) deg = max_deg_allowed;

        std::vector<double> coefs = polyfit(local_x_norm, local_y, deg);
        patches.push_back(Patch{c, half_sector, half_train, half_use,
                                coefs, deg,
                                static_cast<int>(local_x_norm.size())});
    }
}

std::vector<double> PatchApproximator::eval(const std::vector<double>& eval_angles) const {
    std::vector<double> fitted(eval_angles.size(), 0.0);

    for (size_t i = 0; i < eval_angles.size(); ++i) {
        double a = eval_angles[i];
        double sum_wv = 0.0;
        double sum_w  = 0.0;

        for (const auto& p : patches) {
            // distance по кольцу (в градусах) — для весов
            double d = std::abs(a - p.center);
            if (d > 180.0) d = 360.0 - d;

            double w = 0.0;
            if (d <= p.half_sector) {
                w = 1.0;
            } else if (d <= p.half_use) {
                double t = 1.0 - (d - p.half_sector) / (p.half_use - p.half_sector);
                w = smoothstep(t);
            }

            if (w > 0.0) {
                // нормированный x для polyval
                double dx = a - p.center;
                while (dx < -180.0) dx += 360.0;
                while (dx >  180.0) dx -= 360.0;
                double x_norm = dx / p.half_train;

                double r = polyval(p.coefs, x_norm);
                sum_wv += w * r;
                sum_w  += w;
            }
        }
        fitted[i] = (sum_w > 0.0) ? (sum_wv / sum_w) : 0.0;
    }
    return fitted;
}

std::vector<int> PatchApproximator::get_degrees() const {
    std::vector<int> degs;
    degs.reserve(patches.size());
    for (const auto& p : patches) degs.push_back(p.degree);
    return degs;
}