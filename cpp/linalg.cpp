#include "linalg.h"

#include <cmath>
#include <stdexcept>

namespace pappa {

std::vector<double> lstsq_qr(Matrix A, std::vector<double> b) {
    const size_t m = A.size();
    if (m == 0) throw std::invalid_argument("lstsq_qr: пустая матрица");
    const size_t n = A[0].size();
    if (b.size() != m) throw std::invalid_argument("lstsq_qr: длины A и b не совпадают");
    if (m < n) throw std::invalid_argument("lstsq_qr: нужно m >= n");

    // --- Прямой ход: приводим A к верхнетреугольному виду отражениями Хаусхолдера
    for (size_t k = 0; k < n; ++k) {
        double norm = 0.0;
        for (size_t i = k; i < m; ++i) norm += A[i][k] * A[i][k];
        norm = std::sqrt(norm);
        if (norm < 1e-300) continue;                 // столбец уже нулевой

        const double alpha = (A[k][k] > 0.0) ? -norm : norm;
        std::vector<double> v(m, 0.0);
        for (size_t i = k; i < m; ++i) v[i] = A[i][k];
        v[k] -= alpha;
        double vnorm2 = 0.0;
        for (size_t i = k; i < m; ++i) vnorm2 += v[i] * v[i];
        if (vnorm2 < 1e-300) continue;

        // A := A - 2 v (v^T A) / (v^T v), то же для правой части
        for (size_t j = k; j < n; ++j) {
            double s = 0.0;
            for (size_t i = k; i < m; ++i) s += v[i] * A[i][j];
            const double c = 2.0 * s / vnorm2;
            for (size_t i = k; i < m; ++i) A[i][j] -= c * v[i];
        }
        double sb = 0.0;
        for (size_t i = k; i < m; ++i) sb += v[i] * b[i];
        const double cb = 2.0 * sb / vnorm2;
        for (size_t i = k; i < m; ++i) b[i] -= cb * v[i];
    }

    // --- Обратная подстановка по верхнему треугольнику
    std::vector<double> x(n, 0.0);
    for (int i = static_cast<int>(n) - 1; i >= 0; --i) {
        double s = b[static_cast<size_t>(i)];
        for (size_t j = static_cast<size_t>(i) + 1; j < n; ++j) {
            s -= A[static_cast<size_t>(i)][j] * x[j];
        }
        const double d = A[static_cast<size_t>(i)][static_cast<size_t>(i)];
        if (std::abs(d) < 1e-300) throw std::runtime_error("lstsq_qr: вырожденная система");
        x[static_cast<size_t>(i)] = s / d;
    }
    return x;
}

std::vector<double> polyfit(const std::vector<double>& x_norm,
                            const std::vector<double>& y, int deg) {
    if (x_norm.size() != y.size()) throw std::invalid_argument("polyfit: длины не совпадают");
    const size_t m = x_norm.size();
    const size_t n = static_cast<size_t>(deg) + 1;
    Matrix A(m, std::vector<double>(n, 0.0));
    for (size_t i = 0; i < m; ++i) {
        double p = 1.0;
        for (size_t j = 0; j < n; ++j) {             // A[i][j] = x^(deg-j)
            A[i][n - 1 - j] = p;
            p *= x_norm[i];
        }
    }
    return lstsq_qr(std::move(A), y);
}

double polyval(const std::vector<double>& coefs, double x) {
    double result = 0.0;
    for (double c : coefs) result = result * x + c;
    return result;
}

}  // namespace pappa
