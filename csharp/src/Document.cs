using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

namespace Pappa
{
    /// <summary>
    /// Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin:
    ///   &lt;out_dir&gt;/sample.json              манифест (format pappa-sample v1.0)
    ///   &lt;out_dir&gt;/sections/NN.pappa.json   документ сечения (pappa v2.0)
    /// Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
    /// сравниваются численно (python/studies/verify_port.py).
    /// </summary>
    public static class Document
    {
        public const string PortVersion = "0.1.0";

        public sealed class SampleOptions
        {
            public string Name;
            public string InputCsv;
            public bool Pits;
            public string Description;
            public Cleaner.Options Cleaner = new Cleaner.Options();
            public Detector.Options Detector = new Detector.Options();
        }

        private static string IsoUtcNow() =>
            DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", Fmt.Inv);

        /// <summary>Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++.</summary>
        private sealed class W
        {
            public readonly StringBuilder Sb = new StringBuilder();
            private int depth;

            private string Ind() => new string(' ', 2 * Math.Max(0, depth));

            /// <summary>Отступ текущего уровня — как Ind() у C++-писателя.</summary>
            public string Indent() => Ind();

            public void ObjStart() { Sb.Append('{'); depth++; Sb.Append('\n').Append(Ind()); }
            public void ObjEnd() { depth--; Sb.Append('\n').Append(Ind()).Append('}'); }
            public void ArrStart() { Sb.Append('['); depth++; Sb.Append('\n').Append(Ind()); }
            public void ArrEnd() { depth--; Sb.Append('\n').Append(Ind()).Append(']'); }
            public void Comma() { Sb.Append(',').Append('\n').Append(Ind()); }
            public void Key(string k) { Sb.Append(Ind()).Append('"').Append(k).Append("\": "); }
            public void Str(string s) { Sb.Append('"').Append(Json.Escape(s)).Append('"'); }
            public void Num(double v) { Sb.Append(Json.Num(v)); }
            public void Raw(string s) { Sb.Append(s); }
            public void Kv(string k, string v) { Key(k); Str(v); }
            public void Kv(string k, double v) { Key(k); Num(v); }
            public void Kv(string k, int v) { Key(k); Sb.Append(v.ToString(Fmt.Inv)); }
            // ВАЖНО: Sb.Append(bool) напечатал бы "True"/"False" — в JSON нужен нижний регистр.
            public void Kv(string k, bool v) { Key(k); Sb.Append(Fmt.Bool(v)); }
        }

        private static void WritePatches(W w, Model m)
        {
            w.Key("patches");
            w.ArrStart();
            for (int i = 0; i < m.Patches.Count; i++)
            {
                var p = m.Patches[i];
                w.Sb.Append(i > 0 ? ",\n" + w.Indent() : "\n" + w.Indent());
                w.ObjStart();
                w.Kv("center_deg", p.CenterDeg); w.Comma();
                w.Kv("degree", p.Degree); w.Comma();
                w.Kv("n_points", p.NPoints); w.Comma();
                w.Key("coefs");
                w.ArrStart();
                for (int j = 0; j < p.Coefs.Length; j++)
                {
                    if (j > 0) w.Raw(", ");
                    w.Num(p.Coefs[j]);
                }
                w.ArrEnd();
                w.Comma();

                w.Key("metrics");
                w.ObjStart();
                w.Kv("amplitude_mm", p.Metrics.AmplitudeMm); w.Comma();
                w.Kv("mean_radius_mm", p.Metrics.MeanRadiusMm); w.Comma();
                w.Kv("amplitude_norm", p.Metrics.AmplitudeNorm); w.Comma();
                w.Kv("deg_elbow_tol", p.Metrics.DegElbowTol); w.Comma();
                w.Kv("rmse_selected_mm", p.Metrics.RmseSelectedMm); w.Comma();
                w.Kv("rmse_best_mm", p.Metrics.RmseBestMm); w.Comma();
                w.Kv("n_train_points", p.Metrics.NTrainPoints);
                w.ObjEnd();
                w.Comma();

                w.Key("stats");
                w.ObjStart();
                w.Kv("rmse_mm", p.Stats.RmseMm); w.Comma();
                w.Kv("mae_mm", p.Stats.MaeMm); w.Comma();
                w.Kv("max_err_mm", p.Stats.MaxErrMm); w.Comma();
                w.Kv("correlation", p.Stats.Correlation);
                w.ObjEnd();

                // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
                // (включая пустой список): так ждёт загрузчик Python.
                if (m.HasPits)
                {
                    w.Comma();
                    w.Key("pit_terms");
                    w.ArrStart();
                    for (int j = 0; j < p.PitOffsetsDeg.Length; j++)
                    {
                        if (j > 0) w.Raw(", ");
                        w.ObjStart();
                        w.Kv("dx_deg", p.PitOffsetsDeg[j]); w.Comma();
                        w.Kv("amp", p.PitCoefs[j]);
                        w.ObjEnd();
                    }
                    w.ArrEnd();
                }
                w.ObjEnd();
            }
            w.Raw("\n");
            w.Raw(w.Indent());
            w.ArrEnd();
        }

