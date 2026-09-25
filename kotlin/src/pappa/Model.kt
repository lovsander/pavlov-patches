package pappa

/**
 * Модель PAPPA (Kotlin): патчи с адаптивной степенью по нормированной координате,
 * smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
 * Совпадает с референсом Python и портами C/C++/Go/JS/Java: тот же базис, та же
 * политика степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней — ОДНИМ
 * накоплением Грама в базисе Чебышёва + RMSE по явным остаткам.
 */
class Model(private val opt: Options = Options(), pitsDeg: DoubleArray = DoubleArray(0)) {

    data class Options(
        val nPatches: Int = 7,
        val phaseDeg: Double = 24.75,
        val degMin: Int = 4,
        val degMax: Int = 14,
        val overlapTrain: Double = 15.0,
        val overlapUse: Double = 5.0,
        val degElbowTol: Double = 0.05,
        val amplitudeScale: Double = 180.0,
        val coordMode: String = "normalized",
    )

    data class PitShape(
        val sigmaDeg: Double = 3.0,
        val coreSigma: Double = 2.0,
        val windowSigma: Double = 3.2,
        val pitMinAmp: Double = 3e-3,
        val tapering: Boolean = true,
    )

    data class Metrics(
        val amplitudeMm: Double, val meanRadiusMm: Double, val amplitudeNorm: Double,
        val degElbowTol: Double, val rmseSelectedMm: Double, val rmseBestMm: Double,
        val nTrainPoints: Int,
    )

    data class Stats(
        val rmseMm: Double, val maeMm: Double, val maxErrMm: Double, val correlation: Double,
    )

    data class Patch(
        val centerDeg: Double, val degree: Int, val nPoints: Int, val coefs: DoubleArray,
        val pitOffsetsDeg: DoubleArray, val pitCoefs: DoubleArray,
        val metrics: Metrics, val stats: Stats,
    ) {
        override fun equals(other: Any?): Boolean = this === other
        override fun hashCode(): Int = System.identityHashCode(this)
    }

    val options: Options get() = opt
    var pitShape: PitShape = PitShape()
    private var pitCenters = DoubleArray(0)
    private val patchList = ArrayList<Patch>()
    private var centersArr = DoubleArray(0)
    private var halfSectorDeg = 0.0
    var isFitted = false
        private set

    init {
        setPits(pitsDeg)
    }

    fun setPits(centersDeg: DoubleArray) {
        pitCenters = DoubleArray(centersDeg.size) { ((centersDeg[it] % 360) + 360) % 360 }
    }

    val pits: DoubleArray get() = pitCenters
    val patches: List<Patch> get() = patchList
    val hasPits: Boolean get() = pitCenters.isNotEmpty()
    val halfSector: Double get() = halfSectorDeg
    val halfTrain: Double get() = halfSectorDeg + opt.overlapTrain
    val halfUse: Double get() = halfSectorDeg + opt.overlapUse

    /** Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg). */
    fun pitShapeDeg(dDeg: Double): Double {
        val d = Math.abs(dDeg)
        val sigma = pitShape.sigmaDeg
        val val0 = Math.exp(-(d * d) / (2 * sigma * sigma))
        if (!pitShape.tapering) return val0
        val core = pitShape.coreSigma * sigma
        val edge = pitShape.windowSigma * sigma
        if (edge <= core) return val0
        var t = (edge - d) / (edge - core)
        t = Math.min(1.0, Math.max(0.0, t))
        return val0 * t * t * (3 - 2 * t)
    }

    /** Смещения видимых ям в локальной системе патча (°). */
    fun pitOffsets(centerDeg: Double, halfWinDeg: Double): DoubleArray =
        pitCenters.map { Signal.circLocal(it, centerDeg) }
            .filter { Math.abs(it) <= halfWinDeg }
            .toDoubleArray()

    fun weight(dDeg: Double, halfUseDeg: Double): Double = when {
        dDeg <= halfSectorDeg -> 1.0
        dDeg <= halfUseDeg ->
            Signal.smoothstep(1 - (dDeg - halfSectorDeg) / (halfUseDeg - halfSectorDeg))
        else -> 0.0
    }

    val degrees: IntArray get() = IntArray(patchList.size) { patchList[it].degree }

    private data class DegreeChoice(
        val deg: Int, val rmseSelected: Double, val rmseBest: Double, val nTrain: Int,
    )

