#include "json_reader.h"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace pappa {

namespace {
[[noreturn]] void fail(const std::string& message, size_t pos) {
    throw std::runtime_error("JSON: " + message + " (позиция " + std::to_string(pos) + ")");
}

void append_utf8(std::string& out, unsigned int cp) {
    if (cp < 0x80) {
        out.push_back(static_cast<char>(cp));
    } else if (cp < 0x800) {
        out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
}
}  // namespace

class JsonParser {
public:
    explicit JsonParser(const std::string& text) : t_(text) {}

    JsonValue parse() {
        skip_ws();
        JsonValue v = parse_value();
        skip_ws();
        if (pos_ != t_.size()) fail("лишние данные после значения", pos_);
        return v;
    }

private:
    const std::string& t_;
    size_t pos_ = 0;

    void skip_ws() {
        while (pos_ < t_.size() &&
               (t_[pos_] == ' ' || t_[pos_] == '\t' || t_[pos_] == '\n' ||
                t_[pos_] == '\r')) {
            ++pos_;
        }
    }

    char peek() {
        if (pos_ >= t_.size()) fail("неожиданный конец документа", pos_);
        return t_[pos_];
    }

    void expect(char c) {
        if (peek() != c) fail(std::string("ожидалось '") + c + "'", pos_);
        ++pos_;
    }

    bool literal(const char* word) {
        const size_t n = std::strlen(word);
        if (t_.compare(pos_, n, word) == 0) { pos_ += n; return true; }
        return false;
    }

    JsonValue parse_value() {
        const char c = peek();
        if (c == '{') return parse_object();
        if (c == '[') return parse_array();
        if (c == '"') {
            JsonValue v;
            v.type_ = JsonValue::Type::String;
            v.string_ = parse_string();
            return v;
        }
        if (t_.compare(pos_, 4, "true") == 0) {
            pos_ += 4;
            JsonValue v;
            v.type_ = JsonValue::Type::Bool;
            v.bool_ = true;
            return v;
        }
        if (t_.compare(pos_, 5, "false") == 0) {
            pos_ += 5;
            JsonValue v;
            v.type_ = JsonValue::Type::Bool;
            v.bool_ = false;
            return v;
        }
        if (t_.compare(pos_, 4, "null") == 0) {
            pos_ += 4;
            return JsonValue{};
        }
        return parse_number();
    }

    JsonValue parse_object() {
        JsonValue v;
        v.type_ = JsonValue::Type::Object;
        expect('{');
        skip_ws();
        if (peek() == '}') { ++pos_; return v; }
        while (true) {
            skip_ws();
            const std::string key = parse_string();
            skip_ws();
            expect(':');
            skip_ws();
            v.object_.emplace_back(key, parse_value());
            skip_ws();
            const char c = peek();
            if (c == ',') { ++pos_; continue; }
            if (c == '}') { ++pos_; break; }
            fail("ожидалось ',' или '}'", pos_);
        }
        return v;
    }

    JsonValue parse_array() {
        JsonValue v;
        v.type_ = JsonValue::Type::Array;
        expect('[');
        skip_ws();
        if (peek() == ']') { ++pos_; return v; }
        while (true) {
            skip_ws();
            v.array_.push_back(parse_value());
            skip_ws();
            const char c = peek();
            if (c == ',') { ++pos_; continue; }
            if (c == ']') { ++pos_; break; }
            fail("ожидалось ',' или ']'", pos_);
        }
        return v;
    }

