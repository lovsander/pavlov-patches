// PAPPA — порт C++: CLI пайплайна (CONTEXT §27, шаг 4).
//
// Читает CSV с сечениями, чистит выбросы, обучает модель на каждое сечение и
// пишет ПАПКУ ОБРАЗЦА тем же форматом, что Python:
//     <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
// После этого папки сравниваются численно:
//     python python/studies/verify_port.py --cpp-dir <out-dir>
//
// Запуск (пример, одна строка):
//   pappa_pipeline --input python/synthetic_data.csv --out-dir samples/body_cpp --name body --self-check
// Пауза «нажмите ENTER» по умолчанию ВЫКЛЮЧЕНА (нужна была для запуска двойным
// щелчком); включается ключом --pause.

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "geometry_pipeline.h"
#include "sample_writer.h"
#include "section_model.h"

namespace {

struct CsvData {
    std::vector<int> section_ids;
    std::vector<double> heights;
    std::vector<double> angles;
    std::vector<double> radii;
    std::vector<double> ideal;      // эталон, если колонка есть
    bool has_ideal = false;
    size_t n_rows = 0;
};

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : line) {
        if (c == ',') { out.push_back(cur); cur.clear(); }
        else if (c != '\r') { cur.push_back(c); }
    }
    out.push_back(cur);
    return out;
}

// Загрузка CSV по ЗАГОЛОВКУ: имена колонок, а не их порядок. Обязательны
// section_id, height_mm, angle_deg, radius_mm; radius_ideal_mm — если есть.
CsvData load_csv(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Не могу открыть CSV: " + path);

    std::string header_line;
    if (!std::getline(f, header_line)) throw std::runtime_error("Пустой CSV: " + path);
    const std::vector<std::string> header = split_csv_line(header_line);

    int i_sec = -1, i_h = -1, i_a = -1, i_r = -1, i_ideal = -1;
    for (size_t i = 0; i < header.size(); ++i) {
        const std::string& h = header[i];
        if (h == "section_id") i_sec = static_cast<int>(i);
        else if (h == "height_mm") i_h = static_cast<int>(i);
        else if (h == "angle_deg") i_a = static_cast<int>(i);
        else if (h == "radius_mm") i_r = static_cast<int>(i);
        else if (h == "radius_ideal_mm") i_ideal = static_cast<int>(i);
    }
    if (i_sec < 0 || i_h < 0 || i_a < 0 || i_r < 0) {
        throw std::runtime_error(
            "CSV должен содержать колонки section_id, height_mm, angle_deg, radius_mm");
    }

    CsvData data;
    data.has_ideal = i_ideal >= 0;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        const std::vector<std::string> fld = split_csv_line(line);
        const size_t need = static_cast<size_t>(
            std::max(std::max(i_sec, i_h), std::max(i_a, i_r)));
        if (fld.size() <= need) continue;
        data.section_ids.push_back(std::stoi(fld[static_cast<size_t>(i_sec)]));
        data.heights.push_back(std::stod(fld[static_cast<size_t>(i_h)]));
        data.angles.push_back(std::stod(fld[static_cast<size_t>(i_a)]));
        data.radii.push_back(std::stod(fld[static_cast<size_t>(i_r)]));
        if (data.has_ideal) {
            data.ideal.push_back(std::stod(fld[static_cast<size_t>(i_ideal)]));
        }
        ++data.n_rows;
    }
    return data;
}

// Линейная интерполяция замкнутого профиля на сетку (аналог ring_interp).
double ring_interp(const std::vector<double>& angles,
                   const std::vector<double>& values, double x) {
    const size_t n = angles.size();
    if (n == 0) return 0.0;
    if (n == 1) return values[0];
    double xx = std::fmod(x, 360.0);
    if (xx < 0.0) xx += 360.0;
    auto lerp = [](double x0, double y0, double x1, double y1, double t) {
        return y0 + (y1 - y0) * ((t - x0) / (x1 - x0));
    };
    if (xx <= angles.front()) {
        return lerp(angles.back() - 360.0, values.back(), angles.front(),
                    values.front(), xx);
    }
    if (xx >= angles.back()) {
        return lerp(angles.back(), values.back(), angles.front() + 360.0,
                    values.front(), xx);
    }
    for (size_t i = 1; i < n; ++i) {
        if (xx <= angles[i]) {
            return lerp(angles[i - 1], values[i - 1], angles[i], values[i], xx);
        }
    }
    return values.back();
}

}  // namespace

