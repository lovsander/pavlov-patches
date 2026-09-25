using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace Pappa
{
    /// <summary>Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go).</summary>
    public static class Csv
    {
        public sealed class Row
        {
            public int SectionId;
            public double HeightMm;
            public double AngleDeg;
            public double RadiusMm;
        }

        /// <summary>Сечение + обученная модель + метаданные для документа.</summary>
        public sealed class SectionModel
        {
            public int SectionId;
            public double HeightMm;
            public Model Model;
            public int NPointsTotal;
            public int NOutliers;
            public double FitTimeMs;
            public string Description;
            public double[] Pits;
            public int NUsed;
        }

        /// <summary>Параметры посекционного расчёта: значения по умолчанию — как в референсе.</summary>
        public sealed class PipelineOptions
        {
            public Model.Options ModelOptions { get; set; } = new Model.Options();
            public Cleaner.Options Cleaner { get; set; } = new Cleaner.Options();
            public Detector.Options Detector { get; set; } = new Detector.Options();
            public bool Pits { get; set; } = true;
            public bool Verbose { get; set; } = true;
        }

        /// <summary>Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок).</summary>
        public static List<Row> Load(string path)
        {
            var lines = new List<string>();
            foreach (var l in File.ReadAllLines(path, Encoding.UTF8))
                if (l.Trim().Length > 0) lines.Add(l);
            if (lines.Count == 0) throw new InvalidDataException("пустой CSV: " + path);

            var head = lines[0].Split(',');
            var index = new Dictionary<string, int>();
            for (int i = 0; i < head.Length; i++) index[head[i].Trim()] = i;
            foreach (string need in new[] { "section_id", "height_mm", "angle_deg", "radius_mm" })
                if (!index.ContainsKey(need)) throw new InvalidDataException("в CSV нет колонки \"" + need + "\"");

            int iSec = index["section_id"];
            int ih = index["height_mm"];
            int ia = index["angle_deg"];
            int ir = index["radius_mm"];
            int needCol = Math.Max(Math.Max(iSec, ih), Math.Max(ia, ir));

            var rows = new List<Row>(lines.Count - 1);
            for (int k = 1; k < lines.Count; k++)
            {
                var f = lines[k].Split(',');
                if (f.Length <= needCol) continue;
                rows.Add(new Row
                {
                    SectionId = int.Parse(f[iSec].Trim(), NumberStyles.Integer, Fmt.Inv),
                    HeightMm = double.Parse(f[ih].Trim(), NumberStyles.Float, Fmt.Inv),
                    AngleDeg = double.Parse(f[ia].Trim(), NumberStyles.Float, Fmt.Inv),
                    RadiusMm = double.Parse(f[ir].Trim(), NumberStyles.Float, Fmt.Inv),
                });
            }
            if (rows.Count == 0) throw new InvalidDataException("в CSV нет строк с данными");
            return rows;
        }

        /// <summary>Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение.</summary>
        public static List<SectionModel> ProcessSections(List<Row> rows, PipelineOptions opt = null)
        {
            opt ??= new PipelineOptions();

            var bySection = new Dictionary<int, List<Row>>();
            foreach (var r in rows)
            {
                if (!bySection.TryGetValue(r.SectionId, out var list))
                {
                    list = new List<Row>();
                    bySection[r.SectionId] = list;
                }
                list.Add(r);
            }

            var ids = new List<int>(bySection.Keys);
            ids.Sort();

            var outp = new List<SectionModel>(ids.Count);
            foreach (int sid in ids)
            {
                // Сортировка по углу обязана быть УСТОЙЧИВОЙ (List.Sort в C# неустойчив):
                // при равных углах сохраняется порядок файла, а от него зависит height_mm
                // «первой» строки. OrderBy документирован как stable sort.
                var group = new List<Row>(bySection[sid].OrderBy(r => r.AngleDeg));

                int n = group.Count;
                var angles = new double[n];
                var radii = new double[n];
                for (int i = 0; i < n; i++)
                {
                    angles[i] = group[i].AngleDeg;
                    radii[i] = group[i].RadiusMm;
                }

                var cl = Cleaner.CleanIqr(angles, radii, opt.Cleaner);
                var aClean = new List<double>(n);
                var rClean = new List<double>(n);
                for (int i = 0; i < n; i++)
                {
                    if (cl.Mask[i]) continue;
                    aClean.Add(angles[i]);
                    rClean.Add(radii[i]);
                }
                var ang = aClean.ToArray();
                var rad = rClean.ToArray();

                var pits = opt.Pits ? Detector.Pits(ang, rad, opt.Detector) : new double[0];
                var model = new Model(opt.ModelOptions, pits);

                var sw = Stopwatch.StartNew();
                model.Fit(ang, rad);
                sw.Stop();
                double fitMs = sw.Elapsed.TotalMilliseconds;

                double height = group.Count > 0 ? group[0].HeightMm : 0.0;
                var sec = new SectionModel
                {
                    SectionId = sid,
                    HeightMm = height,
                    Model = model,
                    NPointsTotal = n,
                    NOutliers = cl.NOutliers,
                    FitTimeMs = fitMs,
                    Description = "сечение " + sid + ", h=" + F0(height) + " мм",
                    Pits = pits,
                    NUsed = ang.Length,
                };
                if (opt.Verbose)
                {
                    Console.WriteLine("  секция " + sid + " (h=" + F0(height) + " мм): точек " + n
                        + ", выброшено " + cl.NOutliers + ", ям найдено " + pits.Length
                        + ", степени [" + Join(model.Degrees) + "], обучение "
                        + fitMs.ToString("0.0", Fmt.Inv) + " мс");
                }
                outp.Add(sec);
            }
            return outp;
        }

        /// <summary>%.0f с «половиной к чётному» (как Python), а не к большему по модулю.</summary>
        private static string F0(double v) =>
            Math.Round(v, MidpointRounding.ToEven).ToString("0", Fmt.Inv);

        private static string Join(int[] v)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < v.Length; i++)
            {
                if (i > 0) sb.Append(", ");
                sb.Append(v[i].ToString(Fmt.Inv));
            }
            return sb.ToString();
        }
    }
}
