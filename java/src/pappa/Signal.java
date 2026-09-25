package pappa;

import java.util.Arrays;

/**
 * Сигнальные утилиты — поведение как у numpy и как в портах C/C++/Go/JS:
 * медиана (чётное n — среднее двух центральных), перцентиль с линейной
 * интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
 */
public final class Signal {

    private Signal() { }

    public static double[] sorted(double[] x) {
        double[] v = x.clone();
        Arrays.sort(v);
        return v;
    }

    public static double median(double[] x) {
        int n = x.length;
        if (n == 0) return 0;
        double[] v = sorted(x);
        return n % 2 == 1 ? v[n / 2] : 0.5 * (v[n / 2 - 1] + v[n / 2]);
    }

    public static double percentileLinear(double[] x, double q) {
        int n = x.length;
        if (n == 0) return 0;
        double[] v = sorted(x);
        double pos = (q / 100.0) * (n - 1);
        int lo = (int) Math.floor(pos);
        double frac = pos - lo;
        int hi = Math.min(lo + 1, n - 1);
        return v[lo] + frac * (v[hi] - v[lo]);
    }

    public static double iqr(double[] x) {
        if (x.length == 0) return 0;
        return percentileLinear(x, 75) - percentileLinear(x, 25);
    }

    public static double mad(double[] x) {
        if (x.length == 0) return 0;
        double m = median(x);
        double[] d = new double[x.length];
        for (int i = 0; i < x.length; i++) d[i] = Math.abs(x[i] - m);
        return median(d);
    }

    public static double robustSigma(double[] x) { return 1.4826 * mad(x); }

    /** Медианный шаг сетки по углам (медиана положительных разностей, иначе 1). */
    public static double angularStep(double[] angles) {
        if (angles.length < 2) return 1;
        double[] d = new double[angles.length - 1];
        int k = 0;
        for (int i = 1; i < angles.length; i++) {
            double s = angles[i] - angles[i - 1];
            if (s > 0) d[k++] = s;
        }
        if (k == 0) return 1;
        return median(Arrays.copyOf(d, k));
    }

    /** Ширина окна в точках: round(span/шаг) «банковским» округлением, нечётная. */
    public static int windowPoints(double[] angles, double spanDeg) {
        int n = angles.length;
        if (n < 3) return Math.max(1, n);
        // Math.rint = округление «половина к чётному», как Python round() и
        // math.RoundToEven в Go-порте (Math.round тут дал бы tie-up и разъехался)
        long w = (long) Math.rint(spanDeg / angularStep(angles));
        if (w % 2 == 0) w += 1;
        if (w < 3) w = 3;
        if (w > n) w = (n % 2 == 1) ? n : n - 1;
        return (int) Math.max(3, w);
    }

    private static int oddWindow(int window, int n) {
        int w = (window % 2 == 0) ? window + 1 : window;
        if (w < 3) w = 3;
        if (w > n) w = (n % 2 == 1) ? n : n - 1;
        return w;
    }

    public static int wrapIndex(int i, int n) { return ((i % n) + n) % n; }

    /** Медианный фильтр по кольцу (окно в точках). */
    public static double[] medianFilterWrap(double[] x, int window) {
        int n = x.length;
        int w = oddWindow(window, n);
        double[] out = new double[n];
        if (w < 3 || n < 3) {
            Arrays.fill(out, median(x));
            return out;
        }
        int h = (w - 1) / 2;
        double[] win = new double[w];
        for (int i = 0; i < n; i++) {
            for (int k = 0; k < w; k++) win[k] = x[wrapIndex(i - h + k, n)];
            out[i] = median(win);
        }
        return out;
    }

    /** Скользящее среднее по кольцу (окно в точках). */
    public static double[] smoothWrap(double[] x, int window) {
        int n = x.length;
        int w = oddWindow(window, n);
        if (w < 3 || n < 3) return x.clone();
        int h = (w - 1) / 2;
        double[] out = new double[n];
        for (int i = 0; i < n; i++) {
            double s = 0;
            for (int k = -h; k <= h; k++) s += x[wrapIndex(i + k, n)];
            out[i] = s / w;
        }
        return out;
    }

    public static double circDist(double a, double b) {
        double d = ((a - b + 180) % 360 + 360) % 360;
        return Math.abs(d - 180);
    }

    public static double circLocal(double a, double b) {
        double d = ((a - b + 180) % 360 + 360) % 360;
        return d - 180;
    }

    public static double smoothstep(double t) {
        if (t < 0) return 0;
        if (t > 1) return 1;
        return t * t * (3 - 2 * t);
    }
}
