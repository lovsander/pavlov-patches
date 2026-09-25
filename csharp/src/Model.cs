using System;
using System.Collections.Generic;

namespace Pappa
{
    /// <summary>
    /// Модель PAPPA (C#): патчи с адаптивной степенью по нормированной координате,
    /// smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
    /// Совпадает с референсом Python и портами C/C++/Go/JS/Java/Kotlin: тот же базис,
    /// та же политика степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней —
    /// ОДНИМ накоплением Грама в базисе Чебышёва + RMSE по явным остаткам (Кленшоу).
    /// </summary>
    public sealed class Model
    {
        public sealed class Options
        {
            public int NPatches { get; set; } = 7;
            public double PhaseDeg { get; set; } = 24.75;
            public int DegMin { get; set; } = 4;
            public int DegMax { get; set; } = 14;
            public double OverlapTrain { get; set; } = 15.0;
            public double OverlapUse { get; set; } = 5.0;
            public double DegElbowTol { get; set; } = 0.05;
            public double AmplitudeScale { get; set; } = 180.0;
            public string CoordMode { get; set; } = "normalized";
        }

        public sealed class PitShapeOptions
        {
            public double SigmaDeg { get; set; } = 3.0;
            public double CoreSigma { get; set; } = 2.0;
            public double WindowSigma { get; set; } = 3.2;
            public double PitMinAmp { get; set; } = 3e-3;
            public bool Tapering { get; set; } = true;
        }

        public sealed class Metrics
        {
            public double AmplitudeMm;
            public double MeanRadiusMm;
            public double AmplitudeNorm;
            public double DegElbowTol;
            public double RmseSelectedMm;
            public double RmseBestMm;
            public int NTrainPoints;
        }

        public sealed class Stats
        {
            public double RmseMm;
            public double MaeMm;
            public double MaxErrMm;
            public double Correlation;
        }

        public sealed class Patch
        {
            public double CenterDeg;
            public int Degree;
            public int NPoints;
            public double[] Coefs;
            public double[] PitOffsetsDeg;
            public double[] PitCoefs;
            public Metrics Metrics;
            public Stats Stats;
        }

        private readonly Options opt;
        private double[] pitCenters = new double[0];
        private readonly List<Patch> patchList = new List<Patch>();
        private double[] centersArr = new double[0];
        private double halfSectorDeg;

        public bool IsFitted { get; private set; }

        public Model(Options options = null, double[] pitsDeg = null)
        {
            opt = options ?? new Options();
            SetPits(pitsDeg ?? new double[0]);
        }

        public Options OptionsRef => opt;

        public PitShapeOptions PitShape { get; set; } = new PitShapeOptions();

        public void SetPits(double[] centersDeg)
        {
            pitCenters = new double[centersDeg.Length];
            for (int i = 0; i < centersDeg.Length; i++)
                pitCenters[i] = ((centersDeg[i] % 360) + 360) % 360;
        }

        public double[] Pits => pitCenters;

        public List<Patch> Patches => patchList;

        public bool HasPits => pitCenters.Length > 0;

        public double HalfSector => halfSectorDeg;

        public double HalfTrain => halfSectorDeg + opt.OverlapTrain;

        public double HalfUse => halfSectorDeg + opt.OverlapUse;

        /// <summary>Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg).</summary>
        public double PitShapeDeg(double dDeg)
        {
            double d = Math.Abs(dDeg);
            double sigma = PitShape.SigmaDeg;
            double val0 = Math.Exp(-(d * d) / (2 * sigma * sigma));
            if (!PitShape.Tapering) return val0;
            double core = PitShape.CoreSigma * sigma;
            double edge = PitShape.WindowSigma * sigma;
            if (edge <= core) return val0;
            double t = (edge - d) / (edge - core);
            t = Math.Min(1.0, Math.Max(0.0, t));
            return val0 * t * t * (3 - 2 * t);
        }

