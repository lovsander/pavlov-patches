package pappa

/**
 * Сигнальные утилиты — поведение как у numpy и как в портах C/C++/Go/JS/Java:
 * медиана (чётное n — среднее двух центральных), перцентиль с линейной
 * интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
 */
object Signal {

    fun median(x: DoubleArray): Double {
        val n = x.size
        if (n == 0) return 0.0
        val v = x.sortedArray()
        return if (n % 2 == 1) v[n / 2] else 0.5 * (v[n / 2 - 1] + v[n / 2])
    }

    fun percentileLinear(x: DoubleArray, q: Double): Double {
        val n = x.size
        if (n == 0) return 0.0
        val v = x.sortedArray()
        val pos = (q / 100.0) * (n - 1)
        val lo = Math.floor(pos).toInt()
        val frac = pos - lo
        val hi = Math.min(lo + 1, n - 1)
        return v[lo] + frac * (v[hi] - v[lo])
    }

    fun iqr(x: DoubleArray): Double =
        if (x.isEmpty()) 0.0 else percentileLinear(x, 75.0) - percentileLinear(x, 25.0)

    fun mad(x: DoubleArray): Double {
        if (x.isEmpty()) return 0.0
        val m = median(x)
        return median(DoubleArray(x.size) { Math.abs(x[it] - m) })
    }

    fun robustSigma(x: DoubleArray): Double = 1.4826 * mad(x)

    /** Медианный шаг сетки по углам (медиана положительных разностей, иначе 1). */
    fun angularStep(angles: DoubleArray): Double {
        if (angles.size < 2) return 1.0
        val d = ArrayList<Double>(angles.size - 1)
        for (i in 1 until angles.size) {
            val s = angles[i] - angles[i - 1]
            if (s > 0) d.add(s)
        }
        return if (d.isEmpty()) 1.0 else median(d.toDoubleArray())
    }

    /**
     * Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная.
     * Math.rint, а не Math.round: Python round(2.5) == 2 (как math.RoundToEven в Go).
     */
    fun windowPoints(angles: DoubleArray, spanDeg: Double): Int {
        val n = angles.size
        if (n < 3) return Math.max(1, n)
        var w = Math.rint(spanDeg / angularStep(angles)).toLong()
        if (w % 2L == 0L) w += 1
        if (w < 3) w = 3
        if (w > n) w = (if (n % 2 == 1) n else n - 1).toLong()
        return Math.max(3, w.toInt())
    }

    private fun oddWindow(window: Int, n: Int): Int {
        var w = if (window % 2 == 0) window + 1 else window
        if (w < 3) w = 3
        if (w > n) w = if (n % 2 == 1) n else n - 1
        return w
    }

    fun wrapIndex(i: Int, n: Int): Int = ((i % n) + n) % n

    /** Медианный фильтр по кольцу (окно в точках). */
    fun medianFilterWrap(x: DoubleArray, window: Int): DoubleArray {
        val n = x.size
        val w = oddWindow(window, n)
        val out = DoubleArray(n)
        if (w < 3 || n < 3) {
            out.fill(median(x))
            return out
        }
        val h = (w - 1) / 2
        val win = DoubleArray(w)
        for (i in 0 until n) {
            for (k in 0 until w) win[k] = x[wrapIndex(i - h + k, n)]
            out[i] = median(win)
        }
        return out
    }

    /** Скользящее среднее по кольцу (окно в точках). */
    fun smoothWrap(x: DoubleArray, window: Int): DoubleArray {
        val n = x.size
        val w = oddWindow(window, n)
        if (w < 3 || n < 3) return x.copyOf()
        val h = (w - 1) / 2
        val out = DoubleArray(n)
        for (i in 0 until n) {
            var s = 0.0
            for (k in -h..h) s += x[wrapIndex(i + k, n)]
            out[i] = s / w
        }
        return out
    }

    fun circDist(a: Double, b: Double): Double {
        val d = ((a - b + 180) % 360 + 360) % 360
        return Math.abs(d - 180)
    }

    fun circLocal(a: Double, b: Double): Double {
        val d = ((a - b + 180) % 360 + 360) % 360
        return d - 180
    }

    fun smoothstep(t: Double): Double = when {
        t < 0 -> 0.0
        t > 1 -> 1.0
        else -> t * t * (3 - 2 * t)
    }
}
