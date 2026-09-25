#include "sample_writer.h"

#include <algorithm>
#include <ctime>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <stdexcept>

#include "json_writer.h"
#include "section_model.h"

namespace pappa {

namespace {

std::string iso_utc_now() {
    std::time_t t = std::time(nullptr);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &t);
#else
    gmtime_r(&t, &tm);
#endif
    std::ostringstream os;
    os << std::put_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
    return os.str();
}

// Двузначный номер файла сечения: 00, 01, ...
std::string index_name(size_t i) {
    std::ostringstream os;
    os << std::setw(2) << std::setfill('0') << i << ".pappa.json";
    return os.str();
}

void write_patches(JsonWriter& w, const PatchApproximator& m) {
    w.key("patches");
    w.begin_array();
    for (const Patch& p : m.patches()) {
        w.begin_object();
        w.kv("center_deg", p.center);
        w.kv("degree", p.degree);
        w.kv("n_points", p.n_points);
        w.key("coefs");
        w.begin_array();
        for (double c : p.coefs) w.value(c);
        w.end_array();

        w.key("metrics");
        w.begin_object();
        w.kv("amplitude_mm", p.amplitude_mm);
        w.kv("mean_radius_mm", p.mean_radius_mm);
        w.kv("amplitude_norm", p.amplitude_norm);
        w.kv("deg_elbow_tol", m.deg_elbow_tol());
        w.kv("rmse_selected_mm", p.rmse_selected_mm);
        w.kv("rmse_best_mm", p.rmse_best_mm);
        w.kv("n_train_points", p.n_points);
        w.end_object();

        w.key("stats");
        w.begin_object();
        w.kv("rmse_mm", p.rmse_mm);
        w.kv("mae_mm", p.mae_mm);
        w.kv("max_err_mm", p.max_err_mm);
        w.kv("correlation", p.correlation);
        w.end_object();

        // Термины фичера ям пишем ВСЕГДА, когда модель с ямами — включая пустой
        // список у патчей, которые ям не видят: Python-загрузчик ожидает ключ у
        // каждого патча (ровно так же пишет python-референс). Отсутствие ключа
        // роняло eval() — этот баг нашла сверка порта (verify_port).
        if (m.has_pits()) {
            w.key("pit_terms");
            w.begin_array();
            for (size_t j = 0; j < p.pit_offsets_deg.size(); ++j) {
                w.begin_object();
                w.kv("dx_deg", p.pit_offsets_deg[j]);
                w.kv("amp", p.pit_coefs[j]);
                w.end_object();
            }
            w.end_array();
        }
        w.end_object();
    }
    w.end_array();
}

}  // namespace

std::string save_section_document(const std::string& path,
                                  const SectionModel& section) {
    const PatchApproximator& m = section.model;
    if (!m.is_fitted()) {
        throw std::runtime_error("save_section_document: модель не обучена");
    }

    JsonWriter w(2);
    w.begin_object();
    w.kv("format", "pappa");
    w.kv("version", "2.0");
    w.kv("method", m.has_pits() ? "PitPatchApproximator" : "PatchApproximator");
    w.kv("created", iso_utc_now());

    w.key("software");
    w.begin_object();
    w.kv("language", "cpp");
    w.kv("pappa_version", std::string(PORT_VERSION));
    w.end_object();

    w.key("meta");
    w.begin_object();
    w.kv("section_id", section.section_id);
    w.kv("height_mm", section.height_mm);
    w.kv("source", section.source);
    w.kv("description", section.description);
    w.end_object();

    w.key("global");
    w.begin_object();
    w.key("units");
    w.begin_object();
    w.kv("angle", "degree");
    w.kv("length", "mm");
    w.end_object();
    w.kv("n_patches", m.n_patches());
    w.kv("half_sector_deg", m.half_sector());
    w.kv("phase_deg", m.phase_deg());
    w.kv("half_train_deg", m.half_train());
    w.kv("half_use_deg", m.half_use());
    w.kv("overlap_train_deg", m.overlap_train());
    w.kv("overlap_use_deg", m.overlap_use());
    w.kv("deg_min", m.deg_min());
    w.kv("deg_max", m.deg_max());
    w.kv("coord_mode", m.coord_mode());
    w.kv("deg_elbow_tol", m.deg_elbow_tol());
    w.kv("amplitude_scale", m.amplitude_scale());
    if (m.has_pits()) {
        w.key("pit");
        w.begin_object();
        w.kv("sigma_deg", m.sigma_deg());
        w.kv("core_sigma", m.pit_core_sigma());
        w.kv("window_sigma", m.pit_window_sigma());
        w.kv("pit_min_amp", m.pit_min_amp());
        w.kv("tapering", m.tapering());
        w.key("centers_deg");
        w.begin_array();
        for (double c : m.pits()) w.value(c);
        w.end_array();
        w.end_object();
    }
    w.end_object();

    write_patches(w, m);

    w.key("statistics");
    w.begin_object();
    w.kv("n_points_total", section.n_points_total);
    w.kv("n_outliers_removed", section.n_outliers);
    w.kv("fit_time_ms", section.fit_time_ms);
    w.end_object();

    w.end_object();
    w.save(path);
    return path;
}

