import Foundation

/// Модель PAPPA (Swift): патчи с адаптивной степенью по нормированной координате,
/// smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
/// Совпадает с референсом Python и остальными портами: тот же базис, та же политика
/// степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней — ОДНИМ
/// накоплением Грама в базисе Чебышёва + RMSE по явным остаткам.
public final class Model {

    public struct Options {
        public var nPatches: Int
        public var phaseDeg: Double
        public var degMin: Int
        public var degMax: Int
        public var overlapTrain: Double
        public var overlapUse: Double
        public var degElbowTol: Double
        public var amplitudeScale: Double
        public var coordMode: String

        public init(nPatches: Int = 7, phaseDeg: Double = 24.75, degMin: Int = 4, degMax: Int = 14,
                    overlapTrain: Double = 15.0, overlapUse: Double = 5.0,
                    degElbowTol: Double = 0.05, amplitudeScale: Double = 180.0,
                    coordMode: String = "normalized") {
            self.nPatches = nPatches
            self.phaseDeg = phaseDeg
            self.degMin = degMin
            self.degMax = degMax
            self.overlapTrain = overlapTrain
            self.overlapUse = overlapUse
            self.degElbowTol = degElbowTol
            self.amplitudeScale = amplitudeScale
            self.coordMode = coordMode
        }
    }

    public struct PitShape {
        public var sigmaDeg: Double = 3.0
        public var coreSigma: Double = 2.0
        public var windowSigma: Double = 3.2
        public var pitMinAmp: Double = 3e-3
        public var tapering: Bool = true
        public init() {}
    }

    public struct Metrics {
        public let amplitudeMm: Double
        public let meanRadiusMm: Double
        public let amplitudeNorm: Double
        public let degElbowTol: Double
        public let rmseSelectedMm: Double
        public let rmseBestMm: Double
        public let nTrainPoints: Int
    }

    public struct Stats {
        public let rmseMm: Double
        public let maeMm: Double
        public let maxErrMm: Double
        public let correlation: Double
    }

    public struct Patch {
        public let centerDeg: Double
        public let degree: Int
        public let nPoints: Int
        public let coefs: [Double]
        public let pitOffsetsDeg: [Double]
        public let pitCoefs: [Double]
        public let metrics: Metrics
        public let stats: Stats
    }

    public let options: Options
    public var pitShape = PitShape()
    public private(set) var pits: [Double] = []
    public private(set) var patches: [Patch] = []
    public private(set) var halfSector: Double = 0
    public private(set) var isFitted = false

    public init(options: Options = Options(), pitsDeg: [Double] = []) {
        self.options = options
        self.pits = pitsDeg.map { (($0.truncatingRemainder(dividingBy: 360)) + 360)
            .truncatingRemainder(dividingBy: 360) }
    }

    public var hasPits: Bool { !pits.isEmpty }
    public var halfTrain: Double { halfSector + options.overlapTrain }
    public var halfUse: Double { halfSector + options.overlapUse }

    public func degrees() -> [Int] { patches.map { $0.degree } }

    /// Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg).
    public func pitShapeDeg(_ dDeg: Double) -> Double {
        let d = abs(dDeg)
        let sigma = pitShape.sigmaDeg
        let base = exp(-(d * d) / (2 * sigma * sigma))
        if !pitShape.tapering { return base }
        let core = pitShape.coreSigma * sigma
        let edge = pitShape.windowSigma * sigma
        if edge <= core { return base }
        var t = (edge - d) / (edge - core)
        t = min(1, max(0, t))
        return base * t * t * (3 - 2 * t)
    }

    /// Смещения видимых ям в локальной системе патча (°).
    public func pitOffsets(_ centerDeg: Double, _ halfWinDeg: Double) -> [Double] {
        pits.map { Signal.circLocal($0, centerDeg) }.filter { abs($0) <= halfWinDeg }
    }

    public func weight(_ dDeg: Double, _ halfUseDeg: Double) -> Double {
        if dDeg <= halfSector { return 1 }
        if dDeg <= halfUseDeg {
            return Signal.smoothstep(1 - (dDeg - halfSector) / (halfUseDeg - halfSector))
        }
        return 0
    }

    private struct DegreeChoice {
        let deg: Int
        let rmseSelected: Double
        let rmseBest: Double
    }