void print_usage() {
    std::cout <<
        "PAPPA pipeline (порт C++)\n"
        "Использование:\n"
        "  pappa_pipeline --input FILE.csv --out-dir DIR [опции]\n\n"
        "Обязательные:\n"
        "  --input FILE          CSV с колонками section_id,height_mm,angle_deg,radius_mm\n"
        "  --out-dir DIR         куда писать папку образца (sample.json + sections/)\n"
        "Раскладка и степень:\n"
        "  --name NAME           имя образца (по умолчанию — sample)\n"
        "  --n-patches N         число патчей (7)\n"
        "  --phase-deg X         общая фаза раскладки, ° (24.75)\n"
        "  --deg-min/--deg-max   диапазон чётных степеней (4/14)\n"
        "  --overlap-train X     перекрытие обучения, ° (15)\n"
        "  --overlap-use X       перекрытие применения, ° (5)\n"
        "  --deg-elbow-tol X     допуск правила «локтя» (0.05)\n"
        "Очистка (авто-iqr, штатный режим пайплайна):\n"
        "  --baseline-deg X      окно снятия формы, ° (1.0)\n"
        "  --iqr-k X             множитель IQR, усы Тьюки (3.0)\n"
        "Фичер ям (шаг 4b):\n"
        "  --pits / --no-pits    включить/выключить (в 4a по умолчанию ВЫКЛ)\n"
        "Прочее:\n"
        "  --self-check          напечатать RMSE модели и (если есть) к эталону\n"
        "  --dump-points FILE    выгрузить значения модели по сетке 0.06°\n"
        "  --quiet               только итог\n"
        "  --pause               ждать ENTER в конце (для запуска двойным щелчком)\n";
}