        /// <summary>Смещения видимых ям в локальной системе патча (°).</summary>
        public double[] PitOffsets(double centerDeg, double halfWinDeg)
        {
            var outp = new List<double>(pitCenters.Length);
            foreach (double c in pitCenters)
            {
                double dx = Signal.CircLocal(c, centerDeg);
                if (Math.Abs(dx) <= halfWinDeg) outp.Add(dx);
            }
            return outp.ToArray();
        }

        public double Weight(double dDeg, double halfUseDeg)
        {
            if (dDeg <= halfSectorDeg) return 1.0;
            if (dDeg <= halfUseDeg)
                return Signal.Smoothstep(1 - (dDeg - halfSectorDeg) / (halfUseDeg - halfSectorDeg));
            return 0.0;
        }

        public int[] Degrees
        {
            get
            {
                var d = new int[patchList.Count];
                for (int i = 0; i < patchList.Count; i++) d[i] = patchList[i].Degree;
                return d;
            }
        }

        private sealed class DegreeChoice
        {
            public int Deg;
            public double RmseSelected;
            public double RmseBest;
            public int NTrain;
        }

        /// <summary>
        /// Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
        /// не хуже лучшей более чем на degElbowTol. Быстрая ветка (normalized) — одно
        /// накопление Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
        /// </summary>
        private DegreeChoice EstimateDegree(double[] xs, double[] ys)
        {
            int n = xs.Length;
            if (n < 5) return new DegreeChoice { Deg = opt.DegMin, RmseSelected = 0.0, RmseBest = 0.0, NTrain = n };

            var degs = new List<int>();
            var rmses = new List<double>();
            int bestDeg = opt.DegMin;
            double best = double.PositiveInfinity;

            if (opt.CoordMode == "raw")
            {
                // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
                for (int deg = opt.DegMin; deg <= opt.DegMax; deg += 2)
                {
                    var a = new double[n][];
                    for (int i = 0; i < n; i++)
                    {
                        a[i] = new double[deg + 1];
                        double p = 1.0;
                        for (int j = 0; j <= deg; j++)
                        {
                            a[i][deg - j] = p;
                            p *= xs[i];
                        }
                    }
                    var c = Linalg.LstsqQR(a, ys);
                    double sse = 0.0;
                    for (int i = 0; i < n; i++)
                    {
                        double e = Linalg.Polyval(c, xs[i]) - ys[i];
                        sse += e * e;
                    }
                    double r = Math.Sqrt(sse / n);
                    degs.Add(deg);
                    rmses.Add(r);
                    if (r < best) { best = r; bestDeg = deg; }
                }
            }
            else
            {
                int dmax = opt.DegMax;
                int p = dmax + 1;
                double yref = 0.0;
                foreach (double v in ys) yref += v;
                yref /= n;
                var gram = new double[p][];
                for (int r0 = 0; r0 < p; r0++) gram[r0] = new double[p];
                var rhs = new double[p];
                for (int i = 0; i < n; i++)
                {
                    var t = Linalg.ChebRow(xs[i], dmax);
                    double yc = ys[i] - yref;
                    for (int a0 = 0; a0 < p; a0++)
                    {
                        rhs[a0] += t[a0] * yc;
                        for (int c0 = a0; c0 < p; c0++) gram[a0][c0] += t[a0] * t[c0];
                    }
                }
                for (int a0 = 0; a0 < p; a0++)
                    for (int c0 = a0 + 1; c0 < p; c0++) gram[c0][a0] = gram[a0][c0];

                for (int deg = opt.DegMin; deg <= dmax; deg += 2)
                {
                    int nn = deg + 1;
                    var a = new double[nn][];
                    for (int r0 = 0; r0 < nn; r0++) a[r0] = (double[])gram[r0][..nn].Clone();
                    var b = (double[])rhs[..nn].Clone();
                    var c = Linalg.LstsqQR(a, b);
                    double sse = 0.0;
                    for (int i = 0; i < n; i++)
                    {
                        double e = Linalg.ChebSum(c, deg, xs[i]) - (ys[i] - yref);
                        sse += e * e;
                    }
                    double r = Math.Sqrt(sse / n);
                    degs.Add(deg);
                    rmses.Add(r);
                    if (r < best) { best = r; bestDeg = deg; }
                }
            }

            double limit = best * (1 + opt.DegElbowTol);
            int sel = bestDeg;
            double rmseSel = best;
            for (int k = 0; k < degs.Count; k++)     // степени по возрастанию
            {
                if (rmses[k] <= limit) { sel = degs[k]; rmseSel = rmses[k]; break; }
            }
            return new DegreeChoice { Deg = sel, RmseSelected = rmseSel, RmseBest = best, NTrain = n };
        }

