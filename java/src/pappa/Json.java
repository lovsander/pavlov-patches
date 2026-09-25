package pappa;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Минимальный JSON: разбор и запись без внешних зависимостей (в JDK JSON нет).
 * Разбор: объекты -> LinkedHashMap, массивы -> List, числа -> Double,
 * строки -> String, литералы -> Boolean/null.
 */
public final class Json {

    private final String s;
    private int i;

    private Json(String s) { this.s = s; }

    public static Object parse(String text) {
        Json j = new Json(text);
        j.ws();
        Object v = j.value();
        j.ws();
        return v;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> parseObject(String text) {
        return (Map<String, Object>) parse(text);
    }

    private void ws() {
        while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
    }

    private Object value() {
        char c = s.charAt(i);
        switch (c) {
            case '{': return object();
            case '[': return array();
            case '"': return string();
            case 't': expect("true"); return Boolean.TRUE;
            case 'f': expect("false"); return Boolean.FALSE;
            case 'n': expect("null"); return null;
            default: return number();
        }
    }

    private void expect(String lit) {
        if (!s.startsWith(lit, i)) throw err("ожидался литерал " + lit);
        i += lit.length();
    }

    private Map<String, Object> object() {
        Map<String, Object> m = new LinkedHashMap<>();
        i++;                       // {
        ws();
        if (s.charAt(i) == '}') { i++; return m; }
        while (true) {
            ws();
            String k = string();
            ws();
            if (s.charAt(i) != ':') throw err("ожидалось ':'");
            i++;
            ws();
            m.put(k, value());
            ws();
            char c = s.charAt(i++);
            if (c == '}') return m;
            if (c != ',') throw err("ожидалась ',' или '}'");
        }
    }

    private List<Object> array() {
        List<Object> a = new ArrayList<>();
        i++;                       // [
        ws();
        if (s.charAt(i) == ']') { i++; return a; }
        while (true) {
            ws();
            a.add(value());
            ws();
            char c = s.charAt(i++);
            if (c == ']') return a;
            if (c != ',') throw err("ожидалась ',' или ']'");
        }
    }

    private String string() {
        if (s.charAt(i) != '"') throw err("ожидалась строка");
        i++;
        StringBuilder b = new StringBuilder();
        while (true) {
            char c = s.charAt(i++);
            if (c == '"') return b.toString();
            if (c != '\\') { b.append(c); continue; }
            char e = s.charAt(i++);
            switch (e) {
                case 'n': b.append('\n'); break;
                case 't': b.append('\t'); break;
                case 'r': b.append('\r'); break;
                case 'b': b.append('\b'); break;
                case 'f': b.append('\f'); break;
                case 'u':
                    b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                    i += 4;
                    break;
                default: b.append(e);      // " \ /
            }
        }
    }

    private Double number() {
        int start = i;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        try {
            return Double.valueOf(s.substring(start, i));
        } catch (NumberFormatException ex) {
            throw err("плохое число: " + s.substring(start, i));
        }
    }

    private IllegalArgumentException err(String msg) {
        return new IllegalArgumentException("JSON (смещение " + i + "): " + msg);
    }

    // ---------- доступ к разобранному ----------

    @SuppressWarnings("unchecked")
    public static Map<String, Object> obj(Object o) { return (Map<String, Object>) o; }

    @SuppressWarnings("unchecked")
    public static List<Object> arr(Object o) { return (List<Object>) o; }

    public static double dbl(Map<String, Object> m, String k) { return (Double) m.get(k); }

    public static double dbl(Map<String, Object> m, String k, double def) {
        Object v = m.get(k);
        return v == null ? def : (Double) v;
    }

    public static int i(Map<String, Object> m, String k) { return ((Double) m.get(k)).intValue(); }

    public static int i(Map<String, Object> m, String k, int def) {
        Object v = m.get(k);
        return v == null ? def : ((Double) v).intValue();
    }

    public static String str(Map<String, Object> m, String k) { return (String) m.get(k); }

    public static boolean bool(Map<String, Object> m, String k, boolean def) {
        Object v = m.get(k);
        return v == null ? def : (Boolean) v;
    }

    public static double[] doubles(Map<String, Object> m, String k) {
        List<Object> a = arr(m.get(k));
        double[] out = new double[a.size()];
        for (int j = 0; j < out.length; j++) out[j] = (Double) a.get(j);
        return out;
    }

    public static int[] ints(Map<String, Object> m, String k) {
        List<Object> a = arr(m.get(k));
        int[] out = new int[a.size()];
        for (int j = 0; j < out.length; j++) out[j] = ((Double) a.get(j)).intValue();
        return out;
    }

    /** Число в стиле %.17g из C/C++: целые без дробной части, иначе shortest round-trip. */
    public static String num(double v) {
        if (!Double.isFinite(v)) return "0";
        if (v == Math.rint(v) && Math.abs(v) < 1e15) return String.valueOf((long) v);
        return Double.toString(v);
    }
}