        public static string SaveSectionDocument(string path, Csv.SectionModel section)
        {
            var m = section.Model;
            if (!m.IsFitted) throw new InvalidOperationException("SaveSectionDocument: модель не обучена");
            var w = new W();
            w.ObjStart();
            w.Kv("format", "pappa"); w.Comma();
            w.Kv("version", "2.0"); w.Comma();
            w.Kv("method", m.HasPits ? "PitPatchApproximator" : "PatchApproximator"); w.Comma();
            w.Kv("created", IsoUtcNow()); w.Comma();

            w.Key("software");
            w.ObjStart();
            w.Kv("language", "csharp"); w.Comma();
            w.Kv("pappa_version", PortVersion);
            w.ObjEnd();
            w.Comma();

            w.Key("meta");
            w.ObjStart();
            w.Kv("section_id", section.SectionId); w.Comma();
            w.Kv("height_mm", section.HeightMm); w.Comma();
            w.Kv("source", "csv"); w.Comma();
            w.Kv("description", section.Description);
            w.ObjEnd();
            w.Comma();

            w.Key("global");
            w.ObjStart();
            w.Key("units");
            w.ObjStart();
            w.Kv("angle", "degree"); w.Comma();
            w.Kv("length", "mm");
            w.ObjEnd();
            w.Comma();
            var opt = m.OptionsRef;
            w.Kv("n_patches", opt.NPatches); w.Comma();
            w.Kv("half_sector_deg", m.HalfSector); w.Comma();
            w.Kv("phase_deg", opt.PhaseDeg); w.Comma();
            w.Kv("half_train_deg", m.HalfTrain); w.Comma();
            w.Kv("half_use_deg", m.HalfUse); w.Comma();
            w.Kv("overlap_train_deg", opt.OverlapTrain); w.Comma();
            w.Kv("overlap_use_deg", opt.OverlapUse); w.Comma();
            w.Kv("deg_min", opt.DegMin); w.Comma();
            w.Kv("deg_max", opt.DegMax); w.Comma();
            w.Kv("coord_mode", opt.CoordMode); w.Comma();
            w.Kv("deg_elbow_tol", opt.DegElbowTol); w.Comma();
            w.Kv("amplitude_scale", opt.AmplitudeScale);
            if (m.HasPits)
            {
                var ps = m.PitShape;
                w.Comma();
                w.Key("pit");
                w.ObjStart();
                w.Kv("sigma_deg", ps.SigmaDeg); w.Comma();
                w.Kv("core_sigma", ps.CoreSigma); w.Comma();
                w.Kv("window_sigma", ps.WindowSigma); w.Comma();
                w.Kv("pit_min_amp", ps.PitMinAmp); w.Comma();
                w.Kv("tapering", ps.Tapering); w.Comma();
                w.Key("centers_deg");
                w.ArrStart();
                for (int i = 0; i < m.Pits.Length; i++)
                {
                    if (i > 0) w.Raw(", ");
                    w.Num(m.Pits[i]);
                }
                w.ArrEnd();
                w.ObjEnd();
            }
            w.ObjEnd();
            w.Comma();

            WritePatches(w, m);
            w.Comma();

            w.Key("statistics");
            w.ObjStart();
            w.Kv("n_points_total", section.NPointsTotal); w.Comma();
            w.Kv("n_outliers_removed", section.NOutliers); w.Comma();
            w.Kv("fit_time_ms", section.FitTimeMs);
            w.ObjEnd();

            w.ObjEnd();
            File.WriteAllText(path, w.Sb.ToString() + "\n", new UTF8Encoding(false));
            return path;
        }

