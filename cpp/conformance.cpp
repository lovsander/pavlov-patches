// pappa_conformance — проверка порта по КОНФОРМАНС-ВЕКТОРАМ (CONTEXT §27).
//
// Что это: spec/conformance/vectors/*.json — «золотые» пары «вход → ожидаемый
// выход», сгенерированные референсом на Python (studies/make_conformance.py).
// Утилита читает ИХ ЖЕ (через свой json_reader), прогоняет свой код на том же
// входе и сверяет результат с ожиданием. Так порт проверяется БЕЗ Python и без
// папок образцов: достаточно самих векторов.
//
// Три вида (по ступеням пайплайна):
//   model    — степени, коэффициенты, термины фичера, контур (допуск curve_mm);
//   detector — зоны и центры ям;
//   cleaner  — номера отброшенных точек.
//
// Запуск:  pappa_conformance <каталог с векторами>
// Коды:    0 — все векторы прошли; 1 — есть расхождения; 2 — не найден каталог.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include "auto_outlier_cleaner.h"
#include "json_reader.h"
#include "patch_approximator.h"
#include "pit_detector.h"

namespace fs = std::filesystem;
using pappa::JsonValue;

namespace {

struct Result {
    std::string name;
    std::string kind;
    bool ok = false;
    std::vector<std::string> notes;   // что именно разошлось
};

std::string fmt(double v, int prec = 6) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.*g", prec, v);
    return buf;
}

std::vector<double> read_numbers(const JsonValue& array_like) {
    std::vector<double> out;
    out.reserve(array_like.size());
    for (size_t i = 0; i < array_like.size(); ++i) {
        out.push_back(array_like.at(i).as_number());
    }
    return out;
}


std::string join_ints(const std::vector<int>& v);   // определение ниже


