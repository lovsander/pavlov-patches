#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <iomanip>

std::vector<double> polyfit(const std::vector<double>& x,
                            const std::vector<double>& y,
                            int deg) {
    int n = deg + 1;
    std::vector<std::vector<double>> A(n, std::vector<double>(n, 0.0));
    std::vector<double> B(n, 0.0);

    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            double s = 0.0;
            for (double xv : x) s += std::pow(xv, i + j);
            A[i][j] = s;
        }
        double sy = 0.0;
        for (size_t k = 0; k < x.size(); ++k) {
            sy += y[k] * std::pow(x[k], i);
        }
        B[i] = sy;
    }

    for (int i = 0; i < n; ++i) {
        int max_row = i;
        for (int k = i + 1; k < n; ++k) {
            if (std::abs(A[k][i]) > std::abs(A[max_row][i])) max_row = k;
        }
        std::swap(A[i], A[max_row]);
        std::swap(B[i], B[max_row]);

        for (int k = i + 1; k < n; ++k) {
            double c = -A[k][i] / A[i][i];
            for (int j = i; j < n; ++j) A[k][j] += c * A[i][j];
            B[k] += c * B[i];
        }
    }

    std::vector<double> coefs(n);
    for (int i = n - 1; i >= 0; --i) {
        double s = B[i];
        for (int j = i + 1; j < n; ++j) s -= A[i][j] * coefs[j];
        coefs[i] = s / A[i][i];
    }
    std::reverse(coefs.begin(), coefs.end());
    return coefs;
}

double polyval(const std::vector<double>& coefs, double x) {
    double r = 0.0;
    for (double c : coefs) r = r * x + c;
    return r;
}

// ... существующий код ...

int main() {
    // загрузка всех точек сечения 0
    std::vector<double> angles_all, radii_all, ideal_all;

    std::ifstream f("synthetic_data.csv");
    std::string line;
    std::getline(f, line);
    while (std::getline(f, line)) {
        std::stringstream ss(line);
        std::string tok;
        std::getline(ss, tok, ','); int sid = std::stoi(tok);
        std::getline(ss, tok, ','); double h = std::stod(tok);
        std::getline(ss, tok, ','); double a = std::stod(tok);
        std::getline(ss, tok, ','); double r = std::stod(tok);
        std::getline(ss, tok, ','); double ri = std::stod(tok);
        if (sid != 0) continue;
        angles_all.push_back(a);
        radii_all.push_back(r);
        ideal_all.push_back(ri);
    }

    // сортировка (как в pipeline)
    std::vector<int> idx(angles_all.size());
    std::iota(idx.begin(), idx.end(), 0);
    std::sort(idx.begin(), idx.end(),
              [&](int i, int j){ return angles_all[i] < angles_all[j]; });

    std::vector<double> A, R, I;
    for (int i : idx) { A.push_back(angles_all[i]); R.push_back(radii_all[i]); I.push_back(ideal_all[i]); }

    // 8 патчей
    int n_patches = 8;
    double half_sector = 360.0 / n_patches / 2.0;  // 22.5
    double overlap_train = 15.0;
    double overlap_use = 5.0;
    double half_train = half_sector + overlap_train;  // 37.5
    double half_use = half_sector + overlap_use;      // 27.5

    // центры патчей
    std::vector<double> centers;
    for (int i = 0; i < n_patches; ++i) {
        centers.push_back(i * 360.0 / n_patches + half_sector);
    }

    // обучение — те же степени, что в логе
    std::vector<int> degs = {12, 14, 14, 12, 4, 14, 14, 4};
    std::vector<std::vector<double>> coefs_all(n_patches);

    for (int p = 0; p < n_patches; ++p) {
        double c = centers[p];
        std::vector<double> xn, y;
        for (size_t i = 0; i < A.size(); ++i) {
            double dx = A[i] - c;
            if (dx < -180) dx += 360;
            if (dx >  180) dx -= 360;
            if (std::abs(dx) <= half_train) {
                xn.push_back(dx / half_train);
                y.push_back(R[i]);
            }
        }
        coefs_all[p] = polyfit(xn, y, degs[p]);
        std::cout << "patch " << p << " n=" << xn.size() << " deg=" << degs[p] << "\n";
    }

    // blend eval
    double sq = 0.0, mx = 0.0;
    for (size_t i = 0; i < A.size(); ++i) {
        double a = A[i];
        double sw = 0.0, swv = 0.0;
        for (int p = 0; p < n_patches; ++p) {
            double dx = a - centers[p];
            if (dx < -180) dx += 360;
            if (dx >  180) dx -= 360;
            double d = std::abs(dx);

            double w = 0.0;
            if (d <= half_sector) w = 1.0;
            else if (d <= half_use) {
                double t = 1.0 - (d - half_sector) / (half_use - half_sector);
                w = t * t * (3.0 - 2.0 * t);
            }
            if (w > 0.0) {
                double xn = dx / half_train;
                double r = polyval(coefs_all[p], xn);
                swv += w * r;
                sw  += w;
            }
        }
        double fit = (sw > 0) ? swv / sw : 0.0;
        double err = fit - I[i];
        sq += err * err;
        if (std::abs(err) > mx) mx = std::abs(err);
    }
    std::cout << "BLEND RMSE = " << std::sqrt(sq / A.size())
              << ", max = " << mx << "\n";
    return 0;
}