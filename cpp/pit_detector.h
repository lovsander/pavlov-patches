#ifndef PAPPA_PIT_DETECTOR_H
#define PAPPA_PIT_DETECTOR_H

#include <utility>
#include <vector>

// Детектор ям (трещин) порта — повторение pappa/analysis/zones.py:
//
//   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
//   нормированная на свою робастную sigma -> безразмерный индикатор в «MAD-ах»;
//   зоны = участки, где индикатор > k (по умолчанию 5.5), длиной не короче
//   min_zone_deg (2°). Центр ямы = середина зоны.
//
// Почему именно band: точечные производные упираются в шум данных (шаг 0.06°),
// а сравнение двух масштабов — нет (§14). Порядок операций и окна совпадают с
// Python-ом, иначе центры ям (и, значит, базис патчей) разойдутся с референсом.

namespace pappa {

struct PitDetectorOptions {
    double baseline_deg = 1.0;      // узкая медиана
    double wide_deg = 10.0;         // широкая медиана
    double smooth_deg = 2.0;        // сглаживание индикатора
    double k = 5.5;                 // порог в MAD-ах
    double min_zone_deg = 2.0;      // минимальная длина зоны
};

class PitDetector {
public:
    explicit PitDetector(PitDetectorOptions opt = PitDetectorOptions{}) : opt_(opt) {}

    // Индикатор band на упорядоченной по углу сетке (безразмерный, MAD-единицы).
    std::vector<double> band_indicator(const std::vector<double>& angles,
                                       const std::vector<double>& radii) const;

    // Непрерывные зоны (интервалы углов, °) по порогу.
    std::vector<std::pair<double, double>> zones(const std::vector<double>& angles,
                                                 const std::vector<double>& values) const;

    // Центры ям (°) — середины найденных зон.
    std::vector<double> pits(const std::vector<double>& angles,
                             const std::vector<double>& radii) const;

    const PitDetectorOptions& options() const { return opt_; }

private:
    // Скользящее среднее по кольцу (окно в точках, приводится к нечётному).
    static std::vector<double> smooth_wrap(const std::vector<double>& x, int window);
    // Первая разность по кольцу (последняя точка -> первая), |.|
    static std::vector<double> wrap_diff_abs(const std::vector<double>& x);
    // Непрерывные зоны по маске на упорядоченной сетке (использует min_zone_deg).
    std::vector<std::pair<double, double>> mask_to_zones(
        const std::vector<double>& angles, const std::vector<bool>& mask) const;

    PitDetectorOptions opt_;
};

}  // namespace pappa

#endif  // PAPPA_PIT_DETECTOR_H