std::string save_sample(const std::string& out_dir, const std::string& name,
                        const std::vector<SectionModel>& sections,
                        const SampleOptions& opt) {
    namespace fs = std::filesystem;
    const fs::path root = fs::path(out_dir);
    fs::create_directories(root / "sections");

    // Порядок документов — по возрастанию section_id (имена файлов 00, 01, ...).
    std::vector<const SectionModel*> ordered;
    ordered.reserve(sections.size());
    for (const SectionModel& s : sections) ordered.push_back(&s);
    std::sort(ordered.begin(), ordered.end(),
              [](const SectionModel* a, const SectionModel* b) {
                  return a->section_id < b->section_id;
              });

    JsonWriter w(2);
    w.begin_object();
    w.kv("format", "pappa-sample");
    w.kv("version", "1.0");
    w.kv("name", name);
    w.kv("created", iso_utc_now());

    w.key("units");
    w.begin_object();
    w.kv("angle", "degree");
    w.kv("length", "mm");
    w.end_object();

    w.key("meta");
    w.begin_object();
    w.kv("description", opt.description);
    w.end_object();

    if (!opt.input_csv.empty()) {
        w.key("input");
        w.begin_object();
        w.kv("csv", opt.input_csv);
        w.end_object();
    }

    w.key("config");
    w.begin_object();
    const PatchApproximator* first = ordered.empty() ? nullptr : &ordered.front()->model;
    w.kv("n_patches", first ? first->n_patches() : 0);
    w.kv("phase_deg", first ? first->phase_deg() : 0.0);
    w.kv("deg_min", first ? first->deg_min() : 0);
    w.kv("deg_max", first ? first->deg_max() : 0);
    w.kv("overlap_train", first ? first->overlap_train() : 0.0);
    w.kv("overlap_use", first ? first->overlap_use() : 0.0);
    w.kv("deg_elbow_tol", first ? first->deg_elbow_tol() : 0.0);
    w.key("cleaner");
    {
        std::ostringstream os;
        os << "{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", "
           << "\"baseline_deg\": " << opt.cleaner_baseline_deg
           << ", \"iqr_k\": " << opt.cleaner_iqr_k << "}}";
        w.raw_value(os.str());
    }
    w.kv("pits", opt.pits);
    if (opt.pits && first) {
        w.kv("sigma_deg", first->sigma_deg());
        w.kv("pit_core_sigma", first->pit_core_sigma());
        w.kv("pit_window_sigma", first->pit_window_sigma());
        w.kv("pit_min_amp", first->pit_min_amp());
        w.kv("tapering", first->tapering());
    }
    w.key("detector");
    if (opt.detector_json.empty()) w.value_null();
    else w.raw_value(opt.detector_json);
    w.end_object();

    w.key("sections");
    w.begin_array();
    for (size_t i = 0; i < ordered.size(); ++i) {
        const SectionModel& s = *ordered[i];
        const std::string file = "sections/" + index_name(i);
        save_section_document((root / file).string(), s);
        w.begin_object();
        w.kv("index", static_cast<int>(i));
        w.kv("section_id", s.section_id);
        w.kv("height_mm", s.height_mm);
        w.kv("file", file);
        w.kv("n_points", s.n_points_total);
        w.kv("n_outliers", s.n_outliers);
        w.end_object();
    }
    w.end_array();

    w.end_object();
    w.save((root / "sample.json").string());
    return root.string();
}

}  // namespace pappa

