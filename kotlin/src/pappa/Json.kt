package pappa

/**
 * Минимальный JSON: разбор и запись без внешних зависимостей.
 * Разбор: объекты -> LinkedHashMap, массивы -> List, числа -> Double,
 * строки -> String, литералы -> Boolean/null.
 */
object Json {

    fun parse(text: String): Any? {
        val p = Parser(text)
        p.ws()
        return p.value()
    }

    fun parseObject(text: String): Map<String, Any?> = obj(parse(text))

    // ---------- доступ к разобранному ----------

    @Suppress("UNCHECKED_CAST")
    fun obj(o: Any?): Map<String, Any?> = o as Map<String, Any?>

    @Suppress("UNCHECKED_CAST")
    fun arr(o: Any?): List<Any?> = o as List<Any?>

    fun dbl(m: Map<String, Any?>, k: String): Double = m[k] as Double

    fun dbl(m: Map<String, Any?>, k: String, def: Double): Double = (m[k] as? Double) ?: def

    fun int(m: Map<String, Any?>, k: String): Int = (m[k] as Double).toInt()

    fun int(m: Map<String, Any?>, k: String, def: Int): Int = (m[k] as? Double)?.toInt() ?: def

    fun str(m: Map<String, Any?>, k: String): String = m[k] as String

    fun bool(m: Map<String, Any?>, k: String, def: Boolean): Boolean = (m[k] as? Boolean) ?: def

    fun doubles(m: Map<String, Any?>, k: String): DoubleArray =
        arr(m[k]).map { it as Double }.toDoubleArray()

    fun ints(m: Map<String, Any?>, k: String): IntArray =
        arr(m[k]).map { (it as Double).toInt() }.toIntArray()

    /** Число в стиле %.17g из C/C++: целые без дробной части, иначе shortest round-trip. */
    fun num(v: Double): String {
        if (!v.isFinite()) return "0"
        if (v == Math.rint(v) && Math.abs(v) < 1e15) return (v.toLong()).toString()
        return v.toString()
    }

    fun esc(s: String): String = buildString {
        for (c in s) when (c) {
            '"' -> append("\\\"")
            '\\' -> append("\\\\")
            '\n' -> append("\\n")
            '\r' -> append("\\r")
            '\t' -> append("\\t")
            else -> append(c)
        }
    }

    private class Parser(private val s: String) {
        private var i = 0

        fun ws() {
            while (i < s.length && s[i].isWhitespace()) i++
        }

        fun value(): Any? {
            return when (s[i]) {
                '{' -> objectBody()
                '[' -> arrayBody()
                '"' -> string()
                't' -> { expect("true"); true }
                'f' -> { expect("false"); false }
                'n' -> { expect("null"); null }
                else -> number()
            }
        }

        private fun expect(lit: String) {
            require(s.startsWith(lit, i)) { "JSON: ожидался литерал $lit" }
            i += lit.length
        }

        private fun objectBody(): Map<String, Any?> {
            val m = LinkedHashMap<String, Any?>()
            i++                              // {
            ws()
            if (s[i] == '}') { i++; return m }
            while (true) {
                ws()
                val k = string()
                ws()
                require(s[i] == ':') { "JSON: ожидалось ':'" }
                i++
                ws()
                m[k] = value()
                ws()
                when (val c = s[i++]) {
                    '}' -> return m
                    ',' -> {}
                    else -> throw IllegalArgumentException("JSON: ожидалась ',' или '}'")
                }
            }
        }

        private fun arrayBody(): List<Any?> {
            val a = ArrayList<Any?>()
            i++                              // [
            ws()
            if (s[i] == ']') { i++; return a }
            while (true) {
                ws()
                a.add(value())
                ws()
                when (s[i++]) {
                    ']' -> return a
                    ',' -> {}
                    else -> throw IllegalArgumentException("JSON: ожидалась ',' или ']'")
                }
            }
        }

        private fun string(): String {
            require(s[i] == '"') { "JSON: ожидалась строка" }
            i++
            val b = StringBuilder()
            while (true) {
                val c = s[i++]
                if (c == '"') return b.toString()
                if (c != '\\') { b.append(c); continue }
                when (val e = s[i++]) {
                    'n' -> b.append('\n')
                    't' -> b.append('\t')
                    'r' -> b.append('\r')
                    'b' -> b.append('\b')
                    'f' -> b.append('\u000C')
                    'u' -> {
                        b.append(s.substring(i, i + 4).toInt(16).toChar())
                        i += 4
                    }
                    else -> b.append(e)
                }
            }
        }

        private fun number(): Double {
            val start = i
            while (i < s.length && "+-0123456789.eE".indexOf(s[i]) >= 0) i++
            return s.substring(start, i).toDoubleOrNull()
                ?: throw IllegalArgumentException("JSON: плохое число ${s.substring(start, i)}")
        }
    }
}
