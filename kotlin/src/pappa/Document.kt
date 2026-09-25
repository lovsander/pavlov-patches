package pappa

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/**
 * Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java:
 *   <out_dir>/sample.json              манифест (format pappa-sample v1.0)
 *   <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
 * Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
 * сравниваются численно (python/studies/verify_port.py).
 */
object Document {

    const val PORT_VERSION = "0.1.0"

    data class SampleOptions(
        val name: String, val inputCsv: String, val pits: Boolean, val description: String,
        val cleaner: Cleaner.Options = Cleaner.Options(),
        val detector: Detector.Options = Detector.Options(),
    )

    private fun isoUtcNow(): String =
        ZonedDateTime.now(ZoneOffset.UTC).format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'"))

    /** Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++. */
    private class W {
        val sb = StringBuilder()
        var depth = 0

        fun ind(): String = "  ".repeat(maxOf(0, depth))
        fun objStart() { sb.append('{'); depth++; sb.append('\n').append(ind()) }
        fun objEnd() { depth--; sb.append('\n').append(ind()).append('}') }
        fun arrStart() { sb.append('['); depth++; sb.append('\n').append(ind()) }
        fun arrEnd() { depth--; sb.append('\n').append(ind()).append(']') }
        fun comma() { sb.append(',').append('\n').append(ind()) }
        fun key(k: String) { sb.append(ind()).append('"').append(k).append("\": ") }
        fun str(s: String) { sb.append('"').append(Json.esc(s)).append('"') }
        fun num(v: Double) { sb.append(Json.num(v)) }
        fun raw(s: String) { sb.append(s) }
        fun kv(k: String, v: String) { key(k); str(v) }
        fun kv(k: String, v: Double) { key(k); num(v) }
        fun kv(k: String, v: Int) { key(k); sb.append(v) }
        fun kv(k: String, v: Boolean) { key(k); sb.append(v) }
    }

    private fun writePatches(w: W, m: Model) {
        w.key("patches")
        w.arrStart()
        m.patches.forEachIndexed { i, p ->
            w.sb.append(if (i > 0) ",\n" + w.ind() else "\n" + w.ind())
            w.objStart()
            w.kv("center_deg", p.centerDeg);  w.comma()
            w.kv("degree", p.degree);         w.comma()
            w.kv("n_points", p.nPoints);      w.comma()
            w.key("coefs")
            w.arrStart()
            p.coefs.forEachIndexed { j, c -> if (j > 0) w.raw(", "); w.num(c) }
            w.arrEnd()
            w.comma()

            w.key("metrics")
            w.objStart()
            w.kv("amplitude_mm", p.metrics.amplitudeMm);            w.comma()
            w.kv("mean_radius_mm", p.metrics.meanRadiusMm);         w.comma()
            w.kv("amplitude_norm", p.metrics.amplitudeNorm);        w.comma()
            w.kv("deg_elbow_tol", p.metrics.degElbowTol);           w.comma()
            w.kv("rmse_selected_mm", p.metrics.rmseSelectedMm);     w.comma()
            w.kv("rmse_best_mm", p.metrics.rmseBestMm);             w.comma()
            w.kv("n_train_points", p.metrics.nTrainPoints)
            w.objEnd()
            w.comma()

            w.key("stats")
            w.objStart()
            w.kv("rmse_mm", p.stats.rmseMm);        w.comma()
            w.kv("mae_mm", p.stats.maeMm);          w.comma()
            w.kv("max_err_mm", p.stats.maxErrMm);   w.comma()
            w.kv("correlation", p.stats.correlation)
            w.objEnd()

            // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
            // (включая пустой список): так ждёт загрузчик Python.
            if (m.hasPits) {
                w.comma()
                w.key("pit_terms")
                w.arrStart()
                p.pitOffsetsDeg.forEachIndexed { j, dx ->
                    if (j > 0) w.raw(", ")
                    w.objStart()
                    w.kv("dx_deg", dx);             w.comma()
                    w.kv("amp", p.pitCoefs[j])
                    w.objEnd()
                }
                w.arrEnd()
            }
            w.objEnd()
        }
        w.sb.append('\n').append(w.ind())
        w.arrEnd()
    }

