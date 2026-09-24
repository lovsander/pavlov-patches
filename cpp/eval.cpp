#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <stdexcept>
#include <iomanip>
#include <corecrt_math_defines.h>

// Структура, описывающая один локальный патч
struct Patch
{
    double center;
    double half_sector;
    double half_train;
    double half_use;
    std::vector<double> coefs; // Коэффициенты полинома от старшей степени к младшей
    int degree;
    int n_points;
};

class PatchApproximator
{
private:
    int n_patches;
    int deg_min;
    int deg_max;
    double amplitude_scale;
    double overlap_train;
    double overlap_use;
    // допуск политики степени (RMSE-«локоть»), доли
    double deg_elbow_tol;

    double half_sector;
    std::vector<double> centers;
    std::vector<Patch> patches;
    std::vector<int> degrees;
    bool is_fitted;

    // Вспомогательная функция: плавное затухание Smoothstep
    double smoothstep(double t) const
    {
        if (t < 0.0)
            return 0.0;
        if (t > 1.0)
            return 1.0;
        return t * t * (3.0 - 2.0 * t);
    }

    // Вычисление полинома по схеме Горнера (быстрее и точнее, чем степени в лоб)
    double polyval(const std::vector<double> &coefs, double x) const
    {
        double result = 0.0;
        for (double c : coefs)
        {
            result = result * x + c;
        }
        return result;
    }

    // Расчет процентиля (аналог np.percentile)
    double percentile(std::vector<double> v, double p) const
    {
        if (v.empty())
            return 0.0;
        size_t idx = static_cast<size_t>(std::round((p / 100.0) * (v.size() - 1)));
        std::nth_element(v.begin(), v.begin() + idx, v.end());
        return v[idx];
    }

    // Метод наименьших квадратов (МНК) — аналог np.polyfit
    std::vector<double> polyfit(const std::vector<double> &x, const std::vector<double> &y, int deg) const
    {
        int n = deg + 1;
        std::vector<std::vector<double>> A(n, std::vector<double>(n, 0.0));
        std::vector<double> B(n, 0.0);

        // Строим систему нормальных уравнений
        for (int i = 0; i < n; ++i)
        {
            for (int j = 0; j < n; ++j)
            {
                double sum_x = 0.0;
                for (double val : x)
                    sum_x += std::pow(val, i + j);
                A[i][j] = sum_x;
            }
            double sum_y = 0.0;
            for (size_t k = 0; k < x.size(); ++k)
                sum_y += y[k] * std::pow(x[k], i);
            B[i] = sum_y;
        }

        // Решаем систему методом Гаусса с выбором главного элемента по столбцу
        for (int i = 0; i < n; ++i)
        {
            int max_row = i;
            for (int k = i + 1; k < n; ++k)
            {
                if (std::abs(A[k][i]) > std::abs(A[max_row][i]))
                    max_row = k;
            }
            std::swap(A[i], A[max_row]);
            std::swap(B[i], B[max_row]);

            if (std::abs(A[i][i]) < 1e-12)
            {
                throw std::runtime_error("Матрица МНК вырождена. Недостаточно уникальных точек или слишком высокая степень.");
            }

            for (int k = i + 1; k < n; ++k)
            {
                double c = -A[k][i] / A[i][i];
                for (int j = i; j < n; ++j)
                    A[k][j] += c * A[i][j];
                B[k] += c * B[i];
            }
        }

        std::vector<double> coefs(n, 0.0);
        for (int i = n - 1; i >= 0; --i)
        {
            double sum = B[i];
            for (int j = i + 1; j < n; ++j)
                sum -= A[i][j] * coefs[j];
            coefs[i] = sum / A[i][i];
        }

        // Разворачиваем коэффициенты от старшей степени к младшей (как в NumPy)
        std::reverse(coefs.begin(), coefs.end());
        return coefs;
    }

