import Foundation

/// Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin/Rust/Pascal:
///   <out_dir>/sample.json              манифест (format pappa-sample v1.0)
///   <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
/// Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
/// сравниваются численно (python/studies/verify_port.py).
public enum Document {

    public static let portVersion = "0.1.0"
    public static let portLanguage = "swift"

    public struct SampleOptions {
        public var inputCsv = ""
        public var pits = true
        public var description = "PAPPA Swift port"
        public var cleaner = Cleaner.Options()
        public var detector = Detector.Options()
        public init() {}
    }

    /// Сечение даты из числа дней с 1970-01-01 (алгоритм Говарда Хиннанта):
    /// в Foundation форматирование даты есть, но так меньше поводов для сюрпризов.
    private static func civilFromDays(_ z0: Int) -> (Int, Int, Int) {
        let z = z0 + 719468
        let era = (z >= 0 ? z : z - 146096) / 146097
        let doe = z - era * 146097
        let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
        let y = yoe + era * 400
        let doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
        let mp = (5 * doy + 2) / 153
        let d = doy - (153 * mp + 2) / 5 + 1
        let m = mp < 10 ? mp + 3 : mp - 9
        return (m <= 2 ? y + 1 : y, m, d)
    }

    public static func isoUtcNow() -> String {
        let secs = Int(Date().timeIntervalSince1970)
        let days = secs >= 0 ? secs / 86400 : (secs - 86399) / 86400
        let rem = secs - days * 86400
        let (y, m, d) = civilFromDays(days)
        func p2(_ v: Int) -> String { v < 10 ? "0\(v)" : "\(v)" }
        return "\(y)-\(p2(m))-\(p2(d))T\(p2(rem / 3600)):\(p2((rem % 3600) / 60)):\(p2(rem % 60))Z"
    }

    /// Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++.
    final class Writer {
        var sb = ""
        var depth = 0

        var ind: String { String(repeating: " ", count: max(0, depth) * 2) }

        func objStart() { sb += "{"; depth += 1; sb += "\n" + ind }
        func objEnd() { depth -= 1; sb += "\n" + ind + "}" }
        func arrStart() { sb += "["; depth += 1; sb += "\n" + ind }
        func arrEnd() { depth -= 1; sb += "\n" + ind + "]" }
        func comma() { sb += ",\n" + ind }
        func key(_ k: String) { sb += ind + "\"" + k + "\": " }
        func strVal(_ v: String) { sb += "\"" + jsonEsc(v) + "\"" }
        func numVal(_ v: Double) { sb += jsonNum(v) }
        func raw(_ s: String) { sb += s }

        func kv(_ k: String, _ v: String) { key(k); strVal(v) }
        func kv(_ k: String, _ v: Double) { key(k); numVal(v) }
        func kv(_ k: String, _ v: Int) { key(k); sb += String(v) }
        func kv(_ k: String, _ v: Bool) { key(k); sb += v ? "true" : "false" }
    }

    private static func writePatches(_ w: Writer, _ m: Model) {
        w.key("patches")
        w.arrStart()
        for (i, p) in m.patches.enumerated() {
            w.raw(i > 0 ? ",\n" + w.ind : "\n" + w.ind)
            w.objStart()
            w.kv("center_deg", p.centerDeg);  w.comma()
            w.kv("degree", p.degree);         w.comma()
            w.kv("n_points", p.nPoints);      w.comma()
            w.key("coefs")
            w.arrStart()
            for (j, c) in p.coefs.enumerated() {
                if j > 0 { w.raw(", ") }
                w.numVal(c)
            }
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
            w.kv("rmse_mm", p.stats.rmseMm);          w.comma()
            w.kv("mae_mm", p.stats.maeMm);            w.comma()
            w.kv("max_err_mm", p.stats.maxErrMm);     w.comma()
            w.kv("correlation", p.stats.correlation)
            w.objEnd()

            // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
            // (включая пустой список): так ждёт загрузчик Python.
            if m.hasPits {
                w.comma()
                w.key("pit_terms")
                w.arrStart()
                for (j, off) in p.pitOffsetsDeg.enumerated() {
                    if j > 0 { w.raw(", ") }
                    w.objStart()
                    w.kv("dx_deg", off);            w.comma()
                    w.kv("amp", p.pitCoefs[j])
                    w.objEnd()
                }
                w.arrEnd()
            }
            w.objEnd()
        }
        if !m.patches.isEmpty { w.raw("\n" + w.ind) }
        w.arrEnd()
    }

