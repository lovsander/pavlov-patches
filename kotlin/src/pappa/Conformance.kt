package pappa

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/**
 * Проверка порта по конформанс-векторам (spec/conformance/vectors).
 * Допуски — те же, что у C++/Go/C/JS/Java: контур 1e-6 мм, коэффициенты
 * max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
 */
object Conformance {

    data class Result(val ok: Boolean, val detail: String, val notes: List<String>)

    data class Vector(val file: String, val data: Map<String, Any?>)

    fun load(dir: Path): List<Vector> =
        Files.list(dir).use { stream ->
            stream.filter { it.fileName.toString().endsWith(".json") }.sorted().toList()
                .map { Vector(it.fileName.toString(), Json.parseObject(Files.readString(it, StandardCharsets.UTF_8))) }
        }

    private fun near(a: Double, b: Double, rel: Double, floor: Double): Boolean =
        Math.abs(a - b) <= Math.max(floor, rel * Math.abs(b))

    fun check(v: Map<String, Any?>): Result = when (Json.str(v, "kind")) {
        "model" -> checkModel(v)
        "detector" -> checkDetector(v)
        else -> checkCleaner(v)
    }

    private fun toDoubles(a: List<Any?>): DoubleArray = a.map { it as Double }.toDoubleArray()

    private fun checkDetector(v: Map<String, Any?>): Result {
        val cfg = Json.obj(v["config"])
        val exp = Json.obj(v["expected"])
        val input = Json.obj(v["input"])
        val angles = Json.doubles(input, "angles_deg")
        val radii = Json.doubles(input, "radii_mm")
        val o = Detector.Options(Json.dbl(cfg, "window_deg"), Json.dbl(cfg, "wide_deg"),
            Json.dbl(cfg, "smooth_deg"), Json.dbl(cfg, "k"), Json.dbl(cfg, "min_zone_deg"))

        val band = Detector.bandIndicator(angles, radii, o)
        val zn = Detector.zones(angles, band, o)
        val expZones = Json.arr(exp["zones_deg"])
        val expPits = Json.doubles(exp, "pits_deg")
        val notes = ArrayList<String>()

        var ok = zn.size == expZones.size
        if (!ok) notes.add("зон ${zn.size} != ${expZones.size}")
        var dev = 0.0
        for (i in expZones.indices) {
            if (i >= zn.size) break
            val e = toDoubles(Json.arr(expZones[i]))
            dev = Math.max(dev, Math.max(Math.abs(zn[i][0] - e[0]), Math.abs(zn[i][1] - e[1])))
        }
        if (zn.size != expPits.size) {
            ok = false
            notes.add("ям ${zn.size} != ${expPits.size}")
        }
        for (i in expPits.indices) {
            if (i >= zn.size) break
            val d = Math.abs(0.5 * (zn[i][0] + zn[i][1]) - expPits[i])
            dev = Math.max(dev, d)
            if (d > 1e-6) ok = false
        }
        val detail = String.format("зон %d/%d, ям %d/%d, max|Δ| %.2e°",
            zn.size, expZones.size, zn.size, expPits.size, dev)
        return Result(ok, detail, notes)
    }

    private fun checkCleaner(v: Map<String, Any?>): Result {
        val cfg = Json.obj(v["config"])
        val exp = Json.obj(v["expected"])
        val input = Json.obj(v["input"])
        val tol = Json.obj(v["tolerance"])
        val angles = Json.doubles(input, "angles_deg")
        val radii = Json.doubles(input, "radii_mm")
        val o = Cleaner.Options(Json.dbl(cfg, "baseline_deg"), Json.dbl(cfg, "iqr_k"))
        val r = Cleaner.cleanIqr(angles, radii, o)

        val ref = BooleanArray(radii.size)
        for (i in Json.ints(exp, "mask_true_indices")) ref[i] = true
        val n = radii.size
        var extra = 0
        var missing = 0
        var got = 0
        for (i in 0 until n) {
            if (r.mask[i]) {
                got++
                if (!ref[i]) extra++
            } else if (ref[i]) {
                missing++
            }
        }
        val tolN = Math.max(1, Math.floor(Json.dbl(tol, "frac", 0.02) * n).toInt())
        val want = Json.int(exp, "n_outliers")
        val ok = extra <= tolN && missing <= tolN && Math.abs(got - want) <= tolN
        val detail = String.format("выбросов %d (эталон %d), лишних %d, пропущено %d",
            got, want, extra, missing)
        return Result(ok, detail, emptyList())
    }