        public static string SaveSample(string outDir, string name, List<Csv.SectionModel> sections,
                                        SampleOptions o)
        {
            var root = Path.GetFullPath(outDir);
            Directory.CreateDirectory(Path.Combine(root, "sections"));

            var ordered = new List<Csv.SectionModel>(sections.OrderBy(s => s.SectionId));
            var first = ordered.Count > 0 ? ordered[0].Model : null;

            var w = new W();
            w.ObjStart();
            w.Kv("format", "pappa-sample"); w.Comma();
            w.Kv("version", "1.0"); w.Comma();
            w.Kv("name", name); w.Comma();
            w.Kv("created", IsoUtcNow()); w.Comma();

            w.Key("units");
            w.ObjStart();
            w.Kv("angle", "degree"); w.Comma();
            w.Kv("length", "mm");
            w.ObjEnd();
            w.Comma();

            w.Key("meta");
            w.ObjStart();
            w.Kv("description", o.Description);
            w.ObjEnd();
            w.Comma();

            if (!string.IsNullOrEmpty(o.InputCsv))
            {
                w.Key("input");
                w.ObjStart();
                w.Kv("csv", o.InputCsv);
                w.ObjEnd();
                w.Comma();
            }

            w.Key("config");
            w.ObjStart();
            var opt = first?.OptionsRef;
            w.Kv("n_patches", opt?.NPatches ?? 0); w.Comma();
            w.Kv("phase_deg", opt?.PhaseDeg ?? 0.0); w.Comma();
            w.Kv("deg_min", opt?.DegMin ?? 0); w.Comma();
            w.Kv("deg_max", opt?.DegMax ?? 0); w.Comma();
            w.Kv("overlap_train", opt?.OverlapTrain ?? 0.0); w.Comma();
            w.Kv("overlap_use", opt?.OverlapUse ?? 0.0); w.Comma();
            w.Kv("deg_elbow_tol", opt?.DegElbowTol ?? 0.0); w.Comma();
            w.Key("cleaner");
            w.Raw("{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", "
                + "\"baseline_deg\": " + Json.Num(o.Cleaner.BaselineDeg)
                + ", \"iqr_k\": " + Json.Num(o.Cleaner.IqrK) + "}}");
            w.Comma();
            w.Kv("pits", o.Pits);
            if (o.Pits && first != null)
            {
                var ps = first.PitShape;
                w.Comma();
                w.Kv("sigma_deg", ps.SigmaDeg); w.Comma();
                w.Kv("pit_core_sigma", ps.CoreSigma); w.Comma();
                w.Kv("pit_window_sigma", ps.WindowSigma); w.Comma();
                w.Kv("pit_min_amp", ps.PitMinAmp); w.Comma();
                w.Kv("tapering", ps.Tapering);
            }
            w.Comma();
            w.Key("detector");
            w.Raw("null");
            w.ObjEnd();
            w.Comma();

            w.Key("sections");
            w.ArrStart();
            for (int i = 0; i < ordered.Count; i++)
            {
                var s = ordered[i];
                string file = "sections/" + i.ToString("D2", Fmt.Inv) + ".pappa.json";
                SaveSectionDocument(Path.Combine(root, file), s);
                w.Raw(i > 0 ? ",\n" + w.Indent() : "\n" + w.Indent());
                w.ObjStart();
                w.Kv("index", i); w.Comma();
                w.Kv("section_id", s.SectionId); w.Comma();
                w.Kv("height_mm", s.HeightMm); w.Comma();
                w.Kv("file", file); w.Comma();
                w.Kv("n_points", s.NPointsTotal); w.Comma();
                w.Kv("n_outliers", s.NOutliers);
                w.ObjEnd();
            }
            w.Raw("\n");
            w.Raw(w.Indent());
            w.ArrEnd();

            w.ObjEnd();
            File.WriteAllText(Path.Combine(root, "sample.json"), w.Sb.ToString() + "\n",
                new UTF8Encoding(false));
            return root;
        }
    }
}
