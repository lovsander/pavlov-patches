#ifndef PAPPA_JSON_READER_H
#define PAPPA_JSON_READER_H

#include <string>
#include <utility>
#include <vector>

// Минимальный читатель JSON без внешних зависимостей — пара к json_writer.
//
// Зачем свой: утилита проверки порта (cpp/conformance.cpp) читает ТЕ ЖЕ
// конформанс-векторы, что и любой другой язык (spec/conformance/vectors/*.json),
// поэтому порту нужен парсер, а не самодельный формат. Поддерживаются объекты,
// массивы, строки (с \uXXXX), числа, true/false/null — этого достаточно для
// векторов и документов .pappa.json (чтение документов портом — на будущее).

namespace pappa {

class JsonValue {
public:
    enum class Type { Null, Bool, Number, String, Array, Object };
    using Array = std::vector<JsonValue>;
    using Object = std::vector<std::pair<std::string, JsonValue>>;

    bool is_null() const { return type_ == Type::Null; }
    bool is_bool() const { return type_ == Type::Bool; }
    bool is_number() const { return type_ == Type::Number; }
    bool is_string() const { return type_ == Type::String; }
    bool is_array() const { return type_ == Type::Array; }
    bool is_object() const { return type_ == Type::Object; }

    bool as_bool() const;
    double as_number() const;
    int as_int() const;
    const std::string& as_string() const;

    size_t size() const;                                   // длина массива/объекта
    const JsonValue& at(size_t index) const;               // элемент массива
    const JsonValue& at(const std::string& key) const;     // поле объекта
    bool has(const std::string& key) const;

    // Удобные чтения с значением по умолчанию (для необязательных полей).
    double number_or(const std::string& key, double def) const;
    int int_or(const std::string& key, int def) const;
    std::string string_or(const std::string& key, const std::string& def) const;
    double number_or(double def) const;                    // для самого значения

private:
    friend class JsonParser;
    Type type_ = Type::Null;
    bool bool_ = false;
    double number_ = 0.0;
    std::string string_;
    Array array_;
    Object object_;
};

// Разбор строки/файла. Бросает std::runtime_error с позицией при ошибке.
JsonValue parse_json(const std::string& text);
JsonValue parse_json_file(const std::string& path);

}  // namespace pappa

#endif  // PAPPA_JSON_READER_H
