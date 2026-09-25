import Foundation

/// Проверка порта по конформанс-векторам (spec/conformance/vectors).
/// Допуски — те же, что у C++/Go/C/JS/Java/Kotlin/Rust/Pascal: контур 1e-6 мм,
/// коэффициенты max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
public enum Conformance {

    public struct Outcome {
        public let ok: Bool
        public let detail: String
        public let notes: [String]
    }

    public struct Vector {
        public let file: String
        public let data: JsonValue
    }

    public static func load(_ dir: String) throws -> [Vector] {
        let fm = FileManager.default
        let names = try fm.contentsOfDirectory(atPath: dir)
            .filter { $0.hasSuffix(".json") }
            .sorted()
        if names.isEmpty {
            throw Linalg.PappaError("нет каталога векторов: \(dir)")
        }
        return try names.map {
            Vector(file: $0, data: try jsonParse(readText((dir as NSString)
                .appendingPathComponent($0))))
        }
    }

    private static func near(_ a: Double, _ b: Double, _ rel: Double, _ flr: Double) -> Bool {
        abs(a - b) <= max(flr, rel * abs(b))
    }

    public static func check(_ v: JsonValue) throws -> Outcome {
        let kind = (try? v.text("kind")) ?? ""
        if kind == "model" { return try checkModel(v) }
        if kind == "detector" { return try checkDetector(v) }
        return try checkCleaner(v)
    }

    private static func checkDetector(_ v: JsonValue) throws -> Outcome {
        let cfg = try v.key("config")
        let exp = try v.key("expected")
        let input = try v.key("input")
        let angles = try input.doubles("angles_deg")
        let radii = try input.doubles("radii_mm")
        var o = Detector.Options()
        o.windowDeg = try cfg.dbl("window_deg")
        o.wideDeg = try cfg.dbl("wide_deg")
        o.smoothDeg = try cfg.dbl("smooth_deg")
        o.k = try cfg.dbl("k")
        o.minZoneDeg = try cfg.dbl("min_zone_deg")

        let band = Detector.bandIndicator(angles, radii, o)
        let zs = Detector.zones(angles, band, o)
        let expZones = try exp.key("zones_deg").asArray()
        let expPits = try exp.doubles("pits_deg")
        var notes: [String] = []

        var ok = zs.count == expZones.count
        if !ok { notes.append("зон \(zs.count) != \(expZones.count)") }
        var dev = 0.0
        for (i, z) in expZones.enumerated() where i < zs.count {
            let e = try z.asDoubles()
            dev = max(dev, max(abs(zs[i].lo - e[0]), abs(zs[i].hi - e[1])))
        }
        if zs.count != expPits.count {
            ok = false
            notes.append("ям \(zs.count) != \(expPits.count)")
        }
        for (i, p) in expPits.enumerated() where i < zs.count {
            let d = abs(zs[i].center - p)
            dev = max(dev, d)
            if d > 1e-6 { ok = false }
        }
        return Outcome(ok: ok,
                       detail: String(format: "зон %d/%d, ям %d/%d, max|Δ| %.2e°",
                                      zs.count, expZones.count, zs.count, expPits.count, dev),
                       notes: notes)
    }

    private static func checkCleaner(_ v: JsonValue) throws -> Outcome {
        let cfg = try v.key("config")
        let exp = try v.key("expected")
        let input = try v.key("input")
        let tol = try v.key("tolerance")
        let angles = try input.doubles("angles_deg")
        let radii = try input.doubles("radii_mm")
        var o = Cleaner.Options()
        o.baselineDeg = try cfg.dbl("baseline_deg")
        o.iqrK = try cfg.dbl("iqr_k")
        let r = Cleaner.cleanIqr(angles, radii, o)

        var ref = [Bool](repeating: false, count: radii.count)
        for i in try exp.ints("mask_true_indices") where i >= 0 && i < ref.count {
            ref[i] = true
        }
        let n = radii.count
        var extra = 0
        var missing = 0
        var got = 0
        for i in 0..<n {
            if r.mask[i] {
                got += 1
                if !ref[i] { extra += 1 }
            } else if ref[i] {
                missing += 1
            }
        }
        let frac = tol.dblOr("frac", 0.02)
        let tolN = max(1, Int(floor(frac * Double(n))))
        let want = try exp.int("n_outliers")
        let ok = extra <= tolN && missing <= tolN && abs(got - want) <= tolN
        return Outcome(ok: ok,
                       detail: "выбросов \(got) (эталон \(want)), лишних \(extra), "
                           + "пропущено \(missing)",
                       notes: [])
    }

