//! Минимальный JSON: разбор и запись без внешних крейтов.
//! Числа — f64, объекты — Vec<(String, Value)> (порядок ключей сохраняется).

#[derive(Debug, Clone)]
pub enum Value {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<Value>),
    Obj(Vec<(String, Value)>),
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Obj(items) => items.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn obj(&self) -> &[(String, Value)] {
        match self {
            Value::Obj(items) => items,
            _ => panic!("JSON: ожидался объект"),
        }
    }

    pub fn arr(&self) -> &[Value] {
        match self {
            Value::Arr(items) => items,
            _ => panic!("JSON: ожидался массив"),
        }
    }

    pub fn as_f64(&self) -> f64 {
        match self {
            Value::Num(v) => *v,
            _ => panic!("JSON: ожидалось число"),
        }
    }

    pub fn as_usize(&self) -> usize {
        self.as_f64() as usize
    }

    pub fn as_str(&self) -> &str {
        match self {
            Value::Str(s) => s,
            _ => panic!("JSON: ожидалась строка"),
        }
    }

    pub fn f64_or(&self, default: f64) -> f64 {
        match self {
            Value::Num(v) => *v,
            _ => default,
        }
    }

    pub fn str_or(&self, default: &str) -> String {
        match self {
            Value::Str(s) => s.clone(),
            _ => default.to_string(),
        }
    }

    pub fn bool_or(&self, default: bool) -> bool {
        match self {
            Value::Bool(b) => *b,
            _ => default,
        }
    }

    /// Доступ к ключу объекта (паника, если ключа нет).
    pub fn key(&self, key: &str) -> &Value {
        self.get(key)
            .unwrap_or_else(|| panic!("JSON: нет ключа {key}"))
    }

    pub fn dbl(&self, key: &str) -> f64 {
        self.key(key).as_f64()
    }

    pub fn dbl_or(&self, key: &str, default: f64) -> f64 {
        self.get(key).map(|v| v.f64_or(default)).unwrap_or(default)
    }

    pub fn int(&self, key: &str) -> usize {
        self.key(key).as_usize()
    }

    pub fn text(&self, key: &str) -> String {
        self.key(key).as_str().to_string()
    }

    pub fn doubles(&self, key: &str) -> Vec<f64> {
        self.key(key).arr().iter().map(|v| v.as_f64()).collect()
    }

    pub fn ints(&self, key: &str) -> Vec<usize> {
        self.key(key).arr().iter().map(|v| v.as_usize()).collect()
    }
}

pub fn parse(text: &str) -> Value {
    let chars: Vec<char> = text.chars().collect();
    let mut p = Parser { s: &chars, i: 0 };
    p.ws();
    p.value()
}

struct Parser<'a> {
    s: &'a [char],
    i: usize,
}

impl Parser<'_> {
    fn ws(&mut self) {
        while self.i < self.s.len() && self.s[self.i].is_whitespace() {
            self.i += 1;
        }
    }

    fn value(&mut self) -> Value {
        match self.s[self.i] {
            '{' => self.object(),
            '[' => self.array(),
            '"' => Value::Str(self.string()),
            't' => {
                self.expect("true");
                Value::Bool(true)
            }
            'f' => {
                self.expect("false");
                Value::Bool(false)
            }
            'n' => {
                self.expect("null");
                Value::Null
            }
            _ => self.number(),
        }
    }

    fn expect(&mut self, lit: &str) {
        for c in lit.chars() {
            assert_eq!(self.s[self.i], c, "JSON: ожидался литерал {lit}");
            self.i += 1;
        }
    }

    fn object(&mut self) -> Value {
        let mut items = Vec::new();
        self.i += 1; // {
        self.ws();
        if self.s[self.i] == '}' {
            self.i += 1;
            return Value::Obj(items);
        }
        loop {
            self.ws();
            let k = self.string();
            self.ws();
            assert_eq!(self.s[self.i], ':', "JSON: ожидалось ':'");
            self.i += 1;
            self.ws();
            items.push((k, self.value()));
            self.ws();
            let c = self.s[self.i];
            self.i += 1;
            match c {
                '}' => return Value::Obj(items),
                ',' => {}
                _ => panic!("JSON: ожидалась ',' или '}}'"),
            }
        }
    }

    fn array(&mut self) -> Value {
        let mut items = Vec::new();
        self.i += 1; // [
        self.ws();
        if self.s[self.i] == ']' {
            self.i += 1;
            return Value::Arr(items);
        }
        loop {
            self.ws();
            items.push(self.value());
            self.ws();
            let c = self.s[self.i];
            self.i += 1;
            match c {
                ']' => return Value::Arr(items),
                ',' => {}
                _ => panic!("JSON: ожидалась ',' или ']'"),
            }
        }
    }

    fn string(&mut self) -> String {
        assert_eq!(self.s[self.i], '"', "JSON: ожидалась строка");
        self.i += 1;
        let mut out = String::new();
        loop {
            let c = self.s[self.i];
            self.i += 1;
            if c == '"' {
                return out;
            }
            if c != '\\' {
                out.push(c);
                continue;
            }
            let e = self.s[self.i];
            self.i += 1;
            match e {
                'n' => out.push('\n'),
                't' => out.push('\t'),
                'r' => out.push('\r'),
                'b' => out.push('\u{8}'),
                'f' => out.push('\u{c}'),
                'u' => {
                    let hex: String = self.s[self.i..self.i + 4].iter().collect();
                    self.i += 4;
                    let code = u32::from_str_radix(&hex, 16).expect("JSON: плохой \\u");
                    out.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                }
                other => out.push(other),
            }
        }
    }

    fn number(&mut self) -> Value {
        let start = self.i;
        while self.i < self.s.len() && "+-0123456789.eE".contains(self.s[self.i]) {
            self.i += 1;
        }
        let text: String = self.s[start..self.i].iter().collect();
        Value::Num(
            text.parse::<f64>()
                .unwrap_or_else(|_| panic!("JSON: плохое число {text}")),
        )
    }
}

/// Число в стиле `%.17g` из C/C++: целые без дробной части, иначе shortest round-trip;
/// очень большие/малые — в экспоненциальной форме (валидный JSON, Python парсит).
pub fn num(v: f64) -> String {
    if !v.is_finite() || v == 0.0 {
        return "0".to_string();
    }
    let a = v.abs();
    if (1e-4..1e16).contains(&a) {
        if v == v.round() {
            return format!("{}", v as i64);
        }
        return format!("{v}");
    }
    format!("{v:e}")
}

/// Экранирование строки для JSON.
pub fn esc(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            other => out.push(other),
        }
    }
    out
}