    // Политика степени: наименьшая чётная степень, на которой RMSE обучающего
    // окна (half_sector + overlap_train) не хуже лучшей более чем на deg_elbow_tol.
    // Амплитудная шкала (P95-P5)/mean*amplitude_scale измеряла размах, а не
    // сложность формы (недооценивала узкие глубокие ямы) — оставлена только как
    // исторический параметр вызова.
    int estimate_degree(const std::vector<double> &angles, const std::vector<double> &radii, double center) const
    {
        double half_train = half_sector + overlap_train;

        // Окно строим так же, как в fit(): кольцо, развёрнутое на +-360 градусов
        std::vector<double> local_x, local_y;
        for (int shift : {-360, 0, 360})
        {
            for (size_t i = 0; i < angles.size(); ++i)
            {
                double dx = angles[i] + shift - center;
                if (dx >= -half_train && dx <= half_train)
                {
                    local_x.push_back(dx);
                    local_y.push_back(radii[i]);
                }
            }
        }

        if (local_x.size() < 5)
            return deg_min;

        int deg_hi = std::min(deg_max, static_cast<int>(local_x.size()) - 2);
        if (deg_hi % 2 != 0)
            deg_hi -= 1;
        if (deg_hi < deg_min)
            deg_hi = deg_min;

        std::vector<std::pair<int, double>> rmse_by_deg;
        double best_rmse = 0.0;
        int best_deg = deg_min;
        for (int deg = deg_min; deg <= deg_hi; deg += 2)
        {
            std::vector<double> coefs = polyfit(local_x, local_y, deg);
            double sse = 0.0;
            for (size_t k = 0; k < local_x.size(); ++k)
            {
                double e = polyval(coefs, local_x[k]) - local_y[k];
                sse += e * e;
            }
            double rmse = std::sqrt(sse / static_cast<double>(local_x.size()));
            rmse_by_deg.push_back({deg, rmse});
            if (deg == deg_min || rmse < best_rmse)
            {
                best_rmse = rmse;
                best_deg = deg;
            }
        }

        for (const auto &kv : rmse_by_deg)
        {
            if (kv.second <= best_rmse * (1.0 + deg_elbow_tol))
                return kv.first; // правило "локтя": первая достаточно хорошая степень
        }
        return best_deg;
    }

public:
    PatchApproximator(int n_patches = 8, int deg_min = 4, int deg_max = 14,
                      double amplitude_scale = 180.0, double overlap_train = 15.0, double overlap_use = 5.0,
                      double deg_elbow_tol = 0.05)
        : n_patches(n_patches), deg_min(deg_min), deg_max(deg_max),
          amplitude_scale(amplitude_scale), overlap_train(overlap_train), overlap_use(overlap_use),
          deg_elbow_tol(deg_elbow_tol), is_fitted(false)
    {

        if (this->deg_min % 2 != 0)
            this->deg_min++;
        if (this->deg_max % 2 != 0)
            this->deg_max++;
    }

    // Обучение модели аппроксимации
    PatchApproximator &fit(const std::vector<double> &angles, const std::vector<double> &radii)
    {
        if (angles.size() != radii.size())
            throw std::invalid_argument("Размеры массивов углов и радиусов не совпадают.");
        if (angles.size() < 10)
            throw std::invalid_argument("Недостаточно точек для аппроксимации.");

        double sector = 360.0 / n_patches;
        half_sector = sector / 2.0;

        centers.clear();
        for (int i = 0; i < n_patches; ++i)
        {
            centers.push_back(i * sector + half_sector);
        }

        // Виртуальное зацикливание массивов (обёртка на стыке периодов 0/360)
        std::vector<double> angles_ext, radii_ext;
        for (int shift : {-360, 0, 360})
        {
            for (size_t i = 0; i < angles.size(); ++i)
            {
                angles_ext.push_back(angles[i] + shift);
                radii_ext.push_back(radii[i]);
            }
        }

        patches.clear();
        degrees.clear();

        for (double c : centers)
        {
            int deg = estimate_degree(angles, radii, c);
            degrees.push_back(deg);

            double half_train = half_sector + overlap_train;
            double half_use = half_sector + overlap_use;

            std::vector<double> local_x, local_y;
            for (size_t i = 0; i < angles_ext.size(); ++i)
            {
                if (angles_ext[i] >= c - half_train && angles_ext[i] <= c + half_train)
                {
                    local_x.push_back(angles_ext[i] - c);
                    local_y.push_back(radii_ext[i]);
                }
            }

            std::vector<double> coefs = polyfit(local_x, local_y, deg);

            Patch p{c, half_sector, half_train, half_use, coefs, deg, static_cast<int>(local_x.size())};
            patches.push_back(p);
        }

        is_fitted = true;
        return *this;
    }

