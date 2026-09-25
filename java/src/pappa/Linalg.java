package pappa;

/**
 * Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
 * np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени.
 */
public final class Linalg {

    private Linalg() { }

    /**
     * Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера.
     * Входные массивы НЕ портятся: работаем по копиям.
     */
    public static double[] lstsqQR(double[][] aIn, double[] bIn) {
        int m = aIn.length;
        if (m == 0) throw new IllegalArgumentException("lstsqQR: пустая матрица");
        int n = aIn[0].length;
        if (bIn.length != m) throw new IllegalArgumentException("lstsqQR: длины A и b не совпадают");
        if (m < n) throw new IllegalArgumentException("lstsqQR: нужно m >= n");

        double[][] a = new double[m][n];
        for (int i = 0; i < m; i++) a[i] = aIn[i].clone();
        double[] b = bIn.clone();

        for (int k = 0; k < n; k++) {
            double norm = 0;
            for (int i = k; i < m; i++) norm += a[i][k] * a[i][k];
            norm = Math.sqrt(norm);
            if (norm < 1e-300) continue;

            double alpha = a[k][k] > 0 ? -norm : norm;
            double[] v = new double[m];
            for (int i = k; i < m; i++) v[i] = a[i][k];
            v[k] -= alpha;
            double vnorm2 = 0;
            for (int i = k; i < m; i++) vnorm2 += v[i] * v[i];
            if (vnorm2 < 1e-300) continue;

            for (int j = k; j < n; j++) {
                double s = 0;
                for (int i = k; i < m; i++) s += v[i] * a[i][j];
                double c = 2 * s / vnorm2;
                for (int i = k; i < m; i++) a[i][j] -= c * v[i];
            }
            double sb = 0;
            for (int i = k; i < m; i++) sb += v[i] * b[i];
            double cb = 2 * sb / vnorm2;
            for (int i = k; i < m; i++) b[i] -= cb * v[i];
        }

        double[] x = new double[n];
        for (int i = n - 1; i >= 0; i--) {
            double s = b[i];
            for (int j = i + 1; j < n; j++) s -= a[i][j] * x[j];
            double d = a[i][i];
            if (Math.abs(d) < 1e-300) throw new IllegalStateException("lstsqQR: вырожденная система");
            x[i] = s / d;
        }
        return x;
    }

    /** Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval). */
    public static double polyval(double[] coefs, double x) {
        double r = 0;
        for (double c : coefs) r = r * x + c;
        return r;
    }

    public static double[] polyfit(double[] xs, double[] ys, int deg) {
        int m = xs.length;
        int n = deg + 1;
        double[][] a = new double[m][n];
        for (int i = 0; i < m; i++) {
            double p = 1;
            for (int j = 0; j < n; j++) {
                a[i][n - 1 - j] = p;
                p *= xs[i];
            }
        }
        return lstsqQR(a, ys);
    }

    /** T_0(x)..T_degMax(x) — базис Чебышёва (x ∈ [-1, 1]). */
    public static double[] chebRow(double x, int degMax) {
        double[] t = new double[degMax + 1];
        t[0] = 1;
        if (degMax >= 1) t[1] = x;
        for (int k = 2; k <= degMax; k++) t[k] = 2 * x * t[k - 1] - t[k - 2];
        return t;
    }

    /** Σ c_k·T_k(x) по схеме Кленшоу (устойчиво). */
    public static double chebSum(double[] c, int deg, double x) {
        double b1 = 0;
        double b2 = 0;
        for (int k = deg; k >= 1; k--) {
            double b0 = 2 * x * b1 - b2 + c[k];
            b2 = b1;
            b1 = b0;
        }
        return x * b1 - b2 + c[0];
    }
}