    @discardableResult
    public static func saveSectionDocument(_ path: String, _ section: SectionModel) throws -> String {
        let m = section.model
        if !m.isFitted { throw Linalg.PappaError("saveSectionDocument: модель не обучена") }
        let w = Writer()
        w.objStart()
        w.kv("format", "pappa");   w.comma()
        w.kv("version", "2.0");    w.comma()
        w.kv("method", m.hasPits ? "PitPatchApproximator" : "PatchApproximator"); w.comma()
        w.kv("created", isoUtcNow());  w.comma()

        w.key("software")
        w.objStart()
        w.kv("language", portLanguage);   w.comma()
        w.kv("pappa_version", portVersion)
        w.objEnd()
        w.comma()

        w.key("meta")
        w.objStart()
        w.kv("section_id", section.sectionId);   w.comma()
        w.kv("height_mm", section.heightMm);     w.comma()
        w.kv("source", "csv");                   w.comma()
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
        let opt = m.options
        w.kv("n_patches", opt.nPatches);            w.comma()
        w.kv("half_sector_deg", m.halfSector);      w.comma()
        w.kv("phase_deg", opt.phaseDeg);            w.comma()
        w.kv("half_train_deg", m.halfTrain);        w.comma()
        w.kv("half_use_deg", m.halfUse);            w.comma()
        w.kv("overlap_train_deg", opt.overlapTrain); w.comma()
        w.kv("overlap_use_deg", opt.overlapUse);    w.comma()
        w.kv("deg_min", opt.degMin);                w.comma()
        w.kv("deg_max", opt.degMax);                w.comma()
        w.kv("coord_mode", opt.coordMode);          w.comma()
        w.kv("deg_elbow_tol", opt.degElbowTol);     w.comma()
        w.kv("amplitude_scale", opt.amplitudeScale)
        if m.hasPits {
            let ps = m.pitShape
            w.comma()
            w.key("pit")
            w.objStart()
            w.kv("sigma_deg", ps.sigmaDeg);          w.comma()
            w.kv("core_sigma", ps.coreSigma);        w.comma()
            w.kv("window_sigma", ps.windowSigma);    w.comma()
            w.kv("pit_min_amp", ps.pitMinAmp);       w.comma()
            w.kv("tapering", ps.tapering);           w.comma()
            w.key("centers_deg")
            w.arrStart()
            for (i, c) in m.pits.enumerated() {
                if i > 0 { w.raw(", ") }
                w.numVal(c)
            }
            w.arrEnd()
            w.objEnd()
        }
        w.objEnd()
        w.comma()

        writePatches(w, m)
        w.comma()

        w.key("statistics")
        w.objStart()
        w.kv("n_points_total", section.nPointsTotal);    w.comma()
        w.kv("n_outliers_removed", section.nOutliers);   w.comma()
        w.kv("fit_time_ms", section.fitTimeMs)
        w.objEnd()

        w.objEnd()
        try writeText(path, w.sb + "\n")
        return path
    }

    @discardableResult
    public static func saveSample(_ outDir: String, _ name: String, _ sections: [SectionModel],
                                  _ o: SampleOptions = SampleOptions()) throws -> String {
        let fm = FileManager.default
        let root = URL(fileURLWithPath: outDir)
        try fm.createDirectory(at: root.appendingPathComponent("sections"),
                               withIntermediateDirectories: true)

        let ordered = sections.sorted { $0.sectionId < $1.sectionId }
        let first = ordered.first?.model

        let w = Writer()
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

        if !o.inputCsv.isEmpty {
            w.key("input")
            w.objStart()
            w.kv("csv", o.inputCsv)
            w.objEnd()
            w.comma()
        }

        w.key("config")
        w.objStart()
        let opt = first?.options ?? Model.Options()
        w.kv("n_patches", first == nil ? 0 : opt.nPatches);             w.comma()
        w.kv("phase_deg", first == nil ? 0 : opt.phaseDeg);             w.comma()
        w.kv("deg_min", first == nil ? 0 : opt.degMin);                 w.comma()
        w.kv("deg_max", first == nil ? 0 : opt.degMax);                 w.comma()
        w.kv("overlap_train", first == nil ? 0 : opt.overlapTrain);     w.comma()
        w.kv("overlap_use", first == nil ? 0 : opt.overlapUse);         w.comma()
        w.kv("deg_elbow_tol", first == nil ? 0 : opt.degElbowTol);      w.comma()
        w.key("cleaner")
        w.raw("{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", \"baseline_deg\": "
            + jsonNum(o.cleaner.baselineDeg) + ", \"iqr_k\": " + jsonNum(o.cleaner.iqrK) + "}}")
        w.comma()
        w.kv("pits", o.pits)
        if o.pits, let m = first {
            let ps = m.pitShape
            w.comma()
            w.kv("sigma_deg", ps.sigmaDeg);              w.comma()
            w.kv("pit_core_sigma", ps.coreSigma);        w.comma()
            w.kv("pit_window_sigma", ps.windowSigma);    w.comma()
            w.kv("pit_min_amp", ps.pitMinAmp);           w.comma()
            w.kv("tapering", ps.tapering)
        }
        w.comma()
        w.key("detector")
        w.raw("null")
        w.objEnd()
        w.comma()

        w.key("sections")
        w.arrStart()
        for (i, s) in ordered.enumerated() {
            let file = String(format: "sections/%.2d.pappa.json", i)
            try saveSectionDocument(root.appendingPathComponent(file).path, s)
            w.raw(i > 0 ? ",\n" + w.ind : "\n" + w.ind)
            w.objStart()
            w.kv("index", i);                 w.comma()
            w.kv("section_id", s.sectionId);  w.comma()
            w.kv("height_mm", s.heightMm);    w.comma()
            w.kv("file", file);               w.comma()
            w.kv("n_points", s.nPointsTotal); w.comma()
            w.kv("n_outliers", s.nOutliers)
            w.objEnd()
        }
        if !ordered.isEmpty { w.raw("\n" + w.ind) }
        w.arrEnd()

        w.objEnd()
        try writeText(root.appendingPathComponent("sample.json").path, w.sb + "\n")
        return outDir
    }
}
