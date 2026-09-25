#ifndef PAPPA_JSON_WRITER_H
#define PAPPA_JSON_WRITER_H

#include <string>
#include <vector>

// Минимальный писатель JSON без внешних зависимостей (CONTEXT §27, шаг 4).
//
// Зачем свой: документ .pappa.json должен писаться портом так же, как в Python
// (json.dump(indent=2, ensure_ascii=False)), включая ПОЛНУЮ точность чисел
// (17 значащих цифр), иначе сверка порта упрётся в форматирование, а не в метод.
// Схема документа — spec/pappa.schema.json (структура диктуется Python-ом).

namespace pappa {

class JsonWriter {
public:
    explicit JsonWriter(int indent = 2) : indent_(indent) {}

    void begin_object();
    void end_object();
    void begin_array();
    void end_array();

    void key(const std::string& k);

    void value(double v);
    void value(int v);
    void value(long long v);
    void value(bool v);
    void value(const std::string& s);
    // Перегрузка для строковых литералов: без неё "текст" неявно превращается
    // в bool (стандартное преобразование const char* -> bool), и JSON получает
    // true вместо строки.
    void value(const char* s);
    void value_null();

    // Вставить готовый JSON как есть (для вложенных блоков, собранных строкой).
    void raw_value(const std::string& raw_json);

    // Удобные пары «ключ: значение»
    void kv(const std::string& k, double v);
    void kv(const std::string& k, int v);
    void kv(const std::string& k, long long v);
    void kv(const std::string& k, bool v);
    void kv(const std::string& k, const std::string& s);
    void kv(const std::string& k, const char* s);

    const std::string& str() const { return out_; }
    void save(const std::string& path) const;

private:
    void before_item();
    void indent_to(int level);
    static std::string number_to_string(double v);
    static std::string escape(const std::string& s);

    std::string out_;
    int indent_ = 2;
    std::vector<char> stack_;          // 'o' — объект, 'a' — массив
    std::vector<bool> first_;          // ждём ли первого элемента
    bool has_key_ = false;             // следующий value идёт после key(...)
};

}  // namespace pappa

#endif  // PAPPA_JSON_WRITER_H