    /// Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
    /// не хуже лучшей более чем на degElbowTol. Быстрая ветка (normalized) — одно
    /// накопление Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
    private func estimateDegree(_ xs: [Double], _ ys: [Double]) throws -> DegreeChoice {
        let n = xs.count
        if n < 5 { return DegreeChoice(deg: options.degMin, rmseSelected: 0, rmseBest: 0) }

        var degs: [Int] = []
        var rmses: [Double] = []
        var bestDeg = options.degMin
        var best = Double.infinity

        if options.coordMode == "raw" {
            // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
            for deg in stride(from: options.degMin, through: options.degMax, by: 2) {
                var a = [[Double]](repeating: [Double](repeating: 0, count: deg + 1), count: n)
                for i in 0..<n {
                    var p = 1.0
                    for j in 0...deg {
                        a[i][deg - j] = p
                        p *= xs[i]
                    }
                }
                let c = try Linalg.lstsqQR(a, ys)
                var sse = 0.0
                for i in 0..<n {
                    let e = Linalg.polyval(c, xs[i]) - ys[i]
                    sse += e * e
                }
                let r = sqrt(sse / Double(n))
                degs.append(deg)
                rmses.append(r)
                if r < best { best = r; bestDeg = deg }
            }
        } else {
            let dmax = options.degMax
            let p = dmax + 1
            let yref = ys.reduce(0, +) / Double(n)
            var gram = [[Double]](repeating: [Double](repeating: 0, count: p), count: p)
            var rhs = [Double](repeating: 0, count: p)
            for i in 0..<n {
                let t = Linalg.chebRow(xs[i], dmax)
                let yc = ys[i] - yref
                for a in 0..<p {
                    rhs[a] += t[a] * yc
                    for c in a..<p { gram[a][c] += t[a] * t[c] }
                }
            }
            for a in 0..<p {
                if a + 1 < p {
                    for c in (a + 1)..<p { gram[c][a] = gram[a][c] }
                }
            }
            for deg in stride(from: options.degMin, through: dmax, by: 2) {
                let nn = deg + 1
                var a = [[Double]](repeating: [Double](repeating: 0, count: nn), count: nn)
                var b = [Double](repeating: 0, count: nn)
                for r in 0..<nn {
                    for c in 0..<nn { a[r][c] = gram[r][c] }
                    b[r] = rhs[r]
                }
                let c = try Linalg.lstsqQR(a, b)
                var sse = 0.0
                for i in 0..<n {
                    let e = Linalg.chebSum(c, deg, xs[i]) - (ys[i] - yref)
                    sse += e * e
                }
                let r = sqrt(sse / Double(n))
                degs.append(deg)
                rmses.append(r)
                if r < best { best = r; bestDeg = deg }
            }
        }

        let limit = best * (1 + options.degElbowTol)
        var sel = bestDeg
        var rmseSel = best
        for (k, deg) in degs.enumerated() where rmses[k] <= limit {
            sel = deg
            rmseSel = rmses[k]
            break
        }
        return DegreeChoice(deg: sel, rmseSelected: rmseSel, rmseBest: best)
    }

    /// Точки обучающего окна патча (локальная координата: нормированная или сырая).
    private func windowOf(_ angles: [Double], _ radii: [Double], _ center: Double)
        -> (xs: [Double], ys: [Double]) {
        let half = halfTrain
        let norm = options.coordMode != "raw"
        var xs: [Double] = []
        var ys: [Double] = []
        for shift in [-360.0, 0.0, 360.0] {
            for i in 0..<angles.count {
                let dx = angles[i] + shift - center
                if dx >= -half && dx <= half {
                    xs.append(norm ? dx / half : dx)
                    ys.append(radii[i])
                }
            }
        }
        return (xs, ys)
    }

    public func fit(_ angles: [Double], _ radii: [Double]) throws {
        if angles.count != radii.count {
            throw Linalg.PappaError("fit: длины не совпадают")
        }
        if angles.count < 10 { throw Linalg.PappaError("fit: слишком мало точек") }

        let sector = 360.0 / Double(options.nPatches)
        halfSector = sector / 2
        let centers = (0..<options.nPatches).map { i -> Double in
            var c = (Double(i) * sector + halfSector + options.phaseDeg)
                .truncatingRemainder(dividingBy: 360)
            if c < 0 { c += 360 }
            return c
        }
        let halfTrain = self.halfTrain
        patches = []

        for c in centers {
            let (xs, ys) = windowOf(angles, radii, c)
            let n = xs.count
            if n < 5 { continue }
            let est = try estimateDegree(xs, ys)
            let deg = est.deg

            let offs = pitOffsets(c, halfTrain)
            let ncol = deg + 1 + offs.count
            var a = [[Double]](repeating: [Double](repeating: 0, count: ncol), count: n)
            for i in 0..<n {
                var p = 1.0
                for k in stride(from: deg, through: 0, by: -1) {
                    a[i][k] = p
                    p *= xs[i]
                }
                for (j, off) in offs.enumerated() {
                    a[i][deg + 1 + j] = pitShapeDeg(abs(xs[i] * halfTrain - off))
                }
            }
            let coef = try Linalg.lstsqQR(a, ys)
            let polyCoef = Array(coef[0..<(deg + 1)])

            // Отсечка ям, которые в окне патча «не видны» (pitMinAmp).
            var keptOffsets: [Double] = []
            var keptCoefs: [Double] = []
            for (j, off) in offs.enumerated() {
                var maxAbs = 0.0
                for i in 0..<n {
                    let dDeg = abs(xs[i] * halfTrain - off)
                    maxAbs = max(maxAbs, abs(coef[deg + 1 + j] * pitShapeDeg(dDeg)))
                }
                if maxAbs >= pitShape.pitMinAmp {
                    keptOffsets.append(off)
                    keptCoefs.append(coef[deg + 1 + j])
                }
            }

            patches.append(try buildPatch(c, deg, xs, ys, polyCoef,
                                          keptOffsets, keptCoefs, est, angles, radii))
        }
        isFitted = true
    }

