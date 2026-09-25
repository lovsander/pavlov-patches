package pappa;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

/**
 * Самопроверка без внешних зависимостей (JUnit не тащим): конформанс-векторы +
 * дымовой тест пайплайна. Запуск: java -ea -cp out pappa.SelfTest
 * Код возврата: 0 — всё прошло, 1 — расхождения.
 */
public final class SelfTest {

    private SelfTest() { }

    private static int failures;

    private static void check(boolean ok, String what) {
        System.out.printf("  %s %s%n", ok ? "[ok]" : "[FAIL]", what);
        if (!ok) failures++;
    }

    public static void main(String[] args) throws IOException {
        Locale.setDefault(Locale.ROOT);
        Path vecDir = Path.of(args.length > 0 ? args[0] : "../spec/conformance/vectors");
        System.out.println("Java SelfTest: " + vecDir.toAbsolutePath());

        List<Conformance.Vector> vectors = Conformance.load(vecDir);
        System.out.printf("векторы конформанса (%d):%n", vectors.size());
        check(vectors.size() >= 4, "не меньше 4 векторов");
        for (Conformance.Vector v : vectors) {
            Conformance.Result r = Conformance.check(v.data());
            check(r.ok(), v.file() + " — " + r.detail());
        }

        System.out.println("дымовой тест пайплайна (гладкая синусоида, 360 точек):");
        StringBuilder csv = new StringBuilder("section_id,height_mm,angle_deg,radius_mm\n");
        for (int i = 0; i < 360; i++) {
            csv.append(String.format("0,0,%d,%.6f%n", i, 50 + 0.4 * Math.sin(i * Math.PI / 180)));
        }
        Path tmp = Files.createTempFile("pappa_java_selftest", ".csv");
        Files.writeString(tmp, csv.toString());
        List<Csv.Row> rows = Csv.load(tmp.toString());
        Files.deleteIfExists(tmp);
        check(rows.size() == 360, "разбор CSV: 360 точек");

        double[] angles = new double[rows.size()];
        double[] radii = new double[rows.size()];
        for (int i = 0; i < rows.size(); i++) {
            angles[i] = rows.get(i).angleDeg();
            radii[i] = rows.get(i).radiusMm();
        }
        Model m = new Model(Model.Options.defaults());
        m.fit(angles, radii);
        check(m.patches().size() == 7, "патчей " + m.patches().size());
        double[] curve = m.eval(angles);
        double maxErr = 0;
        for (int i = 0; i < radii.length; i++) maxErr = Math.max(maxErr, Math.abs(curve[i] - radii[i]));
        check(maxErr < 1e-6, String.format("контур гладкой синусоиды: max|Δ| = %.2e мм", maxErr));

        System.out.println(failures == 0 ? "ВЫВОД: SelfTest пройден"
                : "ВЫВОД: провалов " + failures);
        System.exit(failures == 0 ? 0 : 1);
    }
}
