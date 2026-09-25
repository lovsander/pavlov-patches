package pappa.cli;

import java.io.IOException;
import java.util.List;
import java.util.Locale;

import pappa.Csv;
import pappa.Document;

/**
 * Пайплайн PAPPA на Java: CSV с сечениями → папка образца.
 *
 * Пишет ТОТ ЖЕ формат, что референс Python и порты C++/C/Go/JS:
 *   &lt;out-dir&gt;/sample.json  +  &lt;out-dir&gt;/sections/NN.pappa.json
 *
 * Проверка: python python/studies/verify_port.py --py-dir &lt;эталон&gt; --cpp-dir &lt;out-dir&gt;
 *
 * Запуск: java -cp out pappa.cli.PappaMain --input python/synthetic_data.csv \
 *         --out-dir samples/synthetic_sphere_java --name synthetic_sphere
 */
public final class PappaMain {

    private PappaMain() { }

    public static void main(String[] args) throws IOException {
        Locale.setDefault(Locale.ROOT);      // стабильный вывод (точка, а не запятая) при любой локали
        String input = null;
        String outDir = null;
        String name = "sample";
        String description = "PAPPA Java port";
        boolean pits = true;
        boolean quiet = false;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--input" -> input = args[++i];
                case "--out-dir" -> outDir = args[++i];
                case "--name" -> name = args[++i];
                case "--description" -> description = args[++i];
                case "--no-pits" -> pits = false;
                case "--quiet" -> quiet = true;
                default -> {
                    System.out.println("PAPPA (Java): --input FILE.csv --out-dir DIR "
                            + "[--name NAME] [--description ТЕКСТ] [--no-pits] [--quiet]");
                    System.exit(2);
                }
            }
        }
        if (input == null || outDir == null) {
            System.out.println("PAPPA (Java): --input FILE.csv --out-dir DIR "
                    + "[--name NAME] [--description ТЕКСТ] [--no-pits] [--quiet]");
            System.exit(2);
        }

        List<Csv.Row> rows = Csv.load(input);
        System.out.printf("PAPPA (Java): %d точек, вход %s%n", rows.size(), input);

        Csv.PipelineOptions base = Csv.PipelineOptions.defaults();
        Csv.PipelineOptions opt = new Csv.PipelineOptions(base.model(), base.cleaner(),
                base.detector(), pits, !quiet);
        List<Csv.SectionModel> sections = Csv.processSections(rows, opt);

        String root = Document.saveSample(outDir, name, sections,
                new Document.SampleOptions(name, input, pits, description,
                        opt.cleaner(), opt.detector()));
        System.out.printf("%nОбразец записан: %s%n", root);
        System.out.printf("  манифест: %s%n", root + "/sample.json");
        System.out.printf("  сечений:  %d (sections/*.pappa.json)%n", sections.size());
        System.out.println("\nСверка с референсом Python:");
        System.out.printf("  python python/studies/verify_port.py --cpp-dir %s%n", root);
    }
}
