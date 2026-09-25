using System;
using System.Collections.Generic;

namespace Pappa
{
    /// <summary>
    /// Детектор ям (трещин) — повторение python/pappa/analysis/zones.py и портов:
    ///   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
    ///   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
    ///   зоны = участки, где индикатор > k, длиной не короче minZoneDeg.
    /// </summary>
    public static class Detector
    {
        public sealed class Options
        {
            public double WindowDeg { get; set; } = 1.0;
            public double WideDeg { get; set; } = 10.0;
            public double SmoothDeg { get; set; } = 2.0;
            public double K { get; set; } = 5.5;
            public double MinZoneDeg { get; set; } = 2.0;

            public Options() { }

            public Options(double windowDeg, double wideDeg, double smoothDeg, double k, double minZoneDeg)
            {
                WindowDeg = windowDeg;
                WideDeg = wideDeg;
                SmoothDeg = smoothDeg;
                K = k;
                MinZoneDeg = minZoneDeg;
            }
        }

        public static double[] BandIndicator(double[] angles, double[] radii, Options o = null)
        {
            o ??= new Options();
            int n = radii.Length;
            int wNarrow = Signal.WindowPoints(angles, o.WindowDeg);
            int wWide = Signal.WindowPoints(angles, o.WideDeg);
            int wSmooth = Signal.WindowPoints(angles, o.SmoothDeg);

            var narrow = Signal.MedianFilterWrap(radii, wNarrow);
            var wide = Signal.MedianFilterWrap(radii, wWide);
            var band = new double[n];
            for (int i = 0; i < n; i++) band[i] = Math.Abs(narrow[i] - wide[i]);

            var outp = Signal.SmoothWrap(band, wSmooth);
            double s = Signal.RobustSigma(outp);
            if (s > 1e-12)
            {
                for (int i = 0; i < n; i++) outp[i] /= s;
            }
            else
            {
                for (int i = 0; i < n; i++) outp[i] = 0.0;
            }
            return outp;
        }

        /// <summary>Непрерывные зоны по маске: элемент = [начало, конец] в градусах.</summary>
        public static List<double[]> MaskToZones(double[] angles, bool[] mask, Options o = null)
        {
            o ??= new Options();
            int n = angles.Length;
            var result = new List<double[]>();

            bool any = false;
            for (int i = 0; i < n; i++) if (mask[i]) { any = true; break; }
            if (!any) return result;

            var diffs = new double[Math.Max(0, n - 1)];
            for (int i = 0; i + 1 < n; i++) diffs[i] = angles[i + 1] - angles[i];
            double step = diffs.Length > 0 ? Signal.Median(diffs) : 1.0;

            var zones = new List<double[]>();
            int k = 0;
            while (k < n)
            {
                if (!mask[k]) { k++; continue; }
                int j = k;
                while (j + 1 < n && mask[j + 1]) j++;
                zones.Add(new[] { angles[k] - step / 2, angles[j] + step / 2 });
                k = j + 1;
            }

            // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
            if (zones.Count > 1 && mask[0] && mask[n - 1])
            {
                var first = zones[0];
                var last = zones[zones.Count - 1];
                var merged = new List<double[]> { new[] { last[0] - 360, first[1] } };
                for (int i = 1; i < zones.Count - 1; i++) merged.Add(zones[i]);
                zones = merged;
            }

            foreach (var z in zones)
            {
                if (z[1] - z[0] >= o.MinZoneDeg) result.Add(z);
            }
            return result;
        }

        public static List<double[]> Zones(double[] angles, double[] values, Options o = null)
        {
            o ??= new Options();
            var mask = new bool[values.Length];
            for (int i = 0; i < values.Length; i++) mask[i] = values[i] > o.K;
            return MaskToZones(angles, mask, o);
        }

        /// <summary>Центры ям (°) — середины найденных зон.</summary>
        public static double[] Pits(double[] angles, double[] radii, Options o = null)
        {
            o ??= new Options();
            var band = BandIndicator(angles, radii, o);
            var zs = Zones(angles, band, o);
            var pits = new double[zs.Count];
            for (int i = 0; i < zs.Count; i++) pits[i] = 0.5 * (zs[i][0] + zs[i][1]);
            return pits;
        }
    }
}
