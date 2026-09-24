#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <map>

// Структура для возврата детальной статистики
struct CleanerStats {
    size_t n_total;
    int n_deriv;
    int n_mad;
    int n_z;
    int n_total_outliers;
    double percent_outliers;
    double mad_value;
};

class OutlierCleaner {
private:
    double threshold_deriv;
    double mad_k;
    double z_threshold;

    // Быстрый расчет медианы за O(N) без полной сортировки массива
    double calculate_median(std::vector<double> v) const {
        if (v.empty()) return 0.0;
        size_t n = v.size();
        if (n % 2 == 1) {
            size_t mid = n / 2;
            std::nth_element(v.begin(), v.begin() + mid, v.end());
            return v[mid];
        } else {
            size_t mid1 = n / 2 - 1;
            size_t mid2 = n / 2;
            std::nth_element(v.begin(), v.begin() + mid1, v.end());
            double val1 = v[mid1];
            std::nth_element(v.begin(), v.begin() + mid2, v.end());
            double val2 = v[mid2];
            return (val1 + val2) / 2.0;
        }
    }

public:
    OutlierCleaner(double threshold_deriv = 0.5, double mad_k = 9.5, double z_threshold = 3.5)
        : threshold_deriv(threshold_deriv), mad_k(mad_k), z_threshold(z_threshold) {}

    // Метод clean: возвращает булев массив (вектор маски), где true = выброс
    std::vector<bool> clean(const std::vector<double>& angles, const std::vector<double>& radii) const {
        if (angles.size() != radii.size()) {
            throw std::invalid_argument("angles и radii должны быть одинаковой длины"); // [3]
        }
        
        size_t n = angles.size();
        std::vector<bool> mask(n, false);
        if (n < 3) return mask; // [3]

        // --- 1. Медиана и MAD ---
        double median_r = calculate_median(radii); // [3]
        
        std::vector<double> abs_dev(n);
        for (size_t i = 0; i < n; ++i) {
            abs_dev[i] = std::abs(radii[i] - median_r); // [3]
        }
        double mad = calculate_median(abs_dev); // [3]

        // --- 2. Проход по точкам и расчет всех трех критериев ---
        for (size_t i = 0; i < n; ++i) {
            // Критерий 1: Производная (разность со следующей точкой по циклу)
            double dr;
            if (i == 0) {
                dr = radii[0] - radii[n - 1]; // Замыкание (стык 0/360) [3]
            } else {
                dr = radii[i] - radii[i - 1]; // [3]
            }
            bool mask_deriv = std::abs(dr) > threshold_deriv; // [3]

            // Критерий 2 и 3: MAD и Modified z-score
            bool mask_mad = false;
            bool mask_z = false;
            
            if (mad > 0.0) {
                mask_mad = abs_dev[i] > (mad_k * mad); // [3]
                double z_score = 0.6745 * abs_dev[i] / mad; // [3]
                mask_z = z_score > z_threshold; // [3]
            }

            // Объединяем логическим ИЛИ [3]
            mask[i] = mask_deriv || mask_mad || mask_z;
        }

        return mask;
    }

    // Метод stats: возвращает структуру с детальной статистикой для логов
    CleanerStats stats(const std::vector<double>& angles, const std::vector<double>& radii) const {
        if (angles.size() != radii.size()) {
            throw std::invalid_argument("angles и radii должны быть одинаковой длины"); // [3]
        }

        size_t n = angles.size();
        int n_deriv = 0, n_mad = 0, n_z = 0, n_total_outliers = 0;

        double median_r = calculate_median(radii); // [3]
        std::vector<double> abs_dev(n);
        for (size_t i = 0; i < n; ++i) abs_dev[i] = std::abs(radii[i] - median_r); // [3]
        double mad = calculate_median(abs_dev); // [3]

        for (size_t i = 0; i < n; ++i) {
            double dr = (i == 0) ? (radii[0] - radii[n - 1]) : (radii[i] - radii[i - 1]); // [3]
            bool mask_deriv = std::abs(dr) > threshold_deriv; // [3]

            bool mask_mad = (mad > 0.0) && (abs_dev[i] > (mad_k * mad)); // [3]
            bool mask_z = (mad > 0.0) && ((0.6745 * abs_dev[i] / mad) > z_threshold); // [3]

            if (mask_deriv) n_deriv++;
            if (mask_mad) n_mad++;
            if (mask_z) n_z++;
            if (mask_deriv || mask_mad || mask_z) n_total_outliers++; // [3]
        }

        double percent = n > 0 ? (100.0 * n_total_outliers / n) : 0.0; // [3]

        return CleanerStats{n, n_deriv, n_mad, n_z, n_total_outliers, percent, mad};
    }

    // Метод apply: возвращает отфильтрованные массивы без выбросов
    void apply(const std::vector<double>& angles, const std::vector<double>& radii, 
               std::vector<double>& angles_clean, std::vector<double>& radii_clean) const {
        
        std::vector<bool> mask = clean(angles, radii); // [3]
        angles_clean.clear();
        radii_clean.clear();

        for (size_t i = 0; i < angles.size(); ++i) {
            if (!mask[i]) { // Берем инвертированную маску (~mask) [3]
                angles_clean.push_back(angles[i]);
                radii_clean.push_back(radii[i]);
            }
        }
    }
};

// --- Демонстрация работы полного пайплайна ---
int main() {
    // Входной профиль сечения
    std::vector<double> angles = {0.0, 60.0, 120.0, 180.0, 240.0, 300.0};
    // 120.0 — это нормальная точка, а на 180.0 смоделируем мощный аппаратный выброс (45 мм вместо ~15 мм)
    std::vector<double> radii  = {15.1, 14.9,  15.3,  45.0,  15.0,  15.2};

    // Инициализируем очиститель с вашими параметрами
    OutlierCleaner cleaner(0.5, 9.5, 3.5); // [2]

    // Смотрим диагностику
    CleanerStats st = cleaner.stats(angles, radii);
    std::cout << "=== СТАТИСТИКА ОЧИСТКИ (C++) ===\n";
    std::cout << "Всего точек: " << st.n_total << "\n";
    std::cout << "Выбросов по производной: " << st.n_deriv << "\n";
    std::cout << "Выбросов по MAD: " << st.n_mad << "\n";
    std::cout << "Выбросов по Z-score: " << st.n_z << "\n";
    std::cout << "Итого отбраковано: " << st.n_total_outliers << " (" << st.percent_outliers << "%)\n";
    std::cout << "Значение MAD: " << st.mad_value << "\n\n";

    // Фильтруем данные
    std::vector<double> a_clean, r_clean;
    cleaner.apply(angles, radii, a_clean, r_clean);

    std::cout << "=== ОЧИЩЕННЫЙ ПРОФИЛЬ ===\n";
    for(size_t i = 0; i < a_clean.size(); ++i) {
        std::cout << "Угол: " << a_clean[i] << "° -> Радиус: " << r_clean[i] << " мм\n";
    }

    return 0;
}