int main(int argc, char** argv) {
    std::string input, out_dir, name, dump_points;
    bool self_check = false, pause = false, verbose = true;
    pappa::PipelineOptions opt;
    opt.pits = false;                  // 4a: фичер ям выключен (включается в 4b)

    auto need_value = [&](int& i, const std::string& flag) -> std::string {
        if (i + 1 >= argc) throw std::runtime_error("для " + flag + " нужно значение");
        return std::string(argv[++i]);
    };

    try {
        for (int i = 1; i < argc; ++i) {
            const std::string a = argv[i];
            if (a == "--input") input = need_value(i, a);
            else if (a == "--out-dir") out_dir = need_value(i, a);
            else if (a == "--name") name = need_value(i, a);
            else if (a == "--n-patches") opt.n_patches = std::stoi(need_value(i, a));
            else if (a == "--phase-deg") opt.phase_deg = std::stod(need_value(i, a));
            else if (a == "--deg-min") opt.deg_min = std::stoi(need_value(i, a));
            else if (a == "--deg-max") opt.deg_max = std::stoi(need_value(i, a));
            else if (a == "--overlap-train") opt.overlap_train = std::stod(need_value(i, a));
            else if (a == "--overlap-use") opt.overlap_use = std::stod(need_value(i, a));
            else if (a == "--deg-elbow-tol") opt.deg_elbow_tol = std::stod(need_value(i, a));
            else if (a == "--baseline-deg") opt.baseline_deg = std::stod(need_value(i, a));
            else if (a == "--iqr-k") opt.iqr_k = std::stod(need_value(i, a));
            else if (a == "--pits") opt.pits = true;
            else if (a == "--no-pits") opt.pits = false;
            else if (a == "--sigma-deg") opt.sigma_deg = std::stod(need_value(i, a));
            else if (a == "--pit-core-sigma") opt.pit_core_sigma = std::stod(need_value(i, a));
            else if (a == "--pit-window-sigma") opt.pit_window_sigma = std::stod(need_value(i, a));
            else if (a == "--pit-min-amp") opt.pit_min_amp = std::stod(need_value(i, a));
            else if (a == "--dump-points") dump_points = need_value(i, a);
            else if (a == "--self-check") self_check = true;
            else if (a == "--quiet") verbose = false;
            else if (a == "--pause") pause = true;
            else if (a == "--help" || a == "-h") { print_usage(); return 0; }
            else throw std::runtime_error("неизвестный ключ: " + a);
        }
        if (input.empty() || out_dir.empty()) {
            print_usage();
            return 2;
        }

        opt.verbose = verbose;
        const CsvData data = load_csv(input);
        if (data.n_rows == 0) throw std::runtime_error("в CSV нет строк с данными");

        std::cout << "PAPPA pipeline (C++): " << data.n_rows << " точек, вход "
                  << input << "\n";
        pappa::GeometryPipeline pipeline(opt);
        std::vector<pappa::SectionModel> sections =
            pipeline.process(data.section_ids, data.heights, data.angles, data.radii);

        for (pappa::SectionModel& s : sections) {
            s.source = input;
            s.description = "сечение " + std::to_string(s.section_id) + ", h=" +
                            std::to_string(static_cast<int>(s.height_mm)) + " мм";
        }

        pappa::SampleOptions sopts;
        sopts.name = name.empty() ? "sample" : name;
        sopts.input_csv = input;
        sopts.description = std::string("собрано портом C++ (PAPPA v") +
                            pappa::PORT_VERSION + ")";
        sopts.cleaner_baseline_deg = opt.baseline_deg;
        sopts.cleaner_iqr_k = opt.iqr_k;
        sopts.pits = opt.pits;
        const std::string root =
            pappa::save_sample(out_dir, sopts.name, sections, sopts);

        std::cout << "\nОбразец записан: " << root << "\n"
                  << "  манифест: " << root << "/sample.json\n"
                  << "  сечений:  " << sections.size() << " (sections/*.pappa.json)\n";

        if (self_check) {
            std::cout << "\nСамопроверка:\n";
            std::cout << "  секция  точек  выброшено  max RMSE окна, мм";
            if (data.has_ideal) std::cout << "  RMSE к эталону, мм";
            std::cout << "\n";
            std::vector<double> grid;
            for (double g = 0.0; g < 360.0; g += 0.06) grid.push_back(g);
            for (const pappa::SectionModel& s : sections) {
                double rmse_win = 0.0;
                for (const pappa::Patch& p : s.model.patches()) {
                    rmse_win = std::max(rmse_win, p.rmse_mm);
                }
                std::cout << "  " << s.section_id << "      " << s.n_points_total
                          << "     " << s.n_outliers << "          " << rmse_win;
                if (data.has_ideal) {
                    std::vector<std::pair<double, double>> sec;
                    for (size_t i = 0; i < data.section_ids.size(); ++i) {
                        if (data.section_ids[i] == s.section_id) {
                            sec.emplace_back(data.angles[i], data.ideal[i]);
                        }
                    }
                    std::sort(sec.begin(), sec.end());
                    std::vector<double> ia, ir;
                    ia.reserve(sec.size());
                    ir.reserve(sec.size());
                    for (const auto& pr : sec) {
                        ia.push_back(pr.first);
                        ir.push_back(pr.second);
                    }
                    const std::vector<double> y = s.model.eval(grid);
                    double sse = 0.0;
                    for (size_t i = 0; i < grid.size(); ++i) {
                        const double e = y[i] - ring_interp(ia, ir, grid[i]);
                        sse += e * e;
                    }
                    std::cout << "         "
                              << std::sqrt(sse / static_cast<double>(grid.size()));
                }
                std::cout << "\n";
            }
        }

        if (!dump_points.empty()) {
            std::ofstream f(dump_points);
            if (!f) throw std::runtime_error("Не могу записать: " + dump_points);
            f << "section_id,height_mm,angle_deg,radius_model_mm\n";
            f.precision(12);
            for (const pappa::SectionModel& s : sections) {
                for (double g = 0.0; g < 360.0; g += 0.06) {
                    const std::vector<double> one{g};
                    f << s.section_id << "," << s.height_mm << "," << g << ","
                      << s.model.eval(one)[0] << "\n";
                }
            }
            std::cout << "Точки модели выгружены: " << dump_points << "\n";
        }

        std::cout << "\nСверка с референсом Python:\n"
                  << "  python python/studies/verify_port.py --cpp-dir " << root << "\n";
    } catch (const std::exception& e) {
        std::cerr << "Ошибка: " << e.what() << "\n";
        if (pause) std::cin.get();
        return 1;
    }

    if (pause) {
        std::cout << "\nНажмите ENTER...";
        std::cin.get();
    }
    return 0;
}