// --- модель: обучение и сверка контура ---
Result check_model(const JsonValue& v) {
    Result res;
    res.name = v.string_or("name", "?");
    res.kind = "model";

    const JsonValue& cfg = v.at("config");
    const JsonValue& expected = v.at("expected");
    const std::vector<double> angles = read_numbers(v.at("input").at("angles_deg"));
    const std::vector<double> radii = read_numbers(v.at("input").at("radii_mm"));
    const std::vector<double> pits_deg = read_numbers(cfg.at("pits_deg"));

    pappa::PatchApproximator model(
        cfg.int_or("n_patches", 7), cfg.int_or("deg_min", 4), cfg.int_or("deg_max", 14),
        cfg.number_or("amplitude_scale", 180.0), cfg.number_or("overlap_train", 15.0),
        cfg.number_or("overlap_use", 5.0), cfg.number_or("phase_deg", 0.0),
        cfg.number_or("deg_elbow_tol", 0.05), cfg.string_or("coord_mode", "normalized"));
    if (!pits_deg.empty()) {
        model.set_pit_shape(cfg.number_or("sigma_deg", 3.0),
                            cfg.number_or("pit_core_sigma", 2.0),
                            cfg.number_or("pit_window_sigma", 3.2),
                            cfg.number_or("pit_min_amp", 3e-3),
                            cfg.has("tapering") ? cfg.at("tapering").as_bool() : true);
        model.set_pits(pits_deg);
    }
    model.fit(angles, radii);

    const double tol_floor = v.at("tolerance").number_or("coefs_abs_floor", 1e-8);
    const double tol_rel = v.at("tolerance").number_or("coefs_rel", 1e-9);
    const double tol_curve = v.at("tolerance").number_or("curve_mm", 1e-6);

    std::vector<int> expected_deg;
    for (size_t i = 0; i < expected.at("degrees").size(); ++i) {
        expected_deg.push_back(expected.at("degrees").at(i).as_int());
    }
    const std::vector<int> got_deg = model.get_degrees();
    if (got_deg != expected_deg) {
        res.notes.push_back("степени: получено [" + join_ints(got_deg) +
                            "], ожидалось [" + join_ints(expected_deg) + "]");
    }

    const JsonValue& exp_coefs = expected.at("coefs");
    const JsonValue& exp_terms = expected.at("pit_terms");
    double worst_ratio = 0.0;          // Δ / допуск, > 1 — расхождение
    double worst_coef = 0.0;
    for (size_t p = 0; p < exp_coefs.size() && p < model.patches().size(); ++p) {
        const pappa::Patch& patch = model.patches()[p];
        const JsonValue& want = exp_coefs.at(p);
        if (want.size() != patch.coefs.size()) {
            res.notes.push_back("патч " + std::to_string(p) + ": коэффициентов " +
                                std::to_string(patch.coefs.size()) + " != " +
                                std::to_string(want.size()));
            continue;
        }
        for (size_t k = 0; k < want.size(); ++k) {
            const double expected_value = want.at(k).as_number();
            const double delta = std::abs(patch.coefs[k] - expected_value);
            const double allowed =
                std::max(tol_floor, tol_rel * std::abs(expected_value));
            worst_coef = std::max(worst_coef, delta);
            worst_ratio = std::max(worst_ratio, delta / allowed);
        }
        const JsonValue& want_terms = exp_terms.at(p);
        const std::vector<double> want_dx = read_numbers(want_terms.at("dx_deg"));
        const std::vector<double> want_amp = read_numbers(want_terms.at("amp"));
        if (want_dx.size() != patch.pit_offsets_deg.size()) {
            res.notes.push_back("патч " + std::to_string(p) + ": терминов фичера " +
                                std::to_string(patch.pit_offsets_deg.size()) + " != " +
                                std::to_string(want_dx.size()));
            continue;
        }
        for (size_t k = 0; k < want_dx.size(); ++k) {
            if (std::abs(patch.pit_offsets_deg[k] - want_dx[k]) > 1e-9) {
                res.notes.push_back("патч " + std::to_string(p) + ": dx фичера " +
                                    fmt(patch.pit_offsets_deg[k]) + " != " + fmt(want_dx[k]));
            }
            if (std::abs(patch.pit_coefs[k] - want_amp[k]) >
                std::max(tol_floor, tol_rel * std::abs(want_amp[k]))) {
                res.notes.push_back("патч " + std::to_string(p) + ": амплитуда фичера " +
                                    fmt(patch.pit_coefs[k]) + " != " + fmt(want_amp[k]));
            }
        }
    }
    if (worst_ratio > 1.0) {
        res.notes.push_back("коэффициенты: расхождение " + fmt(worst_coef) +
                            " мм при допуске (отн. " + fmt(tol_rel) + ", порог " +
                            fmt(tol_floor) + "), отношение " + fmt(worst_ratio, 3));
    }

    const JsonValue& curve = expected.at("curve");
    const std::vector<double> grid = read_numbers(curve.at("angles_deg"));
    const std::vector<double> want_y = read_numbers(curve.at("radii_mm"));
    const std::vector<double> got_y = model.eval(grid);
    double worst_curve = 0.0;
    for (size_t i = 0; i < got_y.size() && i < want_y.size(); ++i) {
        worst_curve = std::max(worst_curve, std::abs(got_y[i] - want_y[i]));
    }
    if (worst_curve > tol_curve) {
        res.notes.push_back("контур: максимум расхождения " + fmt(worst_curve) +
                            " > допуска " + fmt(tol_curve));
    }

    res.ok = res.notes.empty();
    return res;
}

std::string join_ints(const std::vector<int>& v) {
    std::string s;
    for (size_t i = 0; i < v.size(); ++i) s += (i ? "," : "") + std::to_string(v[i]);
    return s;
}


// --- детектор: зоны и центры ---
Result check_detector(const JsonValue& v) {
    Result res;
    res.name = v.string_or("name", "?");
    res.kind = "detector";

    const JsonValue& cfg = v.at("config");
    const std::vector<double> angles = read_numbers(v.at("input").at("angles_deg"));
    const std::vector<double> radii = read_numbers(v.at("input").at("radii_mm"));

    pappa::PitDetectorOptions opt;
    opt.baseline_deg = cfg.number_or("window_deg", 1.0);
    opt.wide_deg = cfg.number_or("wide_deg", 10.0);
    opt.smooth_deg = cfg.number_or("smooth_deg", 2.0);
    opt.k = cfg.number_or("k", 5.5);
    opt.min_zone_deg = cfg.number_or("min_zone_deg", 2.0);
    const pappa::PitDetector detector(opt);

    const std::vector<double> got_pits = detector.pits(angles, radii);
    const std::vector<double> want_pits = read_numbers(v.at("expected").at("pits_deg"));
    if (got_pits.size() != want_pits.size()) {
        res.notes.push_back("ям найдено " + std::to_string(got_pits.size()) +
                            ", ожидалось " + std::to_string(want_pits.size()));
    }
    for (size_t i = 0; i < std::min(got_pits.size(), want_pits.size()); ++i) {
        if (std::abs(got_pits[i] - want_pits[i]) > 1e-6) {
            res.notes.push_back("центр ямы " + std::to_string(i) + ": " +
                                fmt(got_pits[i]) + " != " + fmt(want_pits[i]));
        }
    }
    res.ok = res.notes.empty();
    return res;
}

