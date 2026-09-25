import Foundation

/// Минимальный JSON: разбор и запись без внешних пакетов.
/// Объект — массив пар ключ/значение, порядок сохраняется.
public indirect enum JsonValue {
    case null
    case bool(Bool)
    case num(Double)
    case str(String)
    case arr([JsonValue])
    case obj([(String, JsonValue)])

    public func get(_ key: String) -> JsonValue? {
        if case .obj(let items) = self {
            for (k, v) in items where k == key { return v }
        }
        return nil
    }

    public func key(_ key: String) throws -> JsonValue {
        guard let v = get(key) else { throw Linalg.PappaError("JSON: нет ключа \(key)") }
        return v
    }

    public func asDouble() throws -> Double {
        if case .num(let v) = self { return v }
        throw Linalg.PappaError("JSON: ожидалось число")
    }

    public func asInt() throws -> Int { Int(try asDouble()) }

    public func asString() throws -> String {
        if case .str(let s) = self { return s }
        throw Linalg.PappaError("JSON: ожидалась строка")
    }

    public func asArray() throws -> [JsonValue] {
        if case .arr(let a) = self { return a }
        throw Linalg.PappaError("JSON: ожидался массив")
    }

    public func asDoubles() throws -> [Double] { try asArray().map { try $0.asDouble() } }

    public var arrayCount: Int {
        if case .arr(let a) = self { return a.count }
        return 0
    }

    public func dbl(_ key: String) throws -> Double { try self.key(key).asDouble() }

    public func dblOr(_ key: String, _ def: Double) -> Double {
        (try? self.key(key).asDouble()) ?? def
    }

    public func int(_ key: String) throws -> Int { Int(try self.dbl(key)) }

    public func intOr(_ key: String, _ def: Int) -> Int { (try? int(key)) ?? def }

    public func text(_ key: String) throws -> String { try self.key(key).asString() }

    public func boolOr(_ key: String, _ def: Bool) -> Bool {
        if let v = get(key), case .bool(let b) = v { return b }
        return def
    }

    public func doubles(_ key: String) throws -> [Double] { try self.key(key).asDoubles() }

    public func ints(_ key: String) throws -> [Int] {
        try self.key(key).asArray().map { try $0.asInt() }
    }
}

/// Число в стиле %.17g из C/C++: целые без дробной части, иначе shortest round-trip
/// (Swift печатает Double именно так; очень большие/малые — в экспоненте).
public func jsonNum(_ v: Double) -> String {
    if !v.isFinite || v == 0 { return "0" }
    if abs(v) < 1e15 && v == v.rounded() { return String(Int64(v)) }
    return "\(v)"
}

public func jsonEsc(_ s: String) -> String {
    var out = ""
    for c in s {
        switch c {
        case "\"": out += "\\\""
        case "\\": out += "\\\\"
        case "\n": out += "\\n"
        case "\r": out += "\\r"
        case "\t": out += "\\t"
        default: out.append(c)
        }
    }
    return out
}

/// Чтение/запись текстовых файлов побайтово (UTF-8, с запасным latin1 для чтения).
public func readText(_ path: String) throws -> String {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    if let s = String(data: data, encoding: .utf8) { return s }
    if let s = String(data: data, encoding: .isoLatin1) { return s }
    throw Linalg.PappaError("не читать \(path)")
}

public func writeText(_ path: String, _ text: String) throws {
    guard let data = text.data(using: .utf8) else {
        throw Linalg.PappaError("не закодировать текст для \(path)")
    }
    try data.write(to: URL(fileURLWithPath: path))
}

/// Разбор JSON-текста.
public func jsonParse(_ text: String) throws -> JsonValue {
    var p = JsonParser(Array(text))
    p.skipWs()
    return try p.value()
}

struct JsonParser {
    let s: [Character]
    var i = 0

    init(_ s: [Character]) { self.s = s }

    mutating func skipWs() {
        while i < s.count && s[i].isWhitespace { i += 1 }
    }

    mutating func value() throws -> JsonValue {
        if i >= s.count { throw Linalg.PappaError("JSON: неожиданный конец") }
        switch s[i] {
        case "{": return try object()
        case "[": return try array()
        case "\"": return .str(try string())
        case "t": try expect("true"); return .bool(true)
        case "f": try expect("false"); return .bool(false)
        case "n": try expect("null"); return .null
        default: return .num(try number())
        }
    }

    mutating func expect(_ lit: String) throws {
        for c in lit {
            if i >= s.count || s[i] != c {
                throw Linalg.PappaError("JSON: ожидался литерал \(lit)")
            }
            i += 1
        }
    }

    mutating func object() throws -> JsonValue {
        var items: [(String, JsonValue)] = []
        i += 1                                    // {
        skipWs()
        if s[i] == "}" { i += 1; return .obj(items) }
        while true {
            skipWs()
            let k = try string()
            skipWs()
            if s[i] != ":" { throw Linalg.PappaError("JSON: ожидалось ':'") }
            i += 1
            skipWs()
            items.append((k, try value()))
            skipWs()
            let c = s[i]
            i += 1
            if c == "}" { return .obj(items) }
            if c != "," { throw Linalg.PappaError("JSON: ожидалась ',' или '}'") }
        }
    }

    mutating func array() throws -> JsonValue {
        var items: [JsonValue] = []
        i += 1                                    // [
        skipWs()
        if s[i] == "]" { i += 1; return .arr(items) }
        while true {
            skipWs()
            items.append(try value())
            skipWs()
            let c = s[i]
            i += 1
            if c == "]" { return .arr(items) }
            if c != "," { throw Linalg.PappaError("JSON: ожидалась ',' или ']'") }
        }
    }

    mutating func string() throws -> String {
        if s[i] != "\"" { throw Linalg.PappaError("JSON: ожидалась строка") }
        i += 1
        var out = ""
        while true {
            let c = s[i]
            i += 1
            if c == "\"" { return out }
            if c != "\\" { out.append(c); continue }
            let e = s[i]
            i += 1
            switch e {
            case "n": out.append("\n")
            case "t": out.append("\t")
            case "r": out.append("\r")
            case "b": out.append("\u{8}")
            case "f": out.append("\u{c}")
            case "u":
                let hex = String(s[i..<(i + 4)])
                i += 4
                if let code = UInt32(hex, radix: 16), let u = UnicodeScalar(code) {
                    out.append(Character(u))
                }
            default: out.append(e)
            }
        }
    }

    mutating func number() throws -> Double {
        let start = i
        while i < s.count && "+-0123456789.eE".contains(s[i]) { i += 1 }
        let txt = String(s[start..<i])
        guard let v = Double(txt) else {
            throw Linalg.PappaError("JSON: плохое число \(txt)")
        }
        return v
    }
}
