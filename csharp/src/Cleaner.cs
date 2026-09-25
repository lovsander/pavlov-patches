using System;
using System.Collections.Generic;

namespace Pappa
{
    /// <summary>
    /// Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
    /// по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
    /// Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py) и порты C/C++/Go/JS/Java/Kotlin.
    /// </summary>
    public static class Cleaner
    {
        public sealed class Options
        {
            public double BaselineDeg { get; set; } = 1.0;
            public double IqrK { get; set; } = 3.0;
            public double MaxRemovedFrac { get; set; } = 0.5;
            public int MinPoints { get; set; } = 20;

            public Options() { }

            public Options(double baselineDeg, double iqrK)
            {
                BaselineDeg = baselineDeg;
                IqrK = iqrK;
            }
        }

        public sealed class Result
        {
            public bool[] Mask;
            public int NOutliers;
            public int Window;
        }

        public static Result CleanIqr(double[] angles, double[] radii, Options o = null)
        {
            o ??= new Options();
            int n = radii.Length;
            var mask = new bool[n];
            if (n < o.MinPoints) return new Result { Mask = mask, NOutliers = 0, Window = 0 };

            int w = Signal.WindowPoints(angles, o.BaselineDeg);
            var baseLine = Signal.MedianFilterWrap(radii, w);
            var res = new double[n];
            for (int i = 0; i < n; i++) res[i] = radii[i] - baseLine[i];

            double center = Signal.Median(res);
            double spread = Signal.Iqr(res);
            // Защита референса: при вырожденном остатке порог Тьюки упирается в 1.0 мм
            // (spec/conformance/README.md, «очиститель молча отключается»).
            double denom = spread > 1e-12 ? spread : 1.0;

            var sev = new double[n];
            int flagged = 0;
            for (int i = 0; i < n; i++)
            {
                sev[i] = Math.Abs(res[i] - center) / denom;
                mask[i] = sev[i] > o.IqrK;
                if (mask[i]) flagged++;
            }

            // Предохранитель: не выбрасываем больше maxRemovedFrac точек.
            int cap = (int)Math.Floor(o.MaxRemovedFrac * n);
            if (cap > 0 && cap < n && flagged > cap)
            {
                var kept = new List<double>(flagged);
                for (int i = 0; i < n; i++) if (mask[i]) kept.Add(sev[i]);
                kept.Sort();
                double level = kept[kept.Count - cap];
                flagged = 0;
                for (int i = 0; i < n; i++)
                {
                    mask[i] = mask[i] && sev[i] >= level;
                    if (mask[i]) flagged++;
                }
            }
            return new Result { Mask = mask, NOutliers = flagged, Window = w };
        }
    }
}
