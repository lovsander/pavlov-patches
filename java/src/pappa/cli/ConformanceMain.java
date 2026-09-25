package pappa.cli;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

import pappa.Conformance;

/**
 * Проверка Java-порта PAPPA по конформанс-векторам.
 * Запуск: java -cp out pappa.cli.ConformanceMain [каталог с векторами]
 * Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.
 */
public final class ConformanceMain {

    private ConformanceMain() { }

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.ROOT);      // вывод не должен зависеть от локали (ru-RU дал бы "8,73e-11")
        Path vecDir = Path.of(args.length > 0 ? args[0] : "../spec/conformance/vectors");
        if (!Files.isDirectory(vecDir)) {
            System.out.println("нет каталога векторов: " + vecDir);
            System.exit(2);
        }
        List<Conformance.Vector> vectors = Conformance.load(vecDir);
        System.out.println("Java-порт PAPPA: " + vectors.size() + " векторов (Java "
                + System.getProperty("java.version") + ")");

        int bad = 0;
        for (Conformance.Vector v : vectors) {
            Conformance.Result r = Conformance.check(v.data());
            if (!r.ok()) bad++;
            System.out.printf("%-46s %-5s %s%n", v.file(), r.ok() ? "OK" : "FAIL", r.detail());
            for (String n : r.notes().subList(0, Math.min(4, r.notes().size()))) {
                System.out.println(" ".repeat(52) + "-> " + n);
            }
        }
        System.out.println(bad == 0 ? "ВЫВОД: Java-порт проходит все векторы"
                : "ВЫВОД: расхождений " + bad);
        System.exit(bad == 0 ? 0 : 1);
    }
}
