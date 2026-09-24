#define _USE_MATH_DEFINES
#ifdef _WIN32
    #include <windows.h>
#endif
#include "geometry_pipeline.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <clocale>
#include <iomanip>
#include <algorithm>
#include <cmath>
#include <map>

struct RowData
{
    int section_id;
    double height_mm, angle_deg, radius_mm, radius_ideal_mm;
    bool is_outlier;
};

std::vector<RowData> load_csv(const std::string &filename)
{
    std::ifstream file(filename);
    if (!file.is_open())
        throw std::runtime_error("Не удалось открыть: " + filename);
    std::vector<RowData> rows;
    std::string line;
    if (!std::getline(file, line))
        return rows; // header

    while (std::getline(file, line))
    {
        line.erase(std::remove(line.begin(), line.end(), '\r'), line.end());
        std::stringstream ss(line);
        std::string token;
        RowData r;

        if (!std::getline(ss, token, ','))
            continue;
        r.section_id = std::stoi(token);
        std::getline(ss, token, ',');

        r.height_mm = std::stod(token);
        std::getline(ss, token, ',');

        r.angle_deg = std::stod(token);
        std::getline(ss, token, ',');

        r.radius_mm = std::stod(token);
        std::getline(ss, token, ',');

        r.radius_ideal_mm = std::stod(token);
        // дальше поля не нужны
        for (int k = 0; k < 6; ++k)
            std::getline(ss, token, ',');
        std::getline(ss, token, ',');
        std::transform(token.begin(), token.end(), token.begin(),
                       [](unsigned char c)
                       { return std::tolower(c); });
        r.is_outlier = (token == "true" || token == "1");
        rows.push_back(r);
        if (rows.size() <= 5)
        {
            std::cout << "  [lc] loaded: sec=" << r.section_id
                      << " h=" << r.height_mm
                      << " angle=" << r.angle_deg
                      << " r=" << r.radius_mm
                      << " ideal=" << r.radius_ideal_mm
                      << "\n";
        }
    }
    return rows;
}

void save_results_csv(const std::string &filename,
                      const std::vector<SectionResult> &results)
{
    std::ofstream f(filename);
    if (!f.is_open())
        throw std::runtime_error("Не могу открыть для записи: " + filename);
    f << "section_id,height_mm,angle_deg,radius_fine_mm,radius_coarse_mm\n";
    f << std::fixed << std::setprecision(6);
    for (const auto &r : results)
    {
        for (size_t i = 0; i < r.angles.size(); ++i)
        {
            f << r.section_id << ","
              << r.height_mm << ","
              << r.angles[i] << ","
              << r.fitted_fine[i] << ","
              << r.fitted_coarse[i] << "\n";
        }
    }
    std::cout << "\n[OK] Результаты сохранены: " << filename << "\n";
}

