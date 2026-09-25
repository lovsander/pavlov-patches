using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace Pappa
{
    /// <summary>
    /// Проверка порта по конформанс-векторам (spec/conformance/vectors).
    /// Допуски — те же, что у C++/Go/C/JS/Java/Kotlin: контур 1e-6 мм, коэффициенты
    /// max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
    /// </summary>
    public static class Conformance
    {
        public sealed class Result
        {
            public bool Ok;
            public string Detail;
            public List<string> Notes = new List<string>();
        }

        public sealed class Vector
        {
            public string File;
            public Dictionary<string, object> Data;
        }

        public static List<Vector> Load(string dir)
        {
            var files = Directory.GetFiles(dir, "*.json", SearchOption.TopDirectoryOnly);
            Array.Sort(files, StringComparer.Ordinal);
            var list = new List<Vector>(files.Length);
            foreach (var f in files)
            {
                list.Add(new Vector
                {
                    File = Path.GetFileName(f),
                    Data = Json.ParseObject(File.ReadAllText(f, Encoding.UTF8)),
                });
            }
            return list;
        }

        private static bool Near(double a, double b, double rel, double floor) =>
            Math.Abs(a - b) <= Math.Max(floor, rel * Math.Abs(b));

        private static double[] ToDoubles(List<object> a)
        {
            var d = new double[a.Count];
            for (int i = 0; i < a.Count; i++) d[i] = (double)a[i];
            return d;
        }

        public static Result Check(Dictionary<string, object> v)
        {
            string kind = Json.Str(v, "kind");
            if (kind == "model") return CheckModel(v);
            if (kind == "detector") return CheckDetector(v);
            return CheckCleaner(v);
        }

        private static Result CheckDetector(Dictionary<string, object> v)
        {
            var cfg = Json.Obj(Json.Get(v, "config"));
            var exp = Json.Obj(Json.Get(v, "expected"));
            var input = Json.Obj(Json.Get(v, "input"));
            var angles = Json.Doubles(input, "angles_deg");
            var radii = Json.Doubles(input, "radii_mm");
            var o = new Detector.Options(Json.Dbl(cfg, "window_deg"), Json.Dbl(cfg, "wide_deg"),
                Json.Dbl(cfg, "smooth_deg"), Json.Dbl(cfg, "k"), Json.Dbl(cfg, "min_zone_deg"));

            var band = Detector.BandIndicator(angles, radii, o);
            var zn = Detector.Zones(angles, band, o);
            var expZones = Json.Arr(Json.Get(exp, "zones_deg"));
            var expPits = Json.Doubles(exp, "pits_deg");
            var notes = new List<string>();

            bool ok = zn.Count == expZones.Count;
            if (!ok) notes.Add("зон " + zn.Count + " != " + expZones.Count);
            double dev = 0.0;
            for (int i = 0; i < expZones.Count && i < zn.Count; i++)
            {
                var e = ToDoubles(Json.Arr(expZones[i]));
                dev = Math.Max(dev, Math.Max(Math.Abs(zn[i][0] - e[0]), Math.Abs(zn[i][1] - e[1])));
            }
            if (zn.Count != expPits.Length)
            {
                ok = false;
                notes.Add("ям " + zn.Count + " != " + expPits.Length);
            }
            for (int i = 0; i < expPits.Length && i < zn.Count; i++)
            {
                double d = Math.Abs(0.5 * (zn[i][0] + zn[i][1]) - expPits[i]);
                dev = Math.Max(dev, d);
                if (d > 1e-6) ok = false;
            }
            string detail = "зон " + zn.Count + "/" + expZones.Count + ", ям " + zn.Count + "/"
                + expPits.Length + ", max|Δ| " + Fmt.E(dev) + "°";
            return new Result { Ok = ok, Detail = detail, Notes = notes };
        }

        private static Result CheckCleaner(Dictionary<string, object> v)
        {
            var cfg = Json.Obj(Json.Get(v, "config"));
            var exp = Json.Obj(Json.Get(v, "expected"));
            var input = Json.Obj(Json.Get(v, "input"));
            var tol = Json.Obj(Json.Get(v, "tolerance"));
            var angles = Json.Doubles(input, "angles_deg");
            var radii = Json.Doubles(input, "radii_mm");
            var o = new Cleaner.Options(Json.Dbl(cfg, "baseline_deg"), Json.Dbl(cfg, "iqr_k"));
            var r = Cleaner.CleanIqr(angles, radii, o);

            var refMask = new bool[radii.Length];
            foreach (int i in Json.Ints(exp, "mask_true_indices")) refMask[i] = true;
            int n = radii.Length;
            int extra = 0;
            int missing = 0;
            int got = 0;
            for (int i = 0; i < n; i++)
            {
                if (r.Mask[i])
                {
                    got++;
                    if (!refMask[i]) extra++;
                }
                else if (refMask[i]) missing++;
            }
            int tolN = Math.Max(1, (int)Math.Floor(Json.Dbl(tol, "frac", 0.02) * n));
            int want = Json.Int(exp, "n_outliers");
            bool ok = extra <= tolN && missing <= tolN && Math.Abs(got - want) <= tolN;
            string detail = "выбросов " + got + " (эталон " + want + "), лишних " + extra
                + ", пропущено " + missing;
            return new Result { Ok = ok, Detail = detail };
        }

        private static Result CheckModel(Dictionary<string, object> v)
        {
            var cfg = Json.Obj(Json.Get(v, "config"));
            var exp = Json.Obj(Json.Get(v, "expected"));
            var tol = Json.Obj(Json.Get(v, "tolerance"));
            var input = Json.Obj(Json.Get(v, "input"));
            var notes = new List<string>();
            bool ok = true;

            var opt = new Model.Options
            {
                NPatches = Json.Int(cfg, "n_patches"),
                PhaseDeg = Json.Dbl(cfg, "phase_deg"),
                DegMin = Json.Int(cfg, "deg_min"),
                DegMax = Json.Int(cfg, "deg_max"),
                OverlapTrain = Json.Dbl(cfg, "overlap_train"),
                OverlapUse = Json.Dbl(cfg, "overlap_use"),
                DegElbowTol = Json.Dbl(cfg, "deg_elbow_tol"),
                AmplitudeScale = Json.Dbl(cfg, "amplitude_scale", 180.0),
                CoordMode = Json.Str(cfg, "coord_mode"),
            };
            var pitsDeg = Json.Doubles(cfg, "pits_deg");
            var m = new Model(opt, pitsDeg);
            if (pitsDeg.Length > 0)
            {
                m.PitShape = new Model.PitShapeOptions
                {
                    SigmaDeg = Json.Dbl(cfg, "sigma_deg"),
                    CoreSigma = Json.Dbl(cfg, "pit_core_sigma"),
                    WindowSigma = Json.Dbl(cfg, "pit_window_sigma"),
                    PitMinAmp = Json.Dbl(cfg, "pit_min_amp"),
                    Tapering = Json.Bool(cfg, "tapering", true),
                };
            }
            m.Fit(Json.Doubles(input, "angles_deg"), Json.Doubles(input, "radii_mm"));

            var wantDeg = Json.Ints(exp, "degrees");
            var gotDeg = m.Degrees;
            bool degOk = wantDeg.Length == gotDeg.Length;
            if (degOk)
                for (int i = 0; i < wantDeg.Length; i++) if (wantDeg[i] != gotDeg[i]) { degOk = false; break; }
            if (!degOk)
            {
                ok = false;
                notes.Add("степени [" + string.Join(", ", gotDeg) + "] != ["
                    + string.Join(", ", wantDeg) + "]");
            }

            double rel = Json.Dbl(tol, "coefs_rel");
            double floor = Json.Dbl(tol, "coefs_abs_floor");
            var coefs = Json.Arr(Json.Get(exp, "coefs"));
            double maxC = 0.0;
            int badC = 0;
            for (int i = 0; i < coefs.Count; i++)
            {
                var refC = ToDoubles(Json.Arr(coefs[i]));
                var got = i < m.Patches.Count ? m.Patches[i].Coefs : new double[0];
                if (got.Length != refC.Length) { ok = false; badC++; continue; }
                for (int j = 0; j < refC.Length; j++)
                {
                    maxC = Math.Max(maxC, Math.Abs(got[j] - refC[j]));
                    if (!Near(got[j], refC[j], rel, floor)) { ok = false; badC++; }
                }
            }

            var pitTerms = Json.Arr(Json.Get(exp, "pit_terms"));
            double maxPit = 0.0;
            int badPit = 0;
            for (int i = 0; i < pitTerms.Count; i++)
            {
                var refTerm = Json.Obj(pitTerms[i]);
                var refDx = Json.Doubles(refTerm, "dx_deg");
                var refAmp = Json.Doubles(refTerm, "amp");
                var gotDx = i < m.Patches.Count ? m.Patches[i].PitOffsetsDeg : new double[0];
                var gotAmp = i < m.Patches.Count ? m.Patches[i].PitCoefs : new double[0];
                if (gotDx.Length != refDx.Length) { ok = false; badPit++; continue; }
                for (int j = 0; j < refDx.Length; j++)
                {
                    double da = Math.Abs(gotDx[j] - refDx[j]);
                    maxPit = Math.Max(maxPit, Math.Max(da, Math.Abs(gotAmp[j] - refAmp[j])));
                    if (da > 1e-9 || !Near(gotAmp[j], refAmp[j], rel, floor)) { ok = false; badPit++; }
                }
            }

            var curve = Json.Obj(Json.Get(exp, "curve"));
            var ca = Json.Doubles(curve, "angles_deg");
            var cr = Json.Doubles(curve, "radii_mm");
            var gotCurve = m.Eval(ca);
            double maxR = 0.0;
            for (int i = 0; i < cr.Length; i++) maxR = Math.Max(maxR, Math.Abs(gotCurve[i] - cr[i]));
            if (maxR > Json.Dbl(tol, "curve_mm")) ok = false;

            string detail = "степени " + (degOk ? "совпали" : "РАСХОДЯТСЯ")
                + ", коэфф. max|Δ| " + Fmt.E(maxC) + " (плохих " + badC + ")"
                + ", термины ям max|Δ| " + Fmt.E(maxPit) + " (плохих " + badPit + ")"
                + ", контур max|Δ| " + Fmt.E(maxR) + " мм";
            return new Result { Ok = ok, Detail = detail, Notes = notes };
        }
    }
}
