#ifndef PAPPA_LINALG_H
#define PAPPA_LINALG_H

#include <vector>

// Линейная алгебра порта PAPPA (см. CONTEXT §27, шаг 4).
//
// Почему QR, а не нормальные уравнения: в Python МНК считается через
// np.polyfit / np.linalg.lstsq (QR/SVD), и чтобы коэффициенты совпадали с
// референсом в пределах допуска, в порту нужен столь же устойчивый решатель.
// Нормальные уравнения возводят число обусловленности в квадрат (на степени 14
// это уже заметно), поэтому используем отражения Хаусхолдера.

namespace pappa {

using Matrix = std::vector<std::vector<double>>;   // A[i][j], i-я строка

// Решение переопределённой системы A x = b методом наименьших квадратов
// (Хаусхолдер + обратная подстановка). A размером m x n (m >= n).
std::vector<double> lstsq_qr(Matrix A, std::vector<double> b);

// МНК-подгонка полинома степени deg по НОРМИРОВАННОЙ координате x ∈ [-1, 1].
// Возвращает коэффициенты от старшей степени к младшей (как np.polyfit).
std::vector<double> polyfit(const std::vector<double>& x_norm,
                            const std::vector<double>& y, int deg);

// Значение полинома по схеме Горнера (coefs[0] — старшая степень).
double polyval(const std::vector<double>& coefs, double x);

}  // namespace pappa

#endif  // PAPPA_LINALG_H
