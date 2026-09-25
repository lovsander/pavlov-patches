import Foundation

/// Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
/// np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени.
public enum Linalg {

    public struct PappaError: Error, CustomStringConvertible {
        public let message: String
        public init(_ m: String) { message = m }
        public var description: String { message }
    }

    /// Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится.
    public static func lstsqQR(_ aIn: [[Double]], _ bIn: [Double]) throws -> [Double] {
        let m = aIn.count
        if m == 0 { throw PappaError("lstsq: пустая матрица") }
        let n = aIn[0].count
        if bIn.count != m { throw PappaError("lstsq: длины A и b не совпадают") }
        if m < n { throw PappaError("lstsq: нужно m >= n") }

        var a = aIn
        var b = bIn

        for k in 0..<n {
            var norm = 0.0
            for i in k..<m { norm += a[i][k] * a[i][k] }
            norm = sqrt(norm)
            if norm < 1e-300 { continue }

            let alpha = a[k][k] > 0 ? -norm : norm
            var v = [Double](repeating: 0, count: m)
            for i in k..<m { v[i] = a[i][k] }
            v[k] -= alpha
            var vnorm2 = 0.0
            for i in k..<m { vnorm2 += v[i] * v[i] }
            if vnorm2 < 1e-300 { continue }

            for j in k..<n {
                var s = 0.0
                for i in k..<m { s += v[i] * a[i][j] }
                let c = 2 * s / vnorm2
                for i in k..<m { a[i][j] -= c * v[i] }
            }
            var sb = 0.0
            for i in k..<m { sb += v[i] * b[i] }
            let cb = 2 * sb / vnorm2
            for i in k..<m { b[i] -= cb * v[i] }
        }

        var x = [Double](repeating: 0, count: n)
        for i in stride(from: n - 1, through: 0, by: -1) {
            var s = b[i]
            if i + 1 < n {
                for j in (i + 1)..<n { s -= a[i][j] * x[j] }
            }
            let d = a[i][i]
            if abs(d) < 1e-300 { throw PappaError("lstsq: вырожденная система") }
            x[i] = s / d
        }
        return x
    }

    /// Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval).
    public static func polyval(_ coefs: [Double], _ x: Double) -> Double {
        var r = 0.0
        for c in coefs { r = r * x + c }
        return r
    }

    public static func polyfit(_ xs: [Double], _ ys: [Double], _ deg: Int) throws -> [Double] {
        let m = xs.count
        let n = deg + 1
        var a = [[Double]](repeating: [Double](repeating: 0, count: n), count: m)
        for i in 0..<m {
            var p = 1.0
            for j in 0..<n {
                a[i][n - 1 - j] = p
                p *= xs[i]
            }
        }
        return try lstsqQR(a, ys)
    }

    /// T_0(x)..T_degMax(x) — базис Чебышёва (x ∈ [-1, 1]).
    public static func chebRow(_ x: Double, _ degMax: Int) -> [Double] {
        var t = [Double](repeating: 0, count: degMax + 1)
        t[0] = 1
        if degMax >= 1 { t[1] = x }
        if degMax >= 2 {
            for k in 2...degMax { t[k] = 2 * x * t[k - 1] - t[k - 2] }
        }
        return t
    }

    /// Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
    public static func chebSum(_ c: [Double], _ deg: Int, _ x: Double) -> Double {
        var b1 = 0.0
        var b2 = 0.0
        if deg >= 1 {
            for k in stride(from: deg, through: 1, by: -1) {
                let b0 = 2 * x * b1 - b2 + c[k]
                b2 = b1
                b1 = b0
            }
        }
        return x * b1 - b2 + c[0]
    }
}
