using System;
using System.Collections.Generic;

namespace Pappa
{
    /// <summary>
    /// Сигнальные утилиты — поведение как у numpy и как в портах C/C++/Go/JS/Java/
    /// Kotlin: медиана (чётное n — среднее двух центральных), перцентиль с линейной
    /// интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
    /// </summary>
    public static class Signal
    {
        public static double Median(double[] x)
        {
            if (x == null || x.Length == 0) return 0.0;
            var v = (double[])x.Clone();
            Array.Sort(v);
            return MedianOfSorted(v);
        }

        /// <summary>Медиана УЖЕ отсортированного массива (без копии и без сортировки).</summary>
        public static double MedianOfSorted(double[] sorted)
        {
            int n = sorted.Length;
            if (n == 0) return 0.0;
            return (n % 2 == 1) ? sorted[n / 2] : 0.5 * (sorted[n / 2 - 1] + sorted[n / 2]);
        }

        /// <summary>Медиана, которая портит (сортирует) переданный scratch-массив.</summary>
        private static double MedianInPlace(double[] scratch)
        {
            Array.Sort(scratch);
            return MedianOfSorted(scratch);
        }

        /// <summary>Перцентиль с линейной интерполяцией (как np.percentile, method="linear").</summary>
        public static double PercentileLinear(double[] x, double q)
        {
            int n = x.Length;
            if (n == 0) return 0.0;
            var v = (double[])x.Clone();
            Array.Sort(v);
            double pos = (q / 100.0) * (n - 1);
            int lo = (int)Math.Floor(pos);
            double frac = pos - lo;
            int hi = Math.Min(lo + 1, n - 1);
            return v[lo] + frac * (v[hi] - v[lo]);
        }

        public static double Iqr(double[] x) =>
            x.Length == 0 ? 0.0 : PercentileLinear(x, 75.0) - PercentileLinear(x, 25.0);

        public static double Mad(double[] x)
        {
            if (x == null || x.Length == 0) return 0.0;
            double m = Median(x);
            var dev = new double[x.Length];
            for (int i = 0; i < x.Length; i++) dev[i] = Math.Abs(x[i] - m);
            return Median(dev);
        }

        public static double RobustSigma(double[] x) => 1.4826 * Mad(x);

        /// <summary>Медианный шаг сетки по углам (медиана положительных разностей, иначе 1).</summary>
        public static double AngularStep(double[] angles)
        {
            if (angles.Length < 2) return 1.0;
            var d = new List<double>(angles.Length - 1);
            for (int i = 1; i < angles.Length; i++)
            {
                double s = angles[i] - angles[i - 1];
                if (s > 0) d.Add(s);
            }
            return d.Count == 0 ? 1.0 : Median(d.ToArray());
        }

        /// <summary>
        /// Ширина окна в точках: round(span/шаг) «половина к ЧЁТНОМУ», нечётная.
        /// Ловушка переноса №1: Math.Round без MidpointRounding округляет половину
        /// ОТ НУЛЯ (в Python round(2.5) == 2) — окна разъехались бы.
        /// </summary>
        public static int WindowPoints(double[] angles, double spanDeg)
        {
            int n = angles.Length;
            if (n < 3) return Math.Max(1, n);
            long w = (long)Math.Round(spanDeg / AngularStep(angles), MidpointRounding.ToEven);
            if (w % 2 == 0) w += 1;
            if (w < 3) w = 3;
            if (w > n) w = (n % 2 == 1) ? n : n - 1;
            return (int)Math.Max(3, w);
        }

        private static int OddWindow(int window, int n)
        {
            int w = (window % 2 == 0) ? window + 1 : window;
            if (w < 3) w = 3;
            if (w > n) w = (n % 2 == 1) ? n : n - 1;
            return w;
        }

        /// <summary>Индекс по кольцу. Ловушка №2: в C# (-1 % n) == -1, а не n-1.</summary>
        public static int WrapIndex(int i, int n) => ((i % n) + n) % n;

        /// <summary>Медианный фильтр по кольцу (окно в точках).</summary>
        public static double[] MedianFilterWrap(double[] x, int window)
        {
            int n = x.Length;
            int w = OddWindow(window, n);
            var outp = new double[n];
            if (w < 3 || n < 3)
            {
                double m = Median(x);
                for (int i = 0; i < n; i++) outp[i] = m;
                return outp;
            }
            int h = (w - 1) / 2;
            var win = new double[w];
            for (int i = 0; i < n; i++)
            {
                for (int k = 0; k < w; k++) win[k] = x[WrapIndex(i - h + k, n)];
                outp[i] = MedianInPlace(win);
            }
            return outp;
        }

        /// <summary>Скользящее среднее по кольцу (окно в точках).</summary>
        public static double[] SmoothWrap(double[] x, int window)
        {
            int n = x.Length;
            int w = OddWindow(window, n);
            if (w < 3 || n < 3) return (double[])x.Clone();
            int h = (w - 1) / 2;
            var outp = new double[n];
            for (int i = 0; i < n; i++)
            {
                double s = 0.0;
                for (int k = -h; k <= h; k++) s += x[WrapIndex(i + k, n)];
                outp[i] = s / w;
            }
            return outp;
        }

        public static double CircDist(double a, double b)
        {
            double d = ((a - b + 180) % 360 + 360) % 360;
            return Math.Abs(d - 180);
        }

        public static double CircLocal(double a, double b)
        {
            double d = ((a - b + 180) % 360 + 360) % 360;
            return d - 180;
        }

        public static double Smoothstep(double t)
        {
            if (t < 0) return 0.0;
            if (t > 1) return 1.0;
            return t * t * (3 - 2 * t);
        }
    }
}
