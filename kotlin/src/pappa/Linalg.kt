package pappa

/**
 * Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
 * np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени.
 */
object Linalg {

    /** Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится. */
    fun lstsqQR(aIn: Array<DoubleArray>, bIn: DoubleArray): DoubleArray {
        val m = aIn.size
        require(m > 0) { "lstsqQR: пустая матрица" }
        val n = aIn[0].size
        require(bIn.size == m) { "lstsqQR: длины A и b не совпадают" }
        require(m >= n) { "lstsqQR: нужно m >= n" }

        val a = Array(m) { aIn[it].copyOf() }
        val b = bIn.copyOf()

        for (k in 0 until n) {
            var norm = 0.0
            for (i in k until m) norm += a[i][k] * a[i][k]
            norm = Math.sqrt(norm)
            if (norm < 1e-300) continue

            val alpha = if (a[k][k] > 0) -norm else norm
            val v = DoubleArray(m)
            for (i in k until m) v[i] = a[i][k]
            v[k] -= alpha
            var vnorm2 = 0.0
            for (i in k until m) vnorm2 += v[i] * v[i]
            if (vnorm2 < 1e-300) continue

            for (j in k until n) {
                var s = 0.0
                for (i in k until m) s += v[i] * a[i][j]
                val c = 2 * s / vnorm2
                for (i in k until m) a[i][j] -= c * v[i]
            }
            var sb = 0.0
            for (i in k until m) sb += v[i] * b[i]
            val cb = 2 * sb / vnorm2
            for (i in k until m) b[i] -= cb * v[i]
        }

        val x = DoubleArray(n)
        for (i in n - 1 downTo 0) {
            var s = b[i]
            for (j in i + 1 until n) s -= a[i][j] * x[j]
            val d = a[i][i]
            check(Math.abs(d) >= 1e-300) { "lstsqQR: вырожденная система" }
            x[i] = s / d
        }
        return x
    }

    /** Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval). */
    fun polyval(coefs: DoubleArray, x: Double): Double {
        var r = 0.0
        for (c in coefs) r = r * x + c
        return r
    }

    fun polyfit(xs: DoubleArray, ys: DoubleArray, deg: Int): DoubleArray {
        val m = xs.size
        val n = deg + 1
        val a = Array(m) { DoubleArray(n) }
        for (i in 0 until m) {
            var p = 1.0
            for (j in 0 until n) {
                a[i][n - 1 - j] = p
                p *= xs[i]
            }
        }
        return lstsqQR(a, ys)
    }

    /** T_0(x)..T_degMax(x) — базис Чебышёва (x ∈ [-1, 1]). */
    fun chebRow(x: Double, degMax: Int): DoubleArray {
        val t = DoubleArray(degMax + 1)
        t[0] = 1.0
        if (degMax >= 1) t[1] = x
        for (k in 2..degMax) t[k] = 2 * x * t[k - 1] - t[k - 2]
        return t
    }

    /** Σ c_k·T_k(x) по схеме Кленшоу (устойчиво). */
    fun chebSum(c: DoubleArray, deg: Int, x: Double): Double {
        var b1 = 0.0
        var b2 = 0.0
        for (k in deg downTo 1) {
            val b0 = 2 * x * b1 - b2 + c[k]
            b2 = b1
            b1 = b0
        }
        return x * b1 - b2 + c[0]
    }
}