int main()
{
    std::setlocale(LC_NUMERIC, "C");

// Консоль Windows — в UTF-8 для корректного вывода кириллицы.
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
#endif

    std::string input_file = "synthetic_data.csv";
    std::string output_file = "smoothed_geometry_output.csv";

    std::cout << "=== ГЕОМЕТРИЧЕСКИЙ ПАЙПЛАЙН (C++) ===\n";
    try
    {

        auto raw_data = load_csv(input_file);
        std::cout << "[OK] Загружено строк: " << raw_data.size() << "\n";
        {
            std::ifstream fcheck(input_file);
            std::string linecheck;
            int cnt = 0;
            std::cout << "\n[file] первые 5 строк физически:\n";
            while (std::getline(fcheck, linecheck))
            {
                if (cnt < 5)
                    std::cout << "  " << linecheck << "\n";
                cnt++;
            }
            std::cout << "[file] всего строк: " << cnt << "\n\n";
        }

        // ===== DEBUG =====
        std::cout << "\n[DEBUG] Первые 5 строк из raw_data:\n";
        for (size_t i = 0; i < 5 && i < raw_data.size(); ++i)
        {
            std::cout << "  sec=" << raw_data[i].section_id
                      << " h=" << raw_data[i].height_mm
                      << " angle=" << raw_data[i].angle_deg
                      << " radius=" << raw_data[i].radius_mm
                      << " ideal=" << raw_data[i].radius_ideal_mm
                      << " out=" << raw_data[i].is_outlier
                      << "\n";
        }
        // =================

        std::vector<int> section_ids;
        std::vector<double> heights, angles, radii;
        section_ids.reserve(raw_data.size());
        heights.reserve(raw_data.size());
        angles.reserve(raw_data.size());
        radii.reserve(raw_data.size());

        for (const auto &r : raw_data)
        {
            section_ids.push_back(r.section_id);
            heights.push_back(r.height_mm);
            angles.push_back(r.angle_deg);
            radii.push_back(r.radius_mm);
        }

        GeometryPipeline pipeline(0.5, 9.5, 3.5);
        auto results = pipeline.process_batch(section_ids, heights, angles, radii);

        save_results_csv(output_file, results);

        // ====== RMSE / MAE / max — НА РЕАЛЬНЫХ УГЛАХ, БЕЗ СЕТКИ ======
        // Сравниваем fitted_fine против radius_ideal_mm
        // Оба массива — в порядке возрастания углов, потому что raw отсортирован
        // в geometry_pipeline. Значит, i-й элемент fitted_fine соответствует
        // i-му элементу angles из результата (sec_angles), а он — тому же углу из raw.

        // Строим индекс: (section_id, angle) -> radius_ideal_mm из raw_data
        std::map<int, std::map<double, double>> ideal_by_sec;
        for (const auto &r : raw_data)
        {
            ideal_by_sec[r.section_id][r.angle_deg] = r.radius_ideal_mm;
        }
        // ===== DEBUG =====
        for (const auto &r : results)
        {
            if (r.section_id != 0)
                continue;
            std::cout << "\n[DEBUG] Сечение 0, первые 10 точек:\n";
            std::cout << std::setw(10) << "angle"
                      << std::setw(14) << "fine"
                      << std::setw(14) << "coarse"
                      << std::setw(14) << "ideal"
                      << std::setw(14) << "err_fine"
                      << "\n";
            for (size_t i = 0; i < 10; ++i)
            {
                auto it = ideal_by_sec[r.section_id].find(r.angles[i]);
                double ideal = (it != ideal_by_sec[r.section_id].end()) ? it->second : -999.0;
                std::cout << std::setw(10) << r.angles[i]
                          << std::setw(14) << r.fitted_fine[i]
                          << std::setw(14) << r.fitted_coarse[i]
                          << std::setw(14) << ideal
                          << std::setw(14) << (r.fitted_fine[i] - ideal)
                          << "\n";
            }
            break;
        }
        // ================

        std::cout << "\n=== МЕТРИКИ (Fine vs Идеал, БЕЗ сетки) ===\n";
        std::cout << std::fixed << std::setprecision(6);
        std::cout << std::setw(6) << "sec"
                  << std::setw(14) << "RMSE, мм"
                  << std::setw(14) << "MAE, мм"
                  << std::setw(14) << "max, мм"
                  << std::setw(10) << "N"
                  << "\n";

        double g_sq = 0.0, g_abs = 0.0, g_max = 0.0;
        size_t g_n = 0;

        for (const auto &r : results)
        {
            double sq = 0.0, ab = 0.0, mx = 0.0;
            size_t n = 0;
            for (size_t i = 0; i < r.angles.size(); ++i)
            {
                auto it_ideal = ideal_by_sec[r.section_id].find(r.angles[i]);
                if (it_ideal == ideal_by_sec[r.section_id].end())
                    continue;
                double ideal = it_ideal->second;
                double err = r.fitted_fine[i] - ideal;
                sq += err * err;
                ab += std::abs(err);
                if (std::abs(err) > mx)
                    mx = std::abs(err);
                ++n;
            }
            if (n == 0)
                continue;
            double rmse = std::sqrt(sq / n);
            double mae = ab / n;

            std::cout << std::setw(6) << r.section_id
                      << std::setw(14) << rmse
                      << std::setw(14) << mae
                      << std::setw(14) << mx
                      << std::setw(10) << n
                      << "\n";

            g_sq += sq;
            g_abs += ab;
            if (mx > g_max)
                g_max = mx;
            g_n += n;
        }

        std::cout << "\n--- СРЕДНЕЕ ПО ВСЕМ СЕЧЕНИЯМ ---\n";
        std::cout << "RMSE:         " << std::sqrt(g_sq / g_n) << " мм\n";
        std::cout << "MAE:          " << (g_abs / g_n) << " мм\n";
        std::cout << "Макс. ошибка: " << g_max << " мм\n";
        std::cout << "Всего точек:  " << g_n << "\n";

        // ====== Δ (Fine - Coarse) ======
        std::cout << "\n=== Δ (Fine − Coarse) по сечениям ===\n";
        std::cout << std::setw(6) << "sec"
                  << std::setw(16) << "max|Δ|, мм"
                  << std::setw(16) << "mean|Δ|, мм"
                  << "\n";
        for (const auto &r : results)
        {
            double mx = 0.0, mean_abs = 0.0;
            size_t n = r.angles.size();
            for (size_t i = 0; i < n; ++i)
            {
                double d = std::abs(r.fitted_fine[i] - r.fitted_coarse[i]);
                if (d > mx)
                    mx = d;
                mean_abs += d;
            }
            mean_abs /= n;
            std::cout << std::setw(6) << r.section_id
                      << std::setw(16) << mx
                      << std::setw(16) << mean_abs
                      << "\n";
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Критическая ошибка: " << e.what() << "\n";
        std::cin.get();
        return 1;
    }

    std::cout << "\nГотово. Нажмите ENTER...";
    std::cin.clear();
    std::cin.get();
    return 0;
}