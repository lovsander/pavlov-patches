using System;
using System.Globalization;
using System.IO;
using System.Text;

namespace Pappa.Cli
{
    /// <summary>
    /// Единая точка входа C#-порта: pappa.exe &lt;команда&gt; [ключи].
    ///
    ///   pappa.exe conformance [каталог-векторов]    проверка по конформанс-векторам (0/1/2)
    ///   pappa.exe selftest    [каталог-векторов]    векторы + дымовой тест + round-trip (0/1)
    ///   pappa.exe pipeline    --input F.csv --out-dir DIR [--name N] [--description ТЕКСТ]
    ///                         [--no-pits] [--quiet]   CSV с сечениями -> папка образца
    ///
    /// Почему подкоманды, а не три exe: .NET-проект с несколькими Main собирается только
    /// через StartupObject, а один exe с командами читается ровно так же, как
    /// pappa_conformance/pappa_pipeline у C++.
    /// </summary>
    public static class Program
    {
        public static int Main(string[] args)
        {
            // Локаль машины не должна влиять ни на числа, ни на разделители.
            CultureInfo.DefaultThreadCurrentCulture = Fmt.Inv;
            CultureInfo.DefaultThreadCurrentUICulture = Fmt.Inv;
            try { Console.OutputEncoding = new UTF8Encoding(false); } catch { }

            if (args.Length == 0)
            {
                Usage();
                return 2;
            }

            string cmd = args[0].ToLowerInvariant();
            var rest = new string[args.Length - 1];
            Array.Copy(args, 1, rest, 0, rest.Length);

            try
            {
                switch (cmd)
                {
                    case "conformance":
                    case "vectors":
                        return RunConformance(rest);
                    case "selftest":
                    case "test":
                        return SelfTest.Run(VecDir(rest));
                    case "pipeline":
                    case "run":
                        return RunPipeline(rest);
                    case "help":
                    case "--help":
                    case "-h":
                        Usage();
                        return 0;
                    default:
                        Console.Error.WriteLine("неизвестная команда: " + args[0]);
                        Usage();
                        return 2;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("ОШИБКА: " + ex.GetType().Name + ": " + ex.Message);
                return 1;
            }
        }

        private static string VecDir(string[] args) =>
            args.Length > 0 && args[0].Length > 0 ? args[0] : "../spec/conformance/vectors";

        private static int RunConformance(string[] args)
        {
            string vecDir = VecDir(args);
            if (!Directory.Exists(vecDir))
            {
                Console.WriteLine("нет каталога векторов: " + vecDir);
                return 2;
            }
            var vectors = Conformance.Load(vecDir);
            Console.WriteLine("C# порт PAPPA: " + vectors.Count + " векторов (.NET "
                + Environment.Version + ", зависимостей из NuGet: 0)");

            int bad = 0;
            foreach (var v in vectors)
            {
                var r = Conformance.Check(v.Data);
                if (!r.Ok) bad++;
                Console.WriteLine(Fmt.Pad(v.File, 46) + " " + Fmt.Pad(r.Ok ? "OK" : "FAIL", 5)
                    + " " + r.Detail);
                int shown = 0;
                foreach (var n in r.Notes)
                {
                    Console.WriteLine(new string(' ', 52) + "-> " + n);
                    if (++shown >= 4) break;
                }
            }
            Console.WriteLine(bad == 0
                ? "ВЫВОД: C#-порт проходит все векторы"
                : "ВЫВОД: расхождений " + bad);
            return bad == 0 ? 0 : 1;
        }

        private static int RunPipeline(string[] args)
        {
            string input = null;
            string outDir = null;
            string name = "sample";
            string description = "PAPPA C# port";
            bool pits = true;
            bool quiet = false;

            for (int i = 0; i < args.Length; i++)
            {
                switch (args[i])
                {
                    case "--input": input = Next(args, ref i); break;
                    case "--out-dir": outDir = Next(args, ref i); break;
                    case "--name": name = Next(args, ref i); break;
                    case "--description": description = Next(args, ref i); break;
                    case "--no-pits": pits = false; break;
                    case "--quiet": quiet = true; break;
                    default:
                        Usage();
                        return 2;
                }
            }
            if (string.IsNullOrEmpty(input) || string.IsNullOrEmpty(outDir))
            {
                Usage();
                return 2;
            }

            var rows = Csv.Load(input);
            Console.WriteLine("PAPPA (C#): " + rows.Count + " точек, вход " + input);

            var opt = new Csv.PipelineOptions { Pits = pits, Verbose = !quiet };
            var sections = Csv.ProcessSections(rows, opt);
            var root = Document.SaveSample(outDir, name, sections, new Document.SampleOptions
            {
                Name = name,
                InputCsv = input,
                Pits = pits,
                Description = description,
                Cleaner = opt.Cleaner,
                Detector = opt.Detector,
            });

            Console.WriteLine();
            Console.WriteLine("Образец записан: " + root);
            Console.WriteLine("  манифест: " + Path.Combine(root, "sample.json"));
            Console.WriteLine("  сечений:  " + sections.Count + " (sections/*.pappa.json)");
            Console.WriteLine();
            Console.WriteLine("Сверка с референсом Python:");
            Console.WriteLine("  python python/studies/verify_port.py --py-dir samples/synthetic_sphere "
                + "--cpp-dir " + root);
            return 0;
        }

        private static string Next(string[] args, ref int i)
        {
            if (i + 1 >= args.Length)
                throw new ArgumentException("ключ " + args[i] + " требует значения");
            return args[++i];
        }

        private static void Usage()
        {
            Console.WriteLine("PAPPA (C#) — Piecewise Adaptive Poly-Patch Approximation.");
            Console.WriteLine();
            Console.WriteLine("  pappa.exe conformance [каталог-векторов]");
            Console.WriteLine("  pappa.exe selftest    [каталог-векторов]");
            Console.WriteLine("  pappa.exe pipeline    --input FILE.csv --out-dir DIR [--name NAME]");
            Console.WriteLine("                        [--description ТЕКСТ] [--no-pits] [--quiet]");
            Console.WriteLine();
            Console.WriteLine("Каталог векторов по умолчанию: ../spec/conformance/vectors");
        }
    }
}