    // Расчет (интерполяция) геометрии по заданной решетке углов
    std::vector<double> eval(const std::vector<double> &eval_angles) const
    {
        if (!is_fitted)
            throw std::runtime_error("Сначала необходимо вызвать метод fit().");

        std::vector<double> fitted(eval_angles.size(), 0.0);

        // Этот цикл в C++ можно легко распараллелить через OpenMP: #pragma omp parallel for
        for (size_t i = 0; i < eval_angles.size(); ++i)
        {
            double a = eval_angles[i];
            double sum_vals_weights = 0.0;
            double sum_weights = 0.0;

            for (const auto &p : patches)
            {
                // Вычисление циклического расстояния
                double d = std::abs(std::fmod(a - p.center + 180.0, 360.0));
                if (d < 0)
                    d += 360.0;
                d = std::abs(d - 180.0);

                double w = 0.0;
                if (d <= p.half_sector)
                {
                    w = 1.0;
                }
                else if (d <= p.half_use)
                {
                    double t = 1.0 - (d - p.half_sector) / (p.half_use - p.half_sector);
                    w = smoothstep(t);
                }

                if (w > 0.0)
                {
                    double local_coord = std::fmod(a - p.center + 180.0, 360.0);
                    if (local_coord < 0)
                        local_coord += 360.0;
                    local_coord -= 180.0;

                    double r = polyval(p.coefs, local_coord);
                    sum_vals_weights += w * r;
                    sum_weights += w;
                }
            }

            if (sum_weights > 0.0)
            {
                fitted[i] = sum_vals_weights / sum_weights;
            }
            else
            {
                fitted[i] = 0.0; // Защитный фолбэк
            }
        }
        return fitted;
    }

    std::vector<int> get_degrees() const { return degrees; }
};

// --- ДЕМОНСТРАЦИОННЫЙ ЗАПУСК ---
int main()
{
    // Симулируем профиль детали с дефектом (провалом на 90 градусов)
    std::vector<double> angles;
    std::vector<double> radii;

    for (int deg = 0; deg < 360; deg += 2)
    {
        double rad = float(deg) * M_PI / 180.0;
        double base_radius = 15.0 + 0.5 * std::sin(2 * rad); // номинальная геометрия

        // Моделируем деформацию (провал) в районе 90 градусов
        if (deg >= 70 && deg <= 110)
        {
            base_radius -= 1.5 * std::cos((deg - 90) * M_PI / 40.0);
        }

        angles.push_back(deg);
        radii.push_back(base_radius);
    }

    // Инициализируем ваш аппроксиматор Павлова
    PatchApproximator approx(8, 4, 14, 180.0, 15.0, 5.0);

    // Обучаем модель
    approx.fit(angles, radii);

    std::cout << "--- Результаты расчета метода Павлова на C++ ---\n";
    std::cout << "Подобранные степени полиномов по секторам:\n";
    for (size_t i = 0; i < approx.get_degrees().size(); ++i)
    {
        std::cout << "Патч " << i << ": степень " << approx.get_degrees()[i] << "\n";
    }

    // Проверяем точность восстановления в контрольных точках
    std::vector test_angles = {45.0, 90.0, 180.0, 270.0};
    std::vector res = approx.eval(test_angles);
    std::cout << "\nКонтроль восстановленных радиусов:\n";
    std::cout << std::fixed << std::setprecision(4);
    for (size_t i = 0; i < test_angles.size(); ++i)
    {
        std::cout << "Угол: " << test_angles[i] << "° -> Расчетный радиус: " << res[i] << " мм\n";
    }
    return 0;
}
