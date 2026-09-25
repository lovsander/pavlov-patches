using System;

namespace Pappa
{
    /// <summary>
    /// Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.linalg.lstsq /
    /// np.polyfit) + базис Чебышёва для быстрого выбора степени.
    /// </summary>
    public static class Linalg
    {
        /// <summary>Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится.</summary>
        public static double[] LstsqQR(double[][] aIn, double[] bIn)
        {
            int m = aIn.Length;
            if (m == 0) throw new ArgumentException("LstsqQR: пустая матрица");
            int n = aIn[0].Length;
            if (bIn.Length != m) throw new ArgumentException("LstsqQR: длины A и b не совпадают");
            if (m < n) throw new ArgumentException("LstsqQR: нужно m >= n");

            var a = new double[m][];
            for (int i = 0; i < m; i++) a[i] = (double[])aIn[i].Clone();
            var b = (double[])bIn.Clone();

            for (int k = 0; k < n; k++)
            {
                double norm = 0.0;
                for (int i = k; i < m; i++) norm += a[i][k] * a[i][k];
                norm = Math.Sqrt(norm);
                if (norm < 1e-300) continue;

                double alpha = a[k][k] > 0 ? -norm : norm;
                var v = new double[m];
                for (int i = k; i < m; i++) v[i] = a[i][k];
                v[k] -= alpha;
                double vnorm2 = 0.0;
                for (int i = k; i < m; i++) vnorm2 += v[i] * v[i];
                if (vnorm2 < 1e-300) continue;

                for (int j = k; j < n; j++)
                {
                    double s = 0.0;
                    for (int i = k; i < m; i++) s += v[i] * a[i][j];
                    double c = 2 * s / vnorm2;
                    for (int i = k; i < m; i++) a[i][j] -= c * v[i];
                }
                double sb = 0.0;
                for (int i = k; i < m; i++) sb += v[i] * b[i];
                double cb = 2 * sb / vnorm2;
                for (int i = k; i < m; i++) b[i] -= cb * v[i];
            }

            var x = new double[n];
            for (int i = n - 1; i >= 0; i--)
            {
                double s = b[i];
                for (int j = i + 1; j < n; j++) s -= a[i][j] * x[j];
                double d = a[i][i];
                if (Math.Abs(d) < 1e-300) throw new ArithmeticException("LstsqQR: вырожденная система");
                x[i] = s / d;
            }
            return x;
        }

        /// <summary>Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval).</summary>
        public static double Polyval(double[] coefs, double x)
        {
            double r = 0.0;
            foreach (double c in coefs) r = r * x + c;
            return r;
        }

        public static double[] Polyfit(double[] xs, double[] ys, int deg)
        {
            int m = xs.Length;
            int n = deg + 1;
            var a = new double[m][];
            for (int i = 0; i < m; i++)
            {
                a[i] = new double[n];
                double p = 1.0;
                for (int j = 0; j < n; j++)
                {
                    a[i][n - 1 - j] = p;
                    p *= xs[i];
                }
            }
            return LstsqQR(a, ys);
        }

        /// <summary>T_0(x)..T_degMax(x) — базис Чебышёва (x ∈ [-1, 1]).</summary>
        public static double[] ChebRow(double x, int degMax)
        {
            var t = new double[degMax + 1];
            t[0] = 1.0;
            if (degMax >= 1) t[1] = x;
            for (int k = 2; k <= degMax; k++) t[k] = 2 * x * t[k - 1] - t[k - 2];
            return t;
        }

        /// <summary>Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).</summary>
        public static double ChebSum(double[] c, int deg, double x)
        {
            double b1 = 0.0;
            double b2 = 0.0;
            for (int k = deg; k >= 1; k--)
            {
                double b0 = 2 * x * b1 - b2 + c[k];
                b2 = b1;
                b1 = b0;
            }
            return x * b1 - b2 + c[0];
        }
    }
}