    /**
     * Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
     * не хуже лучшей более чем на degElbowTol. Быстрая ветка (normalized) — одно
     * накопление Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
     */
    private fun estimateDegree(xs: DoubleArray, ys: DoubleArray): DegreeChoice {
        val n = xs.size
        if (n < 5) return DegreeChoice(opt.degMin, 0.0, 0.0, n)

        val degs = ArrayList<Int>()
        val rmses = ArrayList<Double>()
        var bestDeg = opt.degMin
        var best = Double.POSITIVE_INFINITY

        if (opt.coordMode == "raw") {
            // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
            var deg = opt.degMin
            while (deg <= opt.degMax) {
                val a = Array(n) { DoubleArray(deg + 1) }
                for (i in 0 until n) {
                    var p = 1.0
                    for (j in 0..deg) {
                        a[i][deg - j] = p
                        p *= xs[i]
                    }
                }
                val c = Linalg.lstsqQR(a, ys)
                var sse = 0.0
                for (i in 0 until n) {
                    val e = Linalg.polyval(c, xs[i]) - ys[i]
                    sse += e * e
                }
                val r = Math.sqrt(sse / n)
                degs.add(deg)
                rmses.add(r)
                if (r < best) { best = r; bestDeg = deg }
                deg += 2
            }
        } else {
            val dmax = opt.degMax
            val p = dmax + 1
            var yref = 0.0
            for (v in ys) yref += v
            yref /= n
            val gram = Array(p) { DoubleArray(p) }
            val rhs = DoubleArray(p)
            for (i in 0 until n) {
                val t = Linalg.chebRow(xs[i], dmax)
                val yc = ys[i] - yref
                for (a in 0 until p) {
                    rhs[a] += t[a] * yc
                    for (c in a until p) gram[a][c] += t[a] * t[c]
                }
            }
            for (a in 0 until p) for (c in a + 1 until p) gram[c][a] = gram[a][c]

            var deg = opt.degMin
            while (deg <= dmax) {
                val nn = deg + 1
                val a = Array(nn) { r -> gram[r].copyOf(nn) }
                val b = rhs.copyOf(nn)
                val c = Linalg.lstsqQR(a, b)
                var sse = 0.0
                for (i in 0 until n) {
                    val e = Linalg.chebSum(c, deg, xs[i]) - (ys[i] - yref)
                    sse += e * e
                }
                val r = Math.sqrt(sse / n)
                degs.add(deg)
                rmses.add(r)
                if (r < best) { best = r; bestDeg = deg }
                deg += 2
            }
        }

        val limit = best * (1 + opt.degElbowTol)
        var sel = bestDeg
        var rmseSel = best
        for (k in degs.indices) {            // степени по возрастанию
            if (rmses[k] <= limit) { sel = degs[k]; rmseSel = rmses[k]; break }
        }
        return DegreeChoice(sel, rmseSel, best, n)
    }

    /** Точки обучающего окна патча (локальная координата: нормированная или сырая). */
    private fun windowOf(angles: DoubleArray, radii: DoubleArray, center: Double): Pair<DoubleArray, DoubleArray> {
        val half = halfTrain
        val norm = opt.coordMode != "raw"
        val xs = ArrayList<Double>()
        val ys = ArrayList<Double>()
        for (shift in doubleArrayOf(-360.0, 0.0, 360.0)) {
            for (i in angles.indices) {
                val dx = angles[i] + shift - center
                if (dx >= -half && dx <= half) {
                    xs.add(if (norm) dx / half else dx)
                    ys.add(radii[i])
                }
            }
        }
        return xs.toDoubleArray() to ys.toDoubleArray()
    }

    fun fit(angles: DoubleArray, radii: DoubleArray): Model {
        require(angles.size == radii.size) { "fit: длины не совпадают" }
        require(angles.size >= 10) { "fit: слишком мало точек" }

        val sector = 360.0 / opt.nPatches
        halfSectorDeg = sector / 2
        centersArr = DoubleArray(opt.nPatches) {
            var c = (it * sector + halfSectorDeg + opt.phaseDeg) % 360
            if (c < 0) c += 360
            c
        }
        val halfTrain = halfTrain
        patchList.clear()

        for (c in centersArr) {
            val (xs, ys) = windowOf(angles, radii, c)
            val n = xs.size
            if (n < 5) continue
            val est = estimateDegree(xs, ys)
            val deg = est.deg

            val offs = pitOffsets(c, halfTrain)
            val ncol = deg + 1 + offs.size
            val a = Array(n) { DoubleArray(ncol) }
            for (i in 0 until n) {
                var p = 1.0
                for (k in deg downTo 0) {
                    a[i][k] = p
                    p *= xs[i]
                }
                for (j in offs.indices) {
                    a[i][deg + 1 + j] = pitShapeDeg(Math.abs(xs[i] * halfTrain - offs[j]))
                }
            }
            val coef = Linalg.lstsqQR(a, ys)
            val polyCoef = coef.copyOf(deg + 1)

            // Отсечка ям, которые в окне патча «не видны» (pitMinAmp).
            val keptOffsets = ArrayList<Double>()
            val keptCoefs = ArrayList<Double>()
            for (j in offs.indices) {
                var maxAbs = 0.0
                for (i in 0 until n) {
                    val dDeg = Math.abs(xs[i] * halfTrain - offs[j])
                    maxAbs = Math.max(maxAbs, Math.abs(coef[deg + 1 + j] * pitShapeDeg(dDeg)))
                }
                if (maxAbs >= pitShape.pitMinAmp) {
                    keptOffsets.add(offs[j])
                    keptCoefs.add(coef[deg + 1 + j])
                }
            }
            patchList.add(buildPatch(c, deg, xs, ys, polyCoef,
                keptOffsets.toDoubleArray(), keptCoefs.toDoubleArray(), est, angles, radii))
        }
        isFitted = true
        return this
    }