    private fun checkModel(v: Map<String, Any?>): Result {
        val cfg = Json.obj(v["config"])
        val exp = Json.obj(v["expected"])
        val tol = Json.obj(v["tolerance"])
        val input = Json.obj(v["input"])
        val notes = ArrayList<String>()
        var ok = true

        val opt = Model.Options(
            nPatches = Json.int(cfg, "n_patches"), phaseDeg = Json.dbl(cfg, "phase_deg"),
            degMin = Json.int(cfg, "deg_min"), degMax = Json.int(cfg, "deg_max"),
            overlapTrain = Json.dbl(cfg, "overlap_train"), overlapUse = Json.dbl(cfg, "overlap_use"),
            degElbowTol = Json.dbl(cfg, "deg_elbow_tol"),
            amplitudeScale = Json.dbl(cfg, "amplitude_scale", 180.0),
            coordMode = Json.str(cfg, "coord_mode"))
        val pitsDeg = Json.doubles(cfg, "pits_deg")
        val m = Model(opt, pitsDeg)
        if (pitsDeg.isNotEmpty()) {
            m.pitShape = Model.PitShape(Json.dbl(cfg, "sigma_deg"),
                Json.dbl(cfg, "pit_core_sigma"), Json.dbl(cfg, "pit_window_sigma"),
                Json.dbl(cfg, "pit_min_amp"), Json.bool(cfg, "tapering", true))
        }
        m.fit(Json.doubles(input, "angles_deg"), Json.doubles(input, "radii_mm"))

        val wantDeg = Json.ints(exp, "degrees")
        val gotDeg = m.degrees
        val degOk = wantDeg.contentEquals(gotDeg)
        if (!degOk) {
            ok = false
            notes.add("степени ${gotDeg.contentToString()} != ${wantDeg.contentToString()}")
        }

        val rel = Json.dbl(tol, "coefs_rel")
        val floor = Json.dbl(tol, "coefs_abs_floor")
        val coefs = Json.arr(exp["coefs"])
        var maxC = 0.0
        var badC = 0
        for (i in coefs.indices) {
            val ref = toDoubles(Json.arr(coefs[i]))
            val got = m.patches.getOrNull(i)?.coefs ?: DoubleArray(0)
            if (got.size != ref.size) { ok = false; badC++; continue }
            for (j in ref.indices) {
                maxC = Math.max(maxC, Math.abs(got[j] - ref[j]))
                if (!near(got[j], ref[j], rel, floor)) { ok = false; badC++ }
            }
        }

        val pitTerms = Json.arr(exp["pit_terms"])
        var maxPit = 0.0
        var badPit = 0
        for (i in pitTerms.indices) {
            val ref = Json.obj(pitTerms[i])
            val refDx = Json.doubles(ref, "dx_deg")
            val refAmp = Json.doubles(ref, "amp")
            val gotDx = m.patches.getOrNull(i)?.pitOffsetsDeg ?: DoubleArray(0)
            val gotAmp = m.patches.getOrNull(i)?.pitCoefs ?: DoubleArray(0)
            if (gotDx.size != refDx.size) { ok = false; badPit++; continue }
            for (j in refDx.indices) {
                val da = Math.abs(gotDx[j] - refDx[j])
                maxPit = Math.max(maxPit, Math.max(da, Math.abs(gotAmp[j] - refAmp[j])))
                if (da > 1e-9 || !near(gotAmp[j], refAmp[j], rel, floor)) { ok = false; badPit++ }
            }
        }

        val curve = Json.obj(exp["curve"])
        val ca = Json.doubles(curve, "angles_deg")
        val cr = Json.doubles(curve, "radii_mm")
        val got = m.eval(ca)
        var maxR = 0.0
        for (i in cr.indices) maxR = Math.max(maxR, Math.abs(got[i] - cr[i]))
        if (maxR > Json.dbl(tol, "curve_mm")) ok = false

        val detail = String.format("степени %s, коэфф. max|Δ| %.2e (плохих %d), "
                + "термины ям max|Δ| %.2e (плохих %d), контур max|Δ| %.2e мм",
            if (degOk) "совпали" else "РАСХОДЯТСЯ", maxC, badC, maxPit, badPit, maxR)
        return Result(ok, detail, notes)
    }
}