    fun saveSectionDocument(path: Path, section: Csv.SectionModel): String {
        val m = section.model
        check(m.isFitted) { "saveSectionDocument: модель не обучена" }
        val w = W()
        w.objStart()
        w.kv("format", "pappa");      w.comma()
        w.kv("version", "2.0");       w.comma()
        w.kv("method", if (m.hasPits) "PitPatchApproximator" else "PatchApproximator"); w.comma()
        w.kv("created", isoUtcNow()); w.comma()

        w.key("software")
        w.objStart()
        w.kv("language", "kotlin");   w.comma()
        w.kv("pappa_version", PORT_VERSION)
        w.objEnd()
        w.comma()

        w.key("meta")
        w.objStart()
        w.kv("section_id", section.sectionId);     w.comma()
        w.kv("height_mm", section.heightMm);       w.comma()
        w.kv("source", "csv");                     w.comma()
        w.kv("description", section.description)
        w.objEnd()
        w.comma()

        w.key("global")
        w.objStart()
        w.key("units")
        w.objStart()
        w.kv("angle", "degree");  w.comma()
        w.kv("length", "mm")
        w.objEnd()
        w.comma()
        val opt = m.options
        w.kv("n_patches", opt.nPatches);             w.comma()
        w.kv("half_sector_deg", m.halfSector);       w.comma()
        w.kv("phase_deg", opt.phaseDeg);             w.comma()
        w.kv("half_train_deg", m.halfTrain);         w.comma()
        w.kv("half_use_deg", m.halfUse);             w.comma()
        w.kv("overlap_train_deg", opt.overlapTrain); w.comma()
        w.kv("overlap_use_deg", opt.overlapUse);     w.comma()
        w.kv("deg_min", opt.degMin);                 w.comma()
        w.kv("deg_max", opt.degMax);                 w.comma()
        w.kv("coord_mode", opt.coordMode);           w.comma()
        w.kv("deg_elbow_tol", opt.degElbowTol);      w.comma()
        w.kv("amplitude_scale", opt.amplitudeScale)
        if (m.hasPits) {
            val ps = m.pitShape
            w.comma()
            w.key("pit")
            w.objStart()
            w.kv("sigma_deg", ps.sigmaDeg);        w.comma()
            w.kv("core_sigma", ps.coreSigma);      w.comma()
            w.kv("window_sigma", ps.windowSigma);  w.comma()
            w.kv("pit_min_amp", ps.pitMinAmp);     w.comma()
            w.kv("tapering", ps.tapering);         w.comma()
            w.key("centers_deg")
            w.arrStart()
            m.pits.forEachIndexed { i, c -> if (i > 0) w.raw(", "); w.num(c) }
            w.arrEnd()
            w.objEnd()
        }
        w.objEnd()
        w.comma()

        writePatches(w, m)
        w.comma()

        w.key("statistics")
        w.objStart()
        w.kv("n_points_total", section.nPointsTotal);   w.comma()
        w.kv("n_outliers_removed", section.nOutliers);  w.comma()
        w.kv("fit_time_ms", section.fitTimeMs)
        w.objEnd()

        w.objEnd()
        Files.writeString(path, w.sb.toString() + "\n", StandardCharsets.UTF_8)
        return path.toString()
    }

    fun saveSample(outDir: String, name: String, sections: List<Csv.SectionModel>,
                   o: SampleOptions): String {
        val root = Path.of(outDir)
        Files.createDirectories(root.resolve("sections"))

        val ordered = sections.sortedBy { it.sectionId }
        val first = ordered.firstOrNull()?.model

        val w = W()
        w.objStart()
        w.kv("format", "pappa-sample");  w.comma()
        w.kv("version", "1.0");          w.comma()
        w.kv("name", name);              w.comma()
        w.kv("created", isoUtcNow());    w.comma()

        w.key("units")
        w.objStart()
        w.kv("angle", "degree");  w.comma()
        w.kv("length", "mm")
        w.objEnd()
        w.comma()

        w.key("meta")
        w.objStart()
        w.kv("description", o.description)
        w.objEnd()
        w.comma()

        if (o.inputCsv.isNotEmpty()) {
            w.key("input")
            w.objStart()
            w.kv("csv", o.inputCsv)
            w.objEnd()
            w.comma()
        }

        w.key("config")
        w.objStart()
        val opt = first?.options
        w.kv("n_patches", opt?.nPatches ?: 0);           w.comma()
        w.kv("phase_deg", opt?.phaseDeg ?: 0.0);         w.comma()
        w.kv("deg_min", opt?.degMin ?: 0);               w.comma()
        w.kv("deg_max", opt?.degMax ?: 0);               w.comma()
        w.kv("overlap_train", opt?.overlapTrain ?: 0.0); w.comma()
        w.kv("overlap_use", opt?.overlapUse ?: 0.0);     w.comma()
        w.kv("deg_elbow_tol", opt?.degElbowTol ?: 0.0);  w.comma()
        w.key("cleaner")
        w.raw("{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", "
            + "\"baseline_deg\": " + Json.num(o.cleaner.baselineDeg)
            + ", \"iqr_k\": " + Json.num(o.cleaner.iqrK) + "}}")
        w.comma()
        w.kv("pits", o.pits)
        if (o.pits && first != null) {
            val ps = first.pitShape
            w.comma()
            w.kv("sigma_deg", ps.sigmaDeg);            w.comma()
            w.kv("pit_core_sigma", ps.coreSigma);      w.comma()
            w.kv("pit_window_sigma", ps.windowSigma);  w.comma()
            w.kv("pit_min_amp", ps.pitMinAmp);         w.comma()
            w.kv("tapering", ps.tapering)
        }
        w.comma()
        w.key("detector")
        w.raw("null")
        w.objEnd()
        w.comma()

        w.key("sections")
        w.arrStart()
        ordered.forEachIndexed { i, s ->
            val file = String.format("sections/%02d.pappa.json", i)
            saveSectionDocument(root.resolve(file), s)
            w.sb.append(if (i > 0) ",\n" + w.ind() else "\n" + w.ind())
            w.objStart()
            w.kv("index", i);                  w.comma()
            w.kv("section_id", s.sectionId);   w.comma()
            w.kv("height_mm", s.heightMm);     w.comma()
            w.kv("file", file);                w.comma()
            w.kv("n_points", s.nPointsTotal);  w.comma()
            w.kv("n_outliers", s.nOutliers)
            w.objEnd()
        }
        w.sb.append('\n').append(w.ind())
        w.arrEnd()

        w.objEnd()
        Files.writeString(root.resolve("sample.json"), w.sb.toString() + "\n", StandardCharsets.UTF_8)
        return root.toString()
    }
}
