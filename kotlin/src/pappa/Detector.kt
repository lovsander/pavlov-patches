package pappa

/**
 * Детектор ям (трещин) — повторение python/pappa/analysis/zones.py и портов:
 *   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
 *   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
 *   зоны = участки, где индикатор > k, длиной не короче minZoneDeg.
 */
object Detector {

    data class Options(
        val windowDeg: Double = 1.0,
        val wideDeg: Double = 10.0,
        val smoothDeg: Double = 2.0,
        val k: Double = 5.5,
        val minZoneDeg: Double = 2.0,
    )

    fun bandIndicator(angles: DoubleArray, radii: DoubleArray, o: Options = Options()): DoubleArray {
        val n = radii.size
        val wNarrow = Signal.windowPoints(angles, o.windowDeg)
        val wWide = Signal.windowPoints(angles, o.wideDeg)
        val wSmooth = Signal.windowPoints(angles, o.smoothDeg)

        val narrow = Signal.medianFilterWrap(radii, wNarrow)
        val wide = Signal.medianFilterWrap(radii, wWide)
        val band = DoubleArray(n) { Math.abs(narrow[it] - wide[it]) }

        val out = Signal.smoothWrap(band, wSmooth)
        val s = Signal.robustSigma(out)
        if (s > 1e-12) {
            for (i in 0 until n) out[i] /= s
        } else {
            out.fill(0.0)
        }
        return out
    }

    /** Непрерывные зоны по маске: массив [начало, конец] в градусах. */
    fun maskToZones(angles: DoubleArray, mask: BooleanArray, o: Options = Options()): List<DoubleArray> {
        val n = angles.size
        if (mask.none { it }) return emptyList()

        val diffs = DoubleArray(Math.max(0, n - 1)) { angles[it + 1] - angles[it] }
        val step = if (diffs.isNotEmpty()) Signal.median(diffs) else 1.0

        var zones = ArrayList<DoubleArray>()
        var i = 0
        while (i < n) {
            if (!mask[i]) { i++; continue }
            var j = i
            while (j + 1 < n && mask[j + 1]) j++
            zones.add(doubleArrayOf(angles[i] - step / 2, angles[j] + step / 2))
            i = j + 1
        }

        // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
        if (zones.size > 1 && mask[0] && mask[n - 1]) {
            val first = zones[0]
            val last = zones[zones.size - 1]
            val merged = ArrayList<DoubleArray>()
            merged.add(doubleArrayOf(last[0] - 360, first[1]))
            merged.addAll(zones.subList(1, zones.size - 1))
            zones = merged
        }
        return zones.filter { it[1] - it[0] >= o.minZoneDeg }
    }

    fun zones(angles: DoubleArray, values: DoubleArray, o: Options = Options()): List<DoubleArray> =
        maskToZones(angles, BooleanArray(values.size) { values[it] > o.k }, o)

    /** Центры ям (°) — середины найденных зон. */
    fun pits(angles: DoubleArray, radii: DoubleArray, o: Options = Options()): DoubleArray {
        val band = bandIndicator(angles, radii, o)
        val zs = zones(angles, band, o)
        return DoubleArray(zs.size) { 0.5 * (zs[it][0] + zs[it][1]) }
    }
}
