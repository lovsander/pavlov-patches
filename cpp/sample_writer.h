#ifndef PAPPA_SAMPLE_WRITER_H
#define PAPPA_SAMPLE_WRITER_H

#include <string>
#include <vector>

#include "section_model.h"

// Запись папки образца портом — тот же контракт, что у Python
// (python/pappa/io/sample_store.py + io/model_file.py, CONTEXT §27):
//
//   <out_dir>/sample.json                манифест (format pappa-sample v1.0)
//   <out_dir>/sections/00.pappa.json     документ описания сечения (pappa v2.0)
//
// Имя файла — по порядку сечений, section_id и высота — внутри документа.
// Так папки, собранные Python-ом и портом, сравниваются численно
// (python/studies/verify_port.py) без всякой договорённости «на словах».

namespace pappa {

// Версия порта: пишется в документ, чтобы было видно, ЧЕМ он записан.
constexpr const char* PORT_VERSION = "0.1.0";

struct SampleOptions {
    std::string name = "sample";
    std::string input_csv;
    std::string description;
    // параметры метода — в манифест, для воспроизводимости
    double cleaner_baseline_deg = 1.0;
    double cleaner_iqr_k = 3.0;
    bool pits = false;
    std::string detector_json;       // готовый JSON-объект или пусто
};

// Записать образец. Возвращает путь каталога.
std::string save_sample(const std::string& out_dir, const std::string& name,
                        const std::vector<SectionModel>& sections,
                        const SampleOptions& opt);

// Записать документ одного сечения.
std::string save_section_document(const std::string& path,
                                  const SectionModel& section);

}  // namespace pappa

#endif  // PAPPA_SAMPLE_WRITER_H
