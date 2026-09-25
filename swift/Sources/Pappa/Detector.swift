import Foundation

/// Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
/// по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
public enum Cleaner {

    public struct Options {
        public var baselineDeg: Double = 1.0
        public var iqrK: Double = 3.0
        public var maxRemovedFrac: Double = 0.5
        public var minPoints: Int = 20
        public init() {}
    }

    public struct Result {
        public let mask: [Bool]
        public let nOutliers: Int
        public let window: Int
    }

    public static func cleanIqr(_ angles: [Double], _ radii: [Double],
                                _ o: Options = Options()) -> Result {
        let n = radii.count
        var mask = [Bool](repeating: false, count: n)
        if n < o.minPoints { return Result(mask: mask, nOutliers: 0, window: 0) }

        let w = Signal.windowPoints(angles, o.baselineDeg)
        let base = Signal.medianFilterWrap(radii, w)
        let res = (0..<n).map { radii[$0] - base[$0] }

        let center = Signal.median(res)
        let spread = Signal.iqr(res)
        let denom = spread > 1e-12 ? spread : 1.0   // защита референса

        let sev = res.map { abs($0 - center) / denom }
        var flagged = 0
        for i in 0..<n {
            mask[i] = sev[i] > o.iqrK
            if mask[i] { flagged += 1 }
        }

        // Предохранитель: не выбрасываем больше maxRemovedFrac точек.
        let cap = Int(floor(o.maxRemovedFrac * Double(n)))
        if cap > 0 && cap < n && flagged > cap {
            let kept = (0..<n).filter { mask[$0] }.map { sev[$0] }.sorted()
            let level = kept[kept.count - cap]
            flagged = 0
            for i in 0..<n {
                mask[i] = mask[i] && sev[i] >= level
                if mask[i] { flagged += 1 }
            }
        }
        return Result(mask: mask, nOutliers: flagged, window: w)
    }
}

/// Детектор ям (трещин) — повторение python/pappa/analysis/zones.py:
/// band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
/// нормированная на свою робастную sigma; зоны = участки > k длиной ≥ minZoneDeg.
public enum Detector {

    public struct Options {
        public var windowDeg: Double = 1.0
        public var wideDeg: Double = 10.0
        public var smoothDeg: Double = 2.0
        public var k: Double = 5.5
        public var minZoneDeg: Double = 2.0
        public init() {}
    }

    public struct Zone {
        public let lo: Double
        public let hi: Double
        public var center: Double { 0.5 * (lo + hi) }
    }

    public static func bandIndicator(_ angles: [Double], _ radii: [Double],
                                     _ o: Options = Options()) -> [Double] {
        let n = radii.count
        let narrow = Signal.medianFilterWrap(radii, Signal.windowPoints(angles, o.windowDeg))
        let wide = Signal.medianFilterWrap(radii, Signal.windowPoints(angles, o.wideDeg))
        let band = (0..<n).map { abs(narrow[$0] - wide[$0]) }

        var out = Signal.smoothWrap(band, Signal.windowPoints(angles, o.smoothDeg))
        let s = Signal.robustSigma(out)
        if s > 1e-12 {
            for i in 0..<n { out[i] /= s }
        } else {
            for i in 0..<n { out[i] = 0 }
        }
        return out
    }

    /// Непрерывные зоны по маске (углы — по возрастанию).
    public static func maskToZones(_ angles: [Double], _ mask: [Bool],
                                   _ o: Options = Options()) -> [Zone] {
        let n = angles.count
        if !mask.contains(true) { return [] }

        let diffs = (1..<n).map { angles[$0] - angles[$0 - 1] }
        let step = diffs.isEmpty ? 1.0 : Signal.median(diffs)

        var zones: [Zone] = []
        var i = 0
        while i < n {
            if !mask[i] { i += 1; continue }
            var j = i
            while j + 1 < n && mask[j + 1] { j += 1 }
            zones.append(Zone(lo: angles[i] - step / 2, hi: angles[j] + step / 2))
            i = j + 1
        }

        // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
        if zones.count > 1 && mask[0] && mask[n - 1] {
            let first = zones[0]
            let last = zones[zones.count - 1]
            var merged: [Zone] = [Zone(lo: last.lo - 360, hi: first.hi)]
            if zones.count > 2 {
                merged.append(contentsOf: zones[1..<(zones.count - 1)])
            }
            zones = merged
        }
        return zones.filter { $0.hi - $0.lo >= o.minZoneDeg }
    }

    public static func zones(_ angles: [Double], _ values: [Double],
                             _ o: Options = Options()) -> [Zone] {
        maskToZones(angles, values.map { $0 > o.k }, o)
    }

    /// Центры ям (°).
    public static func pits(_ angles: [Double], _ radii: [Double],
                            _ o: Options = Options()) -> [Double] {
        let band = bandIndicator(angles, radii, o)
        return zones(angles, band, o).map { $0.center }
    }
}