    std::string parse_string() {
        expect('"');
        std::string out;
        while (true) {
            if (pos_ >= t_.size()) fail("незакрытая строка", pos_);
            const char c = t_[pos_++];
            if (c == '"') break;
            if (c != '\\') { out.push_back(c); continue; }
            if (pos_ >= t_.size()) fail("обрыв escape-последовательности", pos_);
            const char e = t_[pos_++];
            switch (e) {
                case '"': out.push_back('"'); break;
                case '\\': out.push_back('\\'); break;
                case '/': out.push_back('/'); break;
                case 'b': out.push_back('\b'); break;
                case 'f': out.push_back('\f'); break;
                case 'n': out.push_back('\n'); break;
                case 'r': out.push_back('\r'); break;
                case 't': out.push_back('\t'); break;
                case 'u': {
                    unsigned int cp = 0;
                    for (int k = 0; k < 4; ++k) {
                        if (pos_ >= t_.size()) fail("обрыв \\u", pos_);
                        const char h = t_[pos_++];
                        cp <<= 4;
                        if (h >= '0' && h <= '9') cp |= static_cast<unsigned>(h - '0');
                        else if (h >= 'a' && h <= 'f') cp |= static_cast<unsigned>(h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F') cp |= static_cast<unsigned>(h - 'A' + 10);
                        else fail("некорректный \\uXXXX", pos_);
                    }
                    append_utf8(out, cp);
                    break;
                }
                default: fail("неизвестная escape-последовательность", pos_);
            }
        }
        return out;
    }

    JsonValue parse_number() {
        const size_t start = pos_;
        if (peek() == '-') ++pos_;
        while (pos_ < t_.size() &&
               (std::isdigit(static_cast<unsigned char>(t_[pos_])) ||
                t_[pos_] == '.' || t_[pos_] == 'e' || t_[pos_] == 'E' ||
                t_[pos_] == '+' || t_[pos_] == '-')) {
            ++pos_;
        }
        if (start == pos_) fail("ожидалось число", pos_);
        JsonValue v;
        v.type_ = JsonValue::Type::Number;
        v.number_ = std::strtod(t_.substr(start, pos_ - start).c_str(), nullptr);
        return v;
    }
};

bool JsonValue::as_bool() const {
    if (type_ != Type::Bool) throw std::runtime_error("JSON: значение не bool");
    return bool_;
}

double JsonValue::as_number() const {
    if (type_ != Type::Number) throw std::runtime_error("JSON: значение не число");
    return number_;
}

int JsonValue::as_int() const { return static_cast<int>(std::llround(as_number())); }

const std::string& JsonValue::as_string() const {
    if (type_ != Type::String) throw std::runtime_error("JSON: значение не строка");
    return string_;
}

size_t JsonValue::size() const {
    if (type_ == Type::Array) return array_.size();
    if (type_ == Type::Object) return object_.size();
    throw std::runtime_error("JSON: у значения нет длины");
}

const JsonValue& JsonValue::at(size_t index) const {
    if (type_ != Type::Array) throw std::runtime_error("JSON: значение не массив");
    if (index >= array_.size()) throw std::runtime_error("JSON: индекс вне массива");
    return array_[index];
}

const JsonValue& JsonValue::at(const std::string& key) const {
    if (type_ != Type::Object) throw std::runtime_error("JSON: значение не объект");
    for (const auto& kv : object_) {
        if (kv.first == key) return kv.second;
    }
    throw std::runtime_error("JSON: нет поля \"" + key + "\"");
}

bool JsonValue::has(const std::string& key) const {
    if (type_ != Type::Object) return false;
    for (const auto& kv : object_) {
        if (kv.first == key) return true;
    }
    return false;
}

double JsonValue::number_or(const std::string& key, double def) const {
    return (has(key) && at(key).is_number()) ? at(key).as_number() : def;
}

int JsonValue::int_or(const std::string& key, int def) const {
    return (has(key) && at(key).is_number()) ? at(key).as_int() : def;
}

std::string JsonValue::string_or(const std::string& key, const std::string& def) const {
    return (has(key) && at(key).is_string()) ? at(key).as_string() : def;
}

double JsonValue::number_or(double def) const { return is_number() ? number_ : def; }

JsonValue parse_json(const std::string& text) {
    JsonParser parser(text);
    return parser.parse();
}

JsonValue parse_json_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("Не могу открыть JSON: " + path);
    std::ostringstream ss;
    ss << f.rdbuf();
    return parse_json(ss.str());
}

}  // namespace pappa

