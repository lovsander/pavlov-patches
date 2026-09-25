package pappa

/**
 * Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
 * по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
 * Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py) и порты C/C++/Go/JS/Java.
 */
object Cleaner {

    data class Options(
        val baselineDeg: Double = 1.0,
        val iqrK: Double = 3.0,
        val maxRemovedFrac: Double = 0.5,
        val minPoints: Int = 20,
    )

    data class Result(val mask: BooleanArray, val nOutliers: Int, val window: Int)

    fun cleanIqr(angles: DoubleArray, radii: DoubleArray, o: Options = Options()): Result {
        val n = radii.size
        val mask = BooleanArray(n)
        if (n < o.minPoints) return Result(mask, 0, 0)

        val w = Signal.windowPoints(angles, o.baselineDeg)
        val base = Signal.medianFilterWrap(radii, w)
        val res = DoubleArray(n) { radii[it] - base[it] }

        val center = Signal.median(res)
        val spread = Signal.iqr(res)
        val denom = if (spread > 1e-12) spread else 1.0   // защита референса (spec/conformance/README)

        val sev = DoubleArray(n)
        var flagged = 0
        for (i in 0 until n) {
            sev[i] = Math.abs(res[i] - center) / denom
            mask[i] = sev[i] > o.iqrK
            if (mask[i]) flagged++
        }

        // Предохранитель: не выбрасываем больше maxRemovedFrac точек.
        val cap = Math.floor(o.maxRemovedFrac * n).toInt()
        if (cap > 0 && cap < n && flagged > cap) {
            val kept = sev.filterIndexed { i, _ -> mask[i] }.sorted()
            val level = kept[kept.size - cap]
            flagged = 0
            for (i in 0 until n) {
                mask[i] = mask[i] && sev[i] >= level
                if (mask[i]) flagged++
            }
        }
        return Result(mask, flagged, w)
    }
}