        /// <summary>Точки обучающего окна патча (локальная координата: нормированная или сырая).</summary>
        private void WindowOf(double[] angles, double[] radii, double center,
                              out double[] xs, out double[] ys)
        {
            double half = HalfTrain;
            bool norm = opt.CoordMode != "raw";
            var xl = new List<double>();
            var yl = new List<double>();
            foreach (double shift in new[] { -360.0, 0.0, 360.0 })
            {
                for (int i = 0; i < angles.Length; i++)
                {
                    double dx = angles[i] + shift - center;
                    if (dx >= -half && dx <= half)
                    {
                        xl.Add(norm ? dx / half : dx);
                        yl.Add(radii[i]);
                    }
                }
            }
            xs = xl.ToArray();
            ys = yl.ToArray();
        }

        public Model Fit(double[] angles, double[] radii)
        {
            if (angles.Length != radii.Length) throw new ArgumentException("fit: длины не совпадают");
            if (angles.Length < 10) throw new ArgumentException("fit: слишком мало точек");

            double sector = 360.0 / opt.NPatches;
            halfSectorDeg = sector / 2;
            centersArr = new double[opt.NPatches];
            for (int i = 0; i < opt.NPatches; i++)
            {
                double c = (i * sector + halfSectorDeg + opt.PhaseDeg) % 360;
                if (c < 0) c += 360;
                centersArr[i] = c;
            }
            double halfTrain = HalfTrain;
            patchList.Clear();

            foreach (double c in centersArr)
            {
                WindowOf(angles, radii, c, out var xs, out var ys);
                int n = xs.Length;
                if (n < 5) continue;
                var est = EstimateDegree(xs, ys);
                int deg = est.Deg;

                var offs = PitOffsets(c, halfTrain);
                int ncol = deg + 1 + offs.Length;
                var a = new double[n][];
                for (int i = 0; i < n; i++)
                {
                    a[i] = new double[ncol];
                    double p = 1.0;
                    for (int k = deg; k >= 0; k--)
                    {
                        a[i][k] = p;
                        p *= xs[i];
                    }
                    for (int j = 0; j < offs.Length; j++)
                        a[i][deg + 1 + j] = PitShapeDeg(Math.Abs(xs[i] * halfTrain - offs[j]));
                }
                var coef = Linalg.LstsqQR(a, ys);
                var polyCoef = new double[deg + 1];
                Array.Copy(coef, polyCoef, deg + 1);

                // Отсечка ям, которые в окне патча «не видны» (pitMinAmp).
                var keptOffsets = new List<double>();
                var keptCoefs = new List<double>();
                for (int j = 0; j < offs.Length; j++)
                {
                    double maxAbs = 0.0;
                    for (int i = 0; i < n; i++)
                    {
                        double dDeg = Math.Abs(xs[i] * halfTrain - offs[j]);
                        maxAbs = Math.Max(maxAbs, Math.Abs(coef[deg + 1 + j] * PitShapeDeg(dDeg)));
                    }
                    if (maxAbs >= PitShape.PitMinAmp)
                    {
                        keptOffsets.Add(offs[j]);
                        keptCoefs.Add(coef[deg + 1 + j]);
                    }
                }
                patchList.Add(BuildPatch(c, deg, xs, ys, polyCoef,
                    keptOffsets.ToArray(), keptCoefs.ToArray(), est, angles, radii));
            }
            IsFitted = true;
            return this;
        }

        /// <summary>Метрики и статистика патча по его обучающему окну (полный базис).</summary>
        private Patch BuildPatch(double c, int deg, double[] xs, double[] ys, double[] polyCoef,
                                 double[] keptOffsets, double[] keptCoefs, DegreeChoice est,
                                 double[] angles, double[] radii)
        {
            int n = xs.Length;
            double sse = 0.0;
            double sae = 0.0;
            double mx = 0.0;
            var fitVals = new double[n];
            for (int i = 0; i < n; i++)
            {
                double v = Linalg.Polyval(polyCoef, xs[i]);
                for (int j = 0; j < keptOffsets.Length; j++)
                    v += keptCoefs[j] * PitShapeDeg(Math.Abs(xs[i] * HalfTrain - keptOffsets[j]));
                fitVals[i] = v;
                double e = v - ys[i];
                sse += e * e;
                sae += Math.Abs(e);
                mx = Math.Max(mx, Math.Abs(e));
            }
            double mf = 0.0;
            double my = 0.0;
            for (int i = 0; i < n; i++) { mf += fitVals[i]; my += ys[i]; }
            mf /= n;
            my /= n;
            double cov = 0.0;
            double vf = 0.0;
            double vy = 0.0;
            for (int i = 0; i < n; i++)
            {
                double df = fitVals[i] - mf;
                double dy = ys[i] - my;
                cov += df * dy;
                vf += df * df;
                vy += dy * dy;
            }
            double corr = (vf > 0 && vy > 0) ? cov / Math.Sqrt(vf * vy) : 0.0;

            // Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
            var sec = new List<double>();
            for (int i = 0; i < angles.Length; i++)
                if (Signal.CircDist(angles[i], c) <= halfSectorDeg) sec.Add(radii[i]);
            double amp = 0.0;
            double meanSec = 0.0;
            if (sec.Count >= 5)
            {
                var arr = sec.ToArray();
                amp = Signal.PercentileLinear(arr, 95.0) - Signal.PercentileLinear(arr, 5.0);
                foreach (double v in arr) meanSec += v;
                meanSec /= arr.Length;
            }

            return new Patch
            {
                CenterDeg = c,
                Degree = deg,
                NPoints = n,
                Coefs = polyCoef,
                PitOffsetsDeg = keptOffsets,
                PitCoefs = keptCoefs,
                Metrics = new Metrics
                {
                    AmplitudeMm = amp,
                    MeanRadiusMm = meanSec,
                    AmplitudeNorm = meanSec > 0 ? amp / meanSec : 0.0,
                    DegElbowTol = opt.DegElbowTol,
                    RmseSelectedMm = est.RmseSelected,
                    RmseBestMm = est.RmseBest,
                    NTrainPoints = n,
                },
                Stats = new Stats
                {
                    RmseMm = Math.Sqrt(sse / n),
                    MaeMm = sae / n,
                    MaxErrMm = mx,
                    Correlation = corr,
                },
            };
        }

        /// <summary>Контур: нормированное smoothstep-смешивание патчей (partition of unity).</summary>
        public double[] EvalPart(double[] angles, string part = "total")
        {
            if (!IsFitted) throw new InvalidOperationException("Сначала вызовите Fit()");
            double halfUse = HalfUse;
            double halfTrain = HalfTrain;
            var outp = new double[angles.Length];
            for (int k = 0; k < angles.Length; k++)
            {
                double a = angles[k];
                double sumWv = 0.0;
                double sumW = 0.0;
                foreach (var p in patchList)
                {
                    double w = Weight(Signal.CircDist(a, p.CenterDeg), halfUse);
                    if (w <= 0) continue;
                    double dx = Signal.CircLocal(a, p.CenterDeg);
                    double x = opt.CoordMode == "raw" ? dx : dx / halfTrain;
                    double v = 0.0;
                    if (part != "pit") v += Linalg.Polyval(p.Coefs, x);
                    if (part != "poly")
                    {
                        for (int j = 0; j < p.PitOffsetsDeg.Length; j++)
                            v += p.PitCoefs[j] * PitShapeDeg(Math.Abs(x * halfTrain - p.PitOffsetsDeg[j]));
                    }
                    sumWv += w * v;
                    sumW += w;
                }
                outp[k] = sumW > 0 ? sumWv / sumW : 0.0;
            }
            return outp;
        }

        public double[] Eval(double[] angles) => EvalPart(angles);
    }
}
