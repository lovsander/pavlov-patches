import Foundation

/// Сигнальные утилиты — поведение как у numpy и как в остальных портах:
/// медиана (чётное n — среднее двух центральных), перцентиль с линейной
/// интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
public enum Signal {

    /// Медиана: чётное n — среднее двух центральных (numpy.median).
    public static func median(_ values: [Double]) -> Double {
        let n = values.count
        if n == 0 { return 0 }
        let v = values.sorted()
        return n % 2 == 1 ? v[n / 2] : 0.5 * (v[n / 2 - 1] + v[n / 2])
    }

    /// Перцентиль с линейной интерполяцией (numpy.percentile).
    public static func percentileLinear(_ values: [Double], _ q: Double) -> Double {
        let n = values.count
        if n == 0 { return 0 }
        let v = values.sorted()
        let pos = (q / 100.0) * Double(n - 1)
        let lo = Int(floor(pos))
        let frac = pos - Double(lo)
        let hi = min(lo + 1, n - 1)
        return v[lo] + frac * (v[hi] - v[lo])
    }

    public static func iqr(_ values: [Double]) -> Double {
        values.isEmpty ? 0 : percentileLinear(values, 75) - percentileLinear(values, 25)
    }

    public static func mad(_ values: [Double]) -> Double {
        if values.isEmpty { return 0 }
        let m = median(values)
        return median(values.map { abs($0 - m) })
    }

    public static func robustSigma(_ values: [Double]) -> Double {
        1.4826 * mad(values)
    }

    /// Медианный шаг сетки по углам (медиана положительных разностей, иначе 1).
    public static func angularStep(_ angles: [Double]) -> Double {
        if angles.count < 2 { return 1 }
        let d = (1..<angles.count).map { angles[$0] - angles[$0 - 1] }.filter { $0 > 0 }
        return d.isEmpty ? 1 : median(d)
    }

    /// Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная.
    /// `.toNearestOrEven`, а не `.rounded()`: последнее округляет половину ОТ нуля,
    /// как Rust `round()` и Java `Math.round`; Python round(2.5) == 2.
    public static func windowPoints(_ angles: [Double], _ spanDeg: Double) -> Int {
        let n = angles.count
        if n < 3 { return max(1, n) }
        var w = Int((spanDeg / angularStep(angles)).rounded(.toNearestOrEven))
        if w % 2 == 0 { w += 1 }
        if w < 3 { w = 3 }
        if w > n { w = n % 2 == 1 ? n : n - 1 }
        return max(3, w)
    }

    private static func oddWindow(_ window: Int, _ n: Int) -> Int {
        var w = window % 2 == 0 ? window + 1 : window
        if w < 3 { w = 3 }
        if w > n { w = n % 2 == 1 ? n : n - 1 }
        return w
    }

    public static func wrapIndex(_ i: Int, _ n: Int) -> Int {
        ((i % n) + n) % n
    }

    /// Медианный фильтр по кольцу (окно в точках).
    public static func medianFilterWrap(_ x: [Double], _ window: Int) -> [Double] {
        let n = x.count
        let w = oddWindow(window, n)
        if w < 3 || n < 3 { return Array(repeating: median(x), count: n) }
        let h = (w - 1) / 2
        var out = [Double](repeating: 0, count: n)
        var win = [Double](repeating: 0, count: w)
        for i in 0..<n {
            for k in 0..<w { win[k] = x[wrapIndex(i - h + k, n)] }
            out[i] = median(win)
        }
        return out
    }

    /// Скользящее среднее по кольцу (окно в точках).
    public static func smoothWrap(_ x: [Double], _ window: Int) -> [Double] {
        let n = x.count
        let w = oddWindow(window, n)
        if w < 3 || n < 3 { return x }
        let h = (w - 1) / 2
        var out = [Double](repeating: 0, count: n)
        for i in 0..<n {
            var s = 0.0
            for k in -h...h { s += x[wrapIndex(i + k, n)] }
            out[i] = s / Double(w)
        }
        return out
    }

    public static func circDist(_ a: Double, _ b: Double) -> Double {
        let d = ((a - b + 180).truncatingRemainder(dividingBy: 360) + 360)
            .truncatingRemainder(dividingBy: 360)
        return abs(d - 180)
    }

    public static func circLocal(_ a: Double, _ b: Double) -> Double {
        let d = ((a - b + 180).truncatingRemainder(dividingBy: 360) + 360)
            .truncatingRemainder(dividingBy: 360)
        return d - 180
    }

    public static func smoothstep(_ t: Double) -> Double {
        if t < 0 { return 0 }
        if t > 1 { return 1 }
        return t * t * (3 - 2 * t)
    }
}