    /// Метрики и статистика патча по его обучающему окну (полный базис).
    private func buildPatch(_ c: Double, _ deg: Int, _ xs: [Double], _ ys: [Double],
                            _ polyCoef: [Double], _ keptOffsets: [Double],
                            _ keptCoefs: [Double], _ est: DegreeChoice,
                            _ angles: [Double], _ radii: [Double]) throws -> Patch {
        let n = xs.count
        let halfTrain = self.halfTrain
        var sse = 0.0
        var sae = 0.0
        var mx = 0.0
        var fitVals = [Double](repeating: 0, count: n)
        for i in 0..<n {
            var v = Linalg.polyval(polyCoef, xs[i])
            for (j, off) in keptOffsets.enumerated() {
                v += keptCoefs[j] * pitShapeDeg(abs(xs[i] * halfTrain - off))
            }
            fitVals[i] = v
            let e = v - ys[i]
            sse += e * e
            sae += abs(e)
            mx = max(mx, abs(e))
        }
        let nf = Double(n)
        let mf = fitVals.reduce(0, +) / nf
        let my = ys.reduce(0, +) / nf
        var cov = 0.0
        var vf = 0.0
        var vy = 0.0
        for i in 0..<n {
            let df = fitVals[i] - mf
            let dy = ys[i] - my
            cov += df * dy
            vf += df * df
            vy += dy * dy
        }
        let corr = (vf > 0 && vy > 0) ? cov / sqrt(vf * vy) : 0

        // Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
        let sec = (0..<angles.count)
            .filter { Signal.circDist(angles[$0], c) <= halfSector }
            .map { radii[$0] }
        var amp = 0.0
        var meanSec = 0.0
        if sec.count >= 5 {
            amp = Signal.percentileLinear(sec, 95) - Signal.percentileLinear(sec, 5)
            meanSec = sec.reduce(0, +) / Double(sec.count)
        }

        let metrics = Metrics(amplitudeMm: amp, meanRadiusMm: meanSec,
                              amplitudeNorm: meanSec > 0 ? amp / meanSec : 0,
                              degElbowTol: options.degElbowTol,
                              rmseSelectedMm: est.rmseSelected, rmseBestMm: est.rmseBest,
                              nTrainPoints: n)
        let stats = Stats(rmseMm: sqrt(sse / nf), maeMm: sae / nf, maxErrMm: mx,
                          correlation: corr)
        return Patch(centerDeg: c, degree: deg, nPoints: n, coefs: polyCoef,
                     pitOffsetsDeg: keptOffsets, pitCoefs: keptCoefs,
                     metrics: metrics, stats: stats)
    }

    /// Контур: нормированное smoothstep-смешивание патчей (partition of unity).
    public func evalPart(_ angles: [Double], _ part: String = "total") throws -> [Double] {
        if !isFitted { throw Linalg.PappaError("Сначала вызовите fit()") }
        let halfUse = self.halfUse
        let halfTrain = self.halfTrain
        let raw = options.coordMode == "raw"
        var out = [Double](repeating: 0, count: angles.count)
        for k in 0..<angles.count {
            let a = angles[k]
            var sumWV = 0.0
            var sumW = 0.0
            for p in patches {
                let w = weight(Signal.circDist(a, p.centerDeg), halfUse)
                if w <= 0 { continue }
                let dx = Signal.circLocal(a, p.centerDeg)
                let x = raw ? dx : dx / halfTrain
                var v = 0.0
                if part != "pit" { v += Linalg.polyval(p.coefs, x) }
                if part != "poly" {
                    for (j, off) in p.pitOffsetsDeg.enumerated() {
                        v += p.pitCoefs[j] * pitShapeDeg(abs(x * halfTrain - off))
                    }
                }
                sumWV += w * v
                sumW += w
            }
            out[k] = sumW > 0 ? sumWV / sumW : 0
        }
        return out
    }

    public func eval(_ angles: [Double]) throws -> [Double] {
        try evalPart(angles, "total")
    }
}