    private static func checkModel(_ v: JsonValue) throws -> Outcome {
        let cfg = try v.key("config")
        let exp = try v.key("expected")
        let tol = try v.key("tolerance")
        let input = try v.key("input")
        var notes: [String] = []
        var ok = true

        var opt = Model.Options()
        opt.nPatches = try cfg.int("n_patches")
        opt.phaseDeg = try cfg.dbl("phase_deg")
        opt.degMin = try cfg.int("deg_min")
        opt.degMax = try cfg.int("deg_max")
        opt.overlapTrain = try cfg.dbl("overlap_train")
        opt.overlapUse = try cfg.dbl("overlap_use")
        opt.degElbowTol = try cfg.dbl("deg_elbow_tol")
        opt.amplitudeScale = cfg.dblOr("amplitude_scale", 180.0)
        opt.coordMode = try cfg.text("coord_mode")

        let pitsDeg = try cfg.doubles("pits_deg")
        let m = Model(options: opt, pitsDeg: pitsDeg)
        if !pitsDeg.isEmpty {
            m.pitShape.sigmaDeg = try cfg.dbl("sigma_deg")
            m.pitShape.coreSigma = try cfg.dbl("pit_core_sigma")
            m.pitShape.windowSigma = try cfg.dbl("pit_window_sigma")
            m.pitShape.pitMinAmp = try cfg.dbl("pit_min_amp")
            m.pitShape.tapering = cfg.boolOr("tapering", true)
        }
        try m.fit(try input.doubles("angles_deg"), try input.doubles("radii_mm"))

        let wantDeg = try exp.ints("degrees")
        let gotDeg = m.degrees()
        let degOk = wantDeg == gotDeg
        if !degOk {
            ok = false
            notes.append("степени \(gotDeg) != \(wantDeg)")
        }

        let rel = try tol.dbl("coefs_rel")
        let flr = try tol.dbl("coefs_abs_floor")
        var maxC = 0.0
        var badC = 0
        let coefsN = try exp.key("coefs").asArray()
        for (i, node) in coefsN.enumerated() {
            let ref = try node.asDoubles()
            let got = i < m.patches.count ? m.patches[i].coefs : []
            if got.count != ref.count { ok = false; badC += 1; continue }
            for j in 0..<ref.count {
                maxC = max(maxC, abs(got[j] - ref[j]))
                if !near(got[j], ref[j], rel, flr) { ok = false; badC += 1 }
            }
        }

        var maxPit = 0.0
        var badPit = 0
        let terms = try exp.key("pit_terms").asArray()
        for (i, node) in terms.enumerated() {
            let refDx = try node.doubles("dx_deg")
            let refAmp = try node.doubles("amp")
            let gotDx = i < m.patches.count ? m.patches[i].pitOffsetsDeg : []
            let gotAmp = i < m.patches.count ? m.patches[i].pitCoefs : []
            if gotDx.count != refDx.count { ok = false; badPit += 1; continue }
            for j in 0..<refDx.count {
                let da = abs(gotDx[j] - refDx[j])
                maxPit = max(maxPit, max(da, abs(gotAmp[j] - refAmp[j])))
                if da > 1e-9 || !near(gotAmp[j], refAmp[j], rel, flr) {
                    ok = false
                    badPit += 1
                }
            }
        }

        let curve = try exp.key("curve")
        let ca = try curve.doubles("angles_deg")
        let cr = try curve.doubles("radii_mm")
        let got = try m.eval(ca)
        var maxR = 0.0
        for i in 0..<cr.count { maxR = max(maxR, abs(got[i] - cr[i])) }
        if maxR > (try tol.dbl("curve_mm")) { ok = false }

        let detail = String(format: "степени %@, коэфф. max|Δ| %.2e (плохих %d), "
                + "термины ям max|Δ| %.2e (плохих %d), контур max|Δ| %.2e мм",
            degOk ? "совпали" : "РАСХОДЯТСЯ", maxC, badC, maxPit, badPit, maxR)
        return Outcome(ok: ok, detail: detail, notes: notes)
    }
}
