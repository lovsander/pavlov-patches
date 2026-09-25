package pappa;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS:
 *   &lt;out_dir&gt;/sample.json              манифест (format pappa-sample v1.0)
 *   &lt;out_dir&gt;/sections/NN.pappa.json   документ сечения (pappa v2.0)
 * Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
 * сравниваются численно (python/studies/verify_port.py).
 */
public final class Document {

    private Document() { }

    public static final String PORT_VERSION = "0.1.0";

    public record SampleOptions(String name, String inputCsv, boolean pits, String description,
                                Cleaner.Options cleaner, Detector.Options detector) {
        public static SampleOptions defaults(String name, String inputCsv, boolean pits) {
            return new SampleOptions(name, inputCsv, pits, "PAPPA Java port",
                    Cleaner.Options.defaults(), Detector.Options.defaults());
        }
    }

    private static String isoUtcNow() {
        return ZonedDateTime.now(ZoneOffset.UTC)
                .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'"));
    }

    private static String esc(String s) {
        StringBuilder b = new StringBuilder();
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default: b.append(c);
            }
        }
        return b.toString();
    }

    /** Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++. */
    private static final class W {
        final StringBuilder b = new StringBuilder();
        int depth;

        String ind() { return "  ".repeat(Math.max(0, depth)); }

        void objStart() { b.append('{'); depth++; b.append('\n').append(ind()); }
        void objEnd() { depth--; b.append('\n').append(ind()).append('}'); }
        void arrStart() { b.append('['); depth++; b.append('\n').append(ind()); }
        void arrEnd() { depth--; b.append('\n').append(ind()).append(']'); }
        void comma() { b.append(',').append('\n').append(ind()); }

        void key(String k) { b.append(ind()).append('"').append(k).append("\": "); }
        void str(String s) { b.append('"').append(esc(s)).append('"'); }
        void num(double v) { b.append(Json.num(v)); }
        void raw(String s) { b.append(s); }

        void kv(String k, String v) { key(k); str(v); }
        void kv(String k, double v) { key(k); num(v); }
        void kv(String k, int v) { key(k); b.append(v); }
        void kv(String k, boolean v) { key(k); b.append(v); }
    }

    private static void writePatches(W w, Model m) {
        w.key("patches");
        w.arrStart();
        List<Model.Patch> ps = m.patches();
        for (int i = 0; i < ps.size(); i++) {
            Model.Patch p = ps.get(i);
            w.b.append(i > 0 ? ",\n" + w.ind() : "\n" + w.ind());
            w.objStart();
            w.kv("center_deg", p.centerDeg());     w.comma();
            w.kv("degree", p.degree());            w.comma();
            w.kv("n_points", p.nPoints());         w.comma();
            w.key("coefs");
            w.arrStart();
            for (int j = 0; j < p.coefs().length; j++) {
                if (j > 0) w.raw(", ");
                w.num(p.coefs()[j]);
            }
            w.arrEnd();
            w.comma();

            w.key("metrics");
            w.objStart();
            w.kv("amplitude_mm", p.metrics().amplitudeMm());             w.comma();
            w.kv("mean_radius_mm", p.metrics().meanRadiusMm());          w.comma();
            w.kv("amplitude_norm", p.metrics().amplitudeNorm());         w.comma();
            w.kv("deg_elbow_tol", p.metrics().degElbowTol());            w.comma();
            w.kv("rmse_selected_mm", p.metrics().rmseSelectedMm());      w.comma();
            w.kv("rmse_best_mm", p.metrics().rmseBestMm());              w.comma();
            w.kv("n_train_points", p.metrics().nTrainPoints());
            w.objEnd();
            w.comma();

            w.key("stats");
            w.objStart();
            w.kv("rmse_mm", p.stats().rmseMm());        w.comma();
            w.kv("mae_mm", p.stats().maeMm());          w.comma();
            w.kv("max_err_mm", p.stats().maxErrMm());   w.comma();
            w.kv("correlation", p.stats().correlation());
            w.objEnd();

            // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
            // (включая пустой список): так ждёт загрузчик Python.
            if (m.hasPits()) {
                w.comma();
                w.key("pit_terms");
                w.arrStart();
                for (int j = 0; j < p.pitOffsetsDeg().length; j++) {
                    if (j > 0) w.raw(", ");
                    w.objStart();
                    w.kv("dx_deg", p.pitOffsetsDeg()[j]);   w.comma();
                    w.kv("amp", p.pitCoefs()[j]);
                    w.objEnd();
                }
                w.arrEnd();
            }
            w.objEnd();
        }
        w.b.append('\n').append(w.ind());
        w.arrEnd();
    }

    public static String saveSectionDocument(Path path, Csv.SectionModel section)
            throws IOException {
        Model m = section.model();
        if (!m.isFitted()) throw new IllegalStateException("saveSectionDocument: модель не обучена");
        W w = new W();
        w.objStart();
        w.kv("format", "pappa");       w.comma();
        w.kv("version", "2.0");        w.comma();
        w.kv("method", m.hasPits() ? "PitPatchApproximator" : "PatchApproximator"); w.comma();
        w.kv("created", isoUtcNow());  w.comma();

        w.key("software");
        w.objStart();
        w.kv("language", "java");      w.comma();
        w.kv("pappa_version", PORT_VERSION);
        w.objEnd();
        w.comma();

        w.key("meta");
        w.objStart();
        w.kv("section_id", section.sectionId());       w.comma();
        w.kv("height_mm", section.heightMm());         w.comma();
        w.kv("source", "csv");                         w.comma();
        w.kv("description", section.description());
        w.objEnd();
        w.comma();

        w.key("global");
        w.objStart();
        w.key("units");
        w.objStart();
        w.kv("angle", "degree");   w.comma();
        w.kv("length", "mm");
        w.objEnd();
        w.comma();
        Model.Options opt = m.options();
        w.kv("n_patches", opt.nPatches());                w.comma();
        w.kv("half_sector_deg", m.halfSector());          w.comma();
        w.kv("phase_deg", opt.phaseDeg());                w.comma();
        w.kv("half_train_deg", m.halfTrain());            w.comma();
        w.kv("half_use_deg", m.halfUse());                w.comma();
        w.kv("overlap_train_deg", opt.overlapTrain());    w.comma();
        w.kv("overlap_use_deg", opt.overlapUse());        w.comma();
        w.kv("deg_min", opt.degMin());                    w.comma();
        w.kv("deg_max", opt.degMax());                    w.comma();
        w.kv("coord_mode", opt.coordMode());              w.comma();
        w.kv("deg_elbow_tol", opt.degElbowTol());         w.comma();
        w.kv("amplitude_scale", opt.amplitudeScale());
        if (m.hasPits()) {
            Model.PitShape ps = m.pitShape();
            w.comma();
            w.key("pit");
            w.objStart();
            w.kv("sigma_deg", ps.sigmaDeg());        w.comma();
            w.kv("core_sigma", ps.coreSigma());      w.comma();
            w.kv("window_sigma", ps.windowSigma());  w.comma();
            w.kv("pit_min_amp", ps.pitMinAmp());     w.comma();
            w.kv("tapering", ps.tapering());         w.comma();
            w.key("centers_deg");
            w.arrStart();
            for (int i = 0; i < m.pits().length; i++) {
                if (i > 0) w.raw(", ");
                w.num(m.pits()[i]);
            }
            w.arrEnd();
            w.objEnd();
        }
        w.objEnd();
        w.comma();

        writePatches(w, m);
        w.comma();

        w.key("statistics");
        w.objStart();
        w.kv("n_points_total", section.nPointsTotal());     w.comma();
        w.kv("n_outliers_removed", section.nOutliers());    w.comma();
        w.kv("fit_time_ms", section.fitTimeMs());
        w.objEnd();

        w.objEnd();
        Files.writeString(path, w.b.toString() + "\n", StandardCharsets.UTF_8);
        return path.toString();
    }

    public static String saveSample(String outDir, String name, List<Csv.SectionModel> sections,
                                    SampleOptions o) throws IOException {
        Path root = Path.of(outDir);
        Files.createDirectories(root.resolve("sections"));

        List<Csv.SectionModel> ordered = new ArrayList<>(sections);
        ordered.sort(Comparator.comparingInt(Csv.SectionModel::sectionId));
        Model first = ordered.isEmpty() ? null : ordered.get(0).model();

        W w = new W();
        w.objStart();
        w.kv("format", "pappa-sample");   w.comma();
        w.kv("version", "1.0");           w.comma();
        w.kv("name", name);               w.comma();
        w.kv("created", isoUtcNow());     w.comma();

        w.key("units");
        w.objStart();
        w.kv("angle", "degree");  w.comma();
        w.kv("length", "mm");
        w.objEnd();
        w.comma();

        w.key("meta");
        w.objStart();
        w.kv("description", o.description());
        w.objEnd();
        w.comma();

        if (o.inputCsv() != null && !o.inputCsv().isEmpty()) {
            w.key("input");
            w.objStart();
            w.kv("csv", o.inputCsv());
            w.objEnd();
            w.comma();
        }

        w.key("config");
        w.objStart();
        Model.Options opt = first == null ? Model.Options.defaults() : first.options();
        w.kv("n_patches", first == null ? 0 : opt.nPatches());           w.comma();
        w.kv("phase_deg", first == null ? 0.0 : opt.phaseDeg());         w.comma();
        w.kv("deg_min", first == null ? 0 : opt.degMin());               w.comma();
        w.kv("deg_max", first == null ? 0 : opt.degMax());               w.comma();
        w.kv("overlap_train", first == null ? 0.0 : opt.overlapTrain()); w.comma();
        w.kv("overlap_use", first == null ? 0.0 : opt.overlapUse());     w.comma();
        w.kv("deg_elbow_tol", first == null ? 0.0 : opt.degElbowTol());  w.comma();
        w.key("cleaner");
        w.raw("{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", "
                + "\"baseline_deg\": " + Json.num(o.cleaner().baselineDeg())
                + ", \"iqr_k\": " + Json.num(o.cleaner().iqrK()) + "}}");
        w.comma();
        w.kv("pits", o.pits());
        if (o.pits() && first != null) {
            Model.PitShape ps = first.pitShape();
            w.comma();
            w.kv("sigma_deg", ps.sigmaDeg());            w.comma();
            w.kv("pit_core_sigma", ps.coreSigma());      w.comma();
            w.kv("pit_window_sigma", ps.windowSigma());  w.comma();
            w.kv("pit_min_amp", ps.pitMinAmp());         w.comma();
            w.kv("tapering", ps.tapering());
        }
        w.comma();
        w.key("detector");
        w.raw("null");
        w.objEnd();
        w.comma();

        w.key("sections");
        w.arrStart();
        for (int i = 0; i < ordered.size(); i++) {
            Csv.SectionModel s = ordered.get(i);
            String file = String.format("sections/%02d.pappa.json", i);
            saveSectionDocument(root.resolve(file), s);
            w.b.append(i > 0 ? ",\n" + w.ind() : "\n" + w.ind());
            w.objStart();
            w.kv("index", i);                        w.comma();
            w.kv("section_id", s.sectionId());       w.comma();
            w.kv("height_mm", s.heightMm());         w.comma();
            w.kv("file", file);                      w.comma();
            w.kv("n_points", s.nPointsTotal());      w.comma();
            w.kv("n_outliers", s.nOutliers());
            w.objEnd();
        }
        w.b.append('\n').append(w.ind());
        w.arrEnd();

        w.objEnd();
        Files.writeString(root.resolve("sample.json"), w.b.toString() + "\n",
                StandardCharsets.UTF_8);
        return root.toString();
    }
}


