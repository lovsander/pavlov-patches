package pappa;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go). */
public final class Csv {

    private Csv() { }

    public record Row(int sectionId, double heightMm, double angleDeg, double radiusMm) { }

    /** Папка образца: одно сечение + модель + метаданные. */
    public record SectionModel(int sectionId, double heightMm, Model model, int nPointsTotal,
                               int nOutliers, double fitTimeMs, String description,
                               double[] pits, int nUsed) { }

    public record PipelineOptions(Model.Options model, Cleaner.Options cleaner,
                                  Detector.Options detector, boolean pits, boolean verbose) {
        public static PipelineOptions defaults() {
            return new PipelineOptions(Model.Options.defaults(), Cleaner.Options.defaults(),
                    Detector.Options.defaults(), true, true);
        }
    }

    /** Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок). */
    public static List<Row> load(String path) throws IOException {
        List<String> lines = Files.readAllLines(Path.of(path), StandardCharsets.UTF_8);
        List<String> data = new ArrayList<>();
        for (String l : lines) if (!l.isBlank()) data.add(l);
        if (data.isEmpty()) throw new IOException("пустой CSV: " + path);

        String[] head = data.get(0).split(",", -1);
        Map<String, Integer> index = new LinkedHashMap<>();
        for (int i = 0; i < head.length; i++) index.put(head[i].trim(), i);
        for (String need : new String[] { "section_id", "height_mm", "angle_deg", "radius_mm" }) {
            if (!index.containsKey(need)) {
                throw new IOException("в CSV нет колонки \"" + need + "\"");
            }
        }

        List<Row> rows = new ArrayList<>();
        for (int k = 1; k < data.size(); k++) {
            String[] f = data.get(k).split(",", -1);
            if (f.length <= Math.max(Math.max(index.get("section_id"), index.get("height_mm")),
                    Math.max(index.get("angle_deg"), index.get("radius_mm")))) continue;
            rows.add(new Row(Integer.parseInt(f[index.get("section_id")].trim()),
                    Double.parseDouble(f[index.get("height_mm")].trim()),
                    Double.parseDouble(f[index.get("angle_deg")].trim()),
                    Double.parseDouble(f[index.get("radius_mm")].trim())));
        }
        if (rows.isEmpty()) throw new IOException("в CSV нет строк с данными");
        return rows;
    }

    /** Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение. */
    public static List<SectionModel> processSections(List<Row> rows, PipelineOptions opt)
            throws IOException {
        Map<Integer, List<Row>> bySection = new LinkedHashMap<>();
        for (Row r : rows) bySection.computeIfAbsent(r.sectionId(), k -> new ArrayList<>()).add(r);
        List<Integer> ids = new ArrayList<>(bySection.keySet());
        ids.sort(Comparator.naturalOrder());

        List<SectionModel> out = new ArrayList<>();
        for (int sid : ids) {
            List<Row> group = new ArrayList<>(bySection.get(sid));
            group.sort(Comparator.comparingDouble(Row::angleDeg));
            int n = group.size();
            double[] angles = new double[n];
            double[] radii = new double[n];
            for (int i = 0; i < n; i++) {
                angles[i] = group.get(i).angleDeg();
                radii[i] = group.get(i).radiusMm();
            }

            Cleaner.Result cl = Cleaner.cleanIqr(angles, radii, opt.cleaner());
            List<Double> ca = new ArrayList<>();
            List<Double> cr = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                if (cl.mask()[i]) continue;
                ca.add(angles[i]);
                cr.add(radii[i]);
            }
            double[] aClean = toArray(ca);
            double[] rClean = toArray(cr);

            double[] pits = opt.pits() ? Detector.pits(aClean, rClean, opt.detector())
                    : new double[0];
            Model model = new Model(opt.model(), pits);
            if (pits.length > 0) model.setPitShape(Model.PitShape.defaults());

            long t0 = System.nanoTime();
            model.fit(aClean, rClean);
            double fitMs = (System.nanoTime() - t0) / 1e6;

            SectionModel sec = new SectionModel(sid, group.get(0).heightMm(), model, n,
                    cl.nOutliers(), fitMs,
                    String.format("сечение %d, h=%.0f мм", sid, group.get(0).heightMm()),
                    pits, aClean.length);
            if (opt.verbose()) {
                System.out.printf("  секция %d (h=%.0f мм): точек %d, выброшено %d, "
                                + "ям найдено %d, степени %s, обучение %.1f мс%n",
                        sid, sec.heightMm(), n, cl.nOutliers(), pits.length,
                        java.util.Arrays.toString(model.degrees()), fitMs);
            }
            out.add(sec);
        }
        return out;
    }

    private static double[] toArray(List<Double> v) {
        double[] a = new double[v.size()];
        for (int i = 0; i < a.length; i++) a[i] = v.get(i);
        return a;
    }
}