    /** Метрики и статистика патча по его обучающему окну (полный базис). */
    private fun buildPatch(c: Double, deg: Int, xs: DoubleArray, ys: DoubleArray,
                           polyCoef: DoubleArray, keptOffsets: DoubleArray,
                           keptCoefs: DoubleArray, est: DegreeChoice,
                           angles: DoubleArray, radii: DoubleArray): Patch {
        val n = xs.size
        var sse = 0.0
        var sae = 0.0
        var mx = 0.0
        val fitVals = DoubleArray(n)
        for (i in 0 until n) {
            var v = Linalg.polyval(polyCoef, xs[i])
            for (j in keptOffsets.indices) {
                v += keptCoefs[j] * pitShapeDeg(Math.abs(xs[i] * halfTrain - keptOffsets[j]))
            }
            fitVals[i] = v
            val e = v - ys[i]
            sse += e * e
            sae += Math.abs(e)
            mx = Math.max(mx, Math.abs(e))
        }
        var mf = 0.0
        var my = 0.0
        for (i in 0 until n) { mf += fitVals[i]; my += ys[i] }
        mf /= n
        my /= n
        var cov = 0.0
        var vf = 0.0
        var vy = 0.0
        for (i in 0 until n) {
            val df = fitVals[i] - mf
            val dy = ys[i] - my
            cov += df * dy
            vf += df * df
            vy += dy * dy
        }
        val corr = if (vf > 0 && vy > 0) cov / Math.sqrt(vf * vy) else 0.0

        // Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
        val sec = ArrayList<Double>()
        for (i in angles.indices) {
            if (Signal.circDist(angles[i], c) <= halfSectorDeg) sec.add(radii[i])
        }
        var amp = 0.0
        var meanSec = 0.0
        if (sec.size >= 5) {
            val arr = sec.toDoubleArray()
            amp = Signal.percentileLinear(arr, 95.0) - Signal.percentileLinear(arr, 5.0)
            for (v in arr) meanSec += v
            meanSec /= arr.size
        }

        val metrics = Metrics(amp, meanSec, if (meanSec > 0) amp / meanSec else 0.0,
            opt.degElbowTol, est.rmseSelected, est.rmseBest, n)
        val stats = Stats(Math.sqrt(sse / n), sae / n, mx, corr)
        return Patch(c, deg, n, polyCoef, keptOffsets, keptCoefs, metrics, stats)
    }

    /** Контур: нормированное smoothstep-смешивание патчей (partition of unity). */
    fun evalPart(angles: DoubleArray, part: String = "total"): DoubleArray {
        check(isFitted) { "Сначала вызовите fit()" }
        val halfUse = halfUse
        val halfTrain = halfTrain
        val out = DoubleArray(angles.size)
        for (k in angles.indices) {
            val a = angles[k]
            var sumWv = 0.0
            var sumW = 0.0
            for (p in patchList) {
                val w = weight(Signal.circDist(a, p.centerDeg), halfUse)
                if (w <= 0) continue
                val dx = Signal.circLocal(a, p.centerDeg)
                val x = if (opt.coordMode == "raw") dx else dx / halfTrain
                var v = 0.0
                if (part != "pit") v += Linalg.polyval(p.coefs, x)
                if (part != "poly") {
                    for (j in p.pitOffsetsDeg.indices) {
                        v += p.pitCoefs[j] * pitShapeDeg(Math.abs(x * halfTrain - p.pitOffsetsDeg[j]))
                    }
                }
                sumWv += w * v
                sumW += w
            }
            out[k] = if (sumW > 0) sumWv / sumW else 0.0
        }
        return out
    }

    fun eval(angles: DoubleArray): DoubleArray = evalPart(angles)
}
