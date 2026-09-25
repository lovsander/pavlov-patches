#include "json_writer.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace pappa {

void JsonWriter::indent_to(int level) {
    for (int i = 0; i < level * indent_; ++i) out_.push_back(' ');
}

// Разделитель и отступ перед очередным ЭЛЕМЕНТОМ контейнера.
// Если только что был ключ (has_key_), разделитель уже поставлен в key().
void JsonWriter::before_item() {
    if (stack_.empty() || has_key_) return;
    if (first_.back()) {
        first_.back() = false;
    } else {
        out_.push_back(',');
    }
    out_.push_back('\n');
    indent_to(static_cast<int>(stack_.size()));
}

void JsonWriter::begin_object() {
    if (!stack_.empty() && !has_key_) before_item();
    out_.push_back('{');
    stack_.push_back('o');
    first_.push_back(true);
    has_key_ = false;
}

void JsonWriter::end_object() {
    if (stack_.empty() || stack_.back() != 'o') throw std::runtime_error("end_object без begin_object");
    const bool was_first = first_.back();
    stack_.pop_back();
    first_.pop_back();
    if (!was_first) { out_.push_back('\n'); indent_to(static_cast<int>(stack_.size())); }
    out_.push_back('}');
    has_key_ = false;
}

void JsonWriter::begin_array() {
    if (!stack_.empty() && !has_key_) before_item();
    out_.push_back('[');
    stack_.push_back('a');
    first_.push_back(true);
    has_key_ = false;
}

void JsonWriter::end_array() {
    if (stack_.empty() || stack_.back() != 'a') throw std::runtime_error("end_array без begin_array");
    const bool was_first = first_.back();
    stack_.pop_back();
    first_.pop_back();
    if (!was_first) { out_.push_back('\n'); indent_to(static_cast<int>(stack_.size())); }
    out_.push_back(']');
    has_key_ = false;
}

void JsonWriter::key(const std::string& k) {
    if (stack_.empty() || stack_.back() != 'o') throw std::runtime_error("key вне объекта");
    before_item();
    out_.push_back('"');
    out_ += escape(k);
    out_ += "\": ";
    has_key_ = true;
}

std::string JsonWriter::number_to_string(double v) {
    if (!std::isfinite(v)) return "null";
    std::ostringstream os;
    os << std::setprecision(17) << v;      // полная точность, как repr(float)
    std::string s = os.str();
    if (s == "-0") s = "0";
    return s;
}

std::string JsonWriter::escape(const std::string& s) {
    std::string r;
    r.reserve(s.size());
    for (unsigned char c : s) {
        switch (c) {
            case '"': r += "\\\""; break;
            case '\\': r += "\\\\"; break;
            case '\n': r += "\\n"; break;
            case '\r': r += "\\r"; break;
            case '\t': r += "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    r += buf;
                } else {
                    r.push_back(static_cast<char>(c));   // UTF-8 как есть
                }
        }
    }
    return r;
}

void JsonWriter::value(double v) {
    before_item();
    out_ += number_to_string(v);
    has_key_ = false;
}

void JsonWriter::value(int v) {
    before_item();
    out_ += std::to_string(v);
    has_key_ = false;
}

void JsonWriter::value(long long v) {
    before_item();
    out_ += std::to_string(v);
    has_key_ = false;
}

void JsonWriter::value(bool v) {
    before_item();
    out_ += v ? "true" : "false";
    has_key_ = false;
}

void JsonWriter::value(const std::string& s) {
    before_item();
    out_.push_back('"');
    out_ += escape(s);
    out_.push_back('"');
    has_key_ = false;
}

void JsonWriter::value(const char* s) {
    value(std::string(s ? s : ""));
}

void JsonWriter::value_null() {
    before_item();
    out_ += "null";
    has_key_ = false;
}

void JsonWriter::raw_value(const std::string& raw_json) {
    before_item();
    out_ += raw_json;
    has_key_ = false;
}

void JsonWriter::kv(const std::string& k, double v) { key(k); value(v); }
void JsonWriter::kv(const std::string& k, int v) { key(k); value(v); }
void JsonWriter::kv(const std::string& k, long long v) { key(k); value(v); }
void JsonWriter::kv(const std::string& k, bool v) { key(k); value(v); }
void JsonWriter::kv(const std::string& k, const std::string& v) { key(k); value(v); }
void JsonWriter::kv(const std::string& k, const char* v) { key(k); value(v); }

void JsonWriter::save(const std::string& path) const {
    std::ofstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("Не могу записать файл: " + path);
    f << out_;
}

}  // namespace pappa
