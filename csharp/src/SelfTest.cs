using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace Pappa
{
    /// <summary>
    /// Самопроверка без внешних зависимостей (xUnit/NUnit не тащим): конформанс-векторы,
    /// дымовой тест пайплайна и round-trip документа. Запуск:
    ///   pappa.exe selftest [каталог с векторами]
    /// Код возврата: 0 — всё прошло, 1 — расхождения.
    /// </summary>
    public static class SelfTest
    {
        /// <summary>Допуск для гладкого синтетического контура (у Kotlin тот же 1e-6).</summary>
        private const double SmoothedTol = 1e-6;

        private static int failures;

        private static void Check(bool ok, string what)
        {
            Console.WriteLine("  " + (ok ? "[ok]" : "[FAIL]") + " " + what);
            if (!ok) failures++;
        }

        public static int Run(string vecDir)
        {
            failures = 0;
            Console.WriteLine("C# SelfTest (.NET " + Environment.Version + "): "
                + Path.GetFullPath(vecDir));

            // --- 1. конформанс-векторы ---
            if (!Directory.Exists(vecDir))
            {
                Console.WriteLine("[FAIL] нет каталога векторов: " + vecDir);
                return 1;
            }
            var vectors = Conformance.Load(vecDir);
            Console.WriteLine("векторы конформанса (" + vectors.Count + "):");
            Check(vectors.Count >= 4, "не меньше 4 векторов");
            foreach (var v in vectors)
            {
                var r = Conformance.Check(v.Data);
                Check(r.Ok, v.File + " — " + r.Detail);
                foreach (var n in r.Notes) Console.WriteLine("       -> " + n);
            }

            // --- 2. дымовой тест пайплайна: гладкая синусоида, 360 точек ---
            Console.WriteLine("дымовой тест пайплайна (гладкая синусоида, 360 точек):");
            var csv = new StringBuilder("section_id,height_mm,angle_deg,radius_mm\n");
            for (int i = 0; i < 360; i++)
                csv.Append("0,0,").Append(i.ToString(Fmt.Inv)).Append(',')
                   .Append((50 + 0.4 * Math.Sin(i * Math.PI / 180)).ToString("0.000000", Fmt.Inv))
                   .Append('\n');

            string tmp = Path.Combine(Path.GetTempPath(),
                "pappa_csharp_selftest_" + Guid.NewGuid().ToString("N") + ".csv");
            File.WriteAllText(tmp, csv.ToString(), new UTF8Encoding(false));
            var rows = Csv.Load(tmp);
            File.Delete(tmp);
            Check(rows.Count == 360, "разбор CSV: 360 точек");

            var angles = new double[rows.Count];
            var radii = new double[rows.Count];
            for (int i = 0; i < rows.Count; i++)
            {
                angles[i] = rows[i].AngleDeg;
                radii[i] = rows[i].RadiusMm;
            }
            var m = new Model();
            m.Fit(angles, radii);
            Check(m.Patches.Count == 7, "патчей " + m.Patches.Count);
            var curve = m.Eval(angles);
            double maxErr = 0.0;
            for (int i = 0; i < radii.Length; i++)
                maxErr = Math.Max(maxErr, Math.Abs(curve[i] - radii[i]));
            Check(maxErr < SmoothedTol, "контур гладкой синусоиды: max|Δ| = " + Fmt.E(maxErr)
                + " мм (нужно < " + Fmt.E(SmoothedTol) + ")");

            // --- 3. round-trip документа: папка образца -> разбор -> инварианты ---
            Console.WriteLine("round-trip документа (2 сечения, ямы включены):");
            RunDocumentRoundTrip();

            Console.WriteLine(failures == 0
                ? "ВЫВОД: SelfTest пройден"
                : "ВЫВОД: провалов " + failures);
            return failures == 0 ? 0 : 1;
        }

        /// <summary>
        /// Папка образца пишется и тут же читается обратно: контракт документа — это
        /// не только «числа как у Python», но и форма (ключи, length(coefs) = degree+1,
        /// pit_terms у КАЖДОГО патча модели с ямами — этого ждёт загрузчик Python).
        /// </summary>
        private static void RunDocumentRoundTrip()
        {
            string dir = Path.Combine(Path.GetTempPath(),
                "pappa_csharp_sample_" + Guid.NewGuid().ToString("N"));
            try
            {
                var sections = new List<Csv.SectionModel>();
                var opt = new Csv.PipelineOptions { Verbose = false };
                for (int s = 0; s < 2; s++)
                {
                    var rows = new List<Csv.Row>();
                    for (int i = 0; i < 360; i++)
                    {
                        // Профиль ровно как в конформанс-векторе детектора (шаг 1°):
                        // гладкая основа + шумовая подложка 47°/13° + ДВЕ резкие
                        // ямы-«ступени». Ямы обязаны быть «ступенями»: разницу узкой
                        // (1°) и широкой (10°) медиан даёт только резкий перепад, на
                        // плавном гауссе детектор ничего не найдёт и pit_terms не
                        // проверится. Шумовая подложка даёт индикатору масштаб (MAD).
                        double a = i;
                        double rad = a * Math.PI / 180;
                        double r = 15.0 + 0.4 * Math.Sin(2 * rad) + 0.2 * Math.Cos(3 * rad)
                                   + 0.03 * Math.Sin(47 * rad) + 0.02 * Math.Sin(13 * rad)
                                   + 0.01 * Math.Sin(37 * rad);
                        if (Math.Abs(a - 90.0) <= 1.5) r -= 1.1;
                        if (Math.Abs(a - 210.0) <= 1.0) r -= 0.8;
                        rows.Add(new Csv.Row
                        {
                            SectionId = s,
                            HeightMm = 10.0 * s,
                            AngleDeg = a,
                            RadiusMm = r,
                        });
                    }
                    var models = Csv.ProcessSections(rows, opt);
                    Check(models.Count == 1, "сечение " + s + ": посчитано " + models.Count);
                    if (models.Count > 0)
                    {
                        Check(models[0].Pits.Length >= 1,
                            "сечение " + s + ": детектор нашёл ям " + models[0].Pits.Length);
                        int kept = 0;
                        foreach (var p in models[0].Model.Patches)
                            if (p.PitOffsetsDeg.Length > 0) kept++;
                        Check(kept >= 1, "сечение " + s + ": патчей с терминами ям " + kept);
                    }
                    sections.AddRange(models);
                }

                Document.SaveSample(dir, "selftest", sections,
                    new Document.SampleOptions
                    {
                        Name = "selftest",
                        InputCsv = "selftest.csv",
                        Pits = true,
                        Description = "C# SelfTest",
                    });

                var manifest = Json.ParseObject(File.ReadAllText(Path.Combine(dir, "sample.json")));
                Check(Json.Str(manifest, "format") == "pappa-sample", "манифест: format=pappa-sample");
                var secList = Json.Arr(Json.Get(manifest, "sections"));
                Check(secList.Count == 2, "манифест: секций " + secList.Count);
                Check(File.Exists(Path.Combine(dir, "sections", "00.pappa.json")),
                    "сечения пишутся как sections/NN.pappa.json");

                int docsChecked = 0;
                for (int i = 0; i < secList.Count; i++)
                {
                    var entry = Json.Obj(secList[i]);
                    string file = Json.Str(entry, "file");
                    var doc = Json.ParseObject(File.ReadAllText(Path.Combine(dir, file)));
                    Check(Json.Str(doc, "format") == "pappa" && Json.Str(doc, "version") == "2.0",
                        file + ": format=pappa version=2.0");
                    Check(Json.Str(doc, "method") == "PitPatchApproximator",
                        file + ": method=PitPatchApproximator");
                    var patches = Json.Arr(Json.Get(doc, "patches"));
                    Check(patches.Count == 7, file + ": патчей " + patches.Count);
                    int withPitTerms = 0;
                    int coefsOk = 0;
                    foreach (var po in patches)
                    {
                        var p = Json.Obj(po);
                        if (Json.Has(p, "pit_terms")) withPitTerms++;
                        if (Json.Doubles(p, "coefs").Length == Json.Int(p, "degree") + 1) coefsOk++;
                    }
                    Check(withPitTerms == patches.Count,
                        file + ": pit_terms у каждого патча (" + withPitTerms + "/" + patches.Count + ")");
                    Check(coefsOk == patches.Count,
                        file + ": len(coefs) = degree+1 у каждого патча (" + coefsOk + "/" + patches.Count + ")");
                    docsChecked++;
                }
                Check(docsChecked == 2, "прочитано документов: " + docsChecked);
            }
            catch (Exception ex)
            {
                Check(false, "round-trip упал: " + ex.GetType().Name + ": " + ex.Message);
            }
            finally
            {
                try { if (Directory.Exists(dir)) Directory.Delete(dir, true); } catch { }
            }
        }
    }
}