// --- очистка: номера отброшенных точек ---
Result check_cleaner(const JsonValue& v) {
    Result res;
    res.name = v.string_or("name", "?");
    res.kind = "cleaner";

    const JsonValue& cfg = v.at("config");
    const std::vector<double> angles = read_numbers(v.at("input").at("angles_deg"));
    const std::vector<double> radii = read_numbers(v.at("input").at("radii_mm"));

    pappa::AutoOutlierCleaner cleaner(cfg.number_or("baseline_deg", 1.0),
                                      cfg.number_or("iqr_k", 3.0));
    const std::vector<bool> mask = cleaner.clean(angles, radii);

    std::vector<long long> got;
    for (size_t i = 0; i < mask.size(); ++i) {
        if (mask[i]) got.push_back(static_cast<long long>(i));
    }
    const JsonValue& want = v.at("expected").at("mask_true_indices");
    std::vector<long long> want_idx;
    for (size_t i = 0; i < want.size(); ++i) want_idx.push_back(want.at(i).as_int());

    if (got != want_idx) {
        res.notes.push_back("отброшено " + std::to_string(got.size()) +
                            " точек, ожидалось " + std::to_string(want_idx.size()));
        size_t shown = 0;
        for (size_t i = 0; i < std::max(got.size(), want_idx.size()) && shown < 5; ++i) {
            const long long a = i < got.size() ? got[i] : -1;
            const long long b = i < want_idx.size() ? want_idx[i] : -1;
            if (a != b) {
                res.notes.push_back("  позиция " + std::to_string(i) + ": получено " +
                                    std::to_string(a) + ", ожидалось " + std::to_string(b));
                ++shown;
            }
        }
    }
    res.ok = res.notes.empty();
    return res;
}

}  // namespace


int main(int argc, char** argv) {
    if (argc < 2) {
        std::cout << "Использование: pappa_conformance <каталог с векторами>\n"
                     "  например:  pappa_conformance ../spec/conformance/vectors\n";
        return 2;
    }
    const fs::path dir = argv[1];
    if (!fs::is_directory(dir)) {
        std::cerr << "Не найден каталог векторов: " << dir.string() << "\n";
        return 2;
    }

    std::vector<fs::path> files;
    for (const auto& entry : fs::directory_iterator(dir)) {
        if (entry.is_regular_file() && entry.path().extension() == ".json") {
            files.push_back(entry.path());
        }
    }
    std::sort(files.begin(), files.end());
    if (files.empty()) {
        std::cerr << "В каталоге нет *.json: " << dir.string() << "\n";
        return 2;
    }

    std::cout << "Конформанс-векторы PAPPA: " << files.size() << " файл(ов) в "
              << dir.string() << "\n\n";
    int failed = 0;
    for (const fs::path& file : files) {
        Result res;
        try {
            const JsonValue v = pappa::parse_json_file(file.string());
            const std::string format = v.string_or("format", "");
            const std::string kind = v.string_or("kind", "");
            if (format != "pappa-conformance") {
                res.kind = kind;
                res.name = file.filename().string();
                res.notes.push_back("формат \"" + format +
                                    "\", ожидался \"pappa-conformance\"");
            } else if (kind == "model") {
                res = check_model(v);
            } else if (kind == "detector") {
                res = check_detector(v);
            } else if (kind == "cleaner") {
                res = check_cleaner(v);
            } else {
                res.kind = kind;
                res.name = file.filename().string();
                res.notes.push_back("неизвестный kind: \"" + kind + "\"");
            }
        } catch (const std::exception& e) {
            res.name = file.filename().string();
            res.notes.push_back(std::string("исключение: ") + e.what());
        }

        std::cout << (res.ok ? "[OK]   " : "[FAIL] ") << file.filename().string()
                  << "  (" << res.kind << ", " << res.name << ")\n";
        for (const std::string& note : res.notes) std::cout << "         " << note << "\n";
        if (!res.ok) ++failed;
    }

    std::cout << "\nИтог: " << (files.size() - static_cast<size_t>(failed)) << "/"
              << files.size() << " векторов пройдено\n";
    return failed == 0 ? 0 : 1;
}
