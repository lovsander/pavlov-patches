package pappa;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/**
 * Проверка порта по конформанс-векторам (spec/conformance/vectors).
 * Допуски — те же, что у C++/Go/C/JS: контур 1e-6 мм, коэффициенты
 * max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
 */
public final class Conformance {

    private Conformance() { }

    public record Result(boolean ok, String detail, List<String> notes) { }

    public record Vector(String file, Map<String, Object> data) { }

    public static List<Vector> load(Path dir) throws IOException {
        List<Vector> out = new ArrayList<>();
        try (Stream<Path> s = Files.list(dir)) {
            List<Path> files = s.filter(p -> p.getFileName().toString().endsWith(".json"))
                    .sorted().toList();
            for (Path p : files) {
                out.add(new Vector(p.getFileName().toString(),
                        Json.parseObject(Files.readString(p, StandardCharsets.UTF_8))));
            }
        }
        return out;
    }

    private static boolean near(double a, double b, double rel, double floor) {
        return Math.abs(a - b) <= Math.max(floor, rel * Math.abs(b));
    }

    public static Result check(Map<String, Object> v) {
        String kind = Json.str(v, "kind");
        if ("model".equals(kind)) return checkModel(v);
        if ("detector".equals(kind)) return checkDetector(v);
        return checkCleaner(v);
    }

    private static double[] toDoubles(List<Object> a) {
        double[] out = new double[a.size()];
        for (int i = 0; i < out.length; i++) out[i] = (Double) a.get(i);
        return out;
    }

    private static Result checkDetector(Map<String, Object> v) {
        Map<String, Object> cfg = Json.obj(v.get("config"));
        Map<String, Object> exp = Json.obj(v.get("expected"));
        Map<String, Object> in = Json.obj(v.get("input"));
        double[] angles = Json.doubles(in, "angles_deg");
        double[] radii = Json.doubles(in, "radii_mm");
        Detector.Options o = new Detector.Options(Json.dbl(cfg, "window_deg"),
                Json.dbl(cfg, "wide_deg"), Json.dbl(cfg, "smooth_deg"),
                Json.dbl(cfg, "k"), Json.dbl(cfg, "min_zone_deg"));

        double[] band = Detector.bandIndicator(angles, radii, o);
        double[][] zn = Detector.zones(angles, band, o);
        List<Object> expZones = Json.arr(exp.get("zones_deg"));
        double[] expPits = Json.doubles(exp, "pits_deg");
        List<String> notes = new ArrayList<>();

        boolean ok = zn.length == expZones.size();
        if (!ok) notes.add("зон " + zn.length + " != " + expZones.size());
        double dev = 0;
        for (int i = 0; i < expZones.size() && i < zn.length; i++) {
            double[] e = toDoubles(Json.arr(expZones.get(i)));
            dev = Math.max(dev, Math.max(Math.abs(zn[i][0] - e[0]), Math.abs(zn[i][1] - e[1])));
        }
        if (zn.length != expPits.length) {
            ok = false;
            notes.add("ям " + zn.length + " != " + expPits.length);
        }
        for (int i = 0; i < expPits.length && i < zn.length; i++) {
            double d = Math.abs(0.5 * (zn[i][0] + zn[i][1]) - expPits[i]);
            dev = Math.max(dev, d);
            if (d > 1e-6) ok = false;
        }
        String detail = String.format("зон %d/%d, ям %d/%d, max|Δ| %.2e°",
                zn.length, expZones.size(), zn.length, expPits.length, dev);
        return new Result(ok, detail, notes);
    }

    private static Result checkCleaner(Map<String, Object> v) {
        Map<String, Object> cfg = Json.obj(v.get("config"));
        Map<String, Object> exp = Json.obj(v.get("expected"));
        Map<String, Object> in = Json.obj(v.get("input"));
        Map<String, Object> tol = Json.obj(v.get("tolerance"));
        double[] angles = Json.doubles(in, "angles_deg");
        double[] radii = Json.doubles(in, "radii_mm");
        Cleaner.Options o = new Cleaner.Options(Json.dbl(cfg, "baseline_deg"),
                Json.dbl(cfg, "iqr_k"), 0.5, 20);
        Cleaner.Result r = Cleaner.cleanIqr(angles, radii, o);

        boolean[] ref = new boolean[radii.length];
        for (int i : Json.ints(exp, "mask_true_indices")) ref[i] = true;
        int n = radii.length;
        int extra = 0;
        int missing = 0;
        int got = 0;
        for (int i = 0; i < n; i++) {
            if (r.mask()[i]) {
                got++;
                if (!ref[i]) extra++;
            } else if (ref[i]) {
                missing++;
            }
        }
        int tolN = Math.max(1, (int) Math.floor(Json.dbl(tol, "frac", 0.02) * n));
        int want = Json.i(exp, "n_outliers");
        boolean ok = extra <= tolN && missing <= tolN && Math.abs(got - want) <= tolN;
        String detail = String.format("выбросов %d (эталон %d), лишних %d, пропущено %d",
                got, want, extra, missing);
        return new Result(ok, detail, List.of());
    }

    private static Result checkModel(Map<String, Object> v) {
        Map<String, Object> cfg = Json.obj(v.get("config"));
        Map<String, Object> exp = Json.obj(v.get("expected"));
        Map<String, Object> tol = Json.obj(v.get("tolerance"));
        Map<String, Object> in = Json.obj(v.get("input"));
        List<String> notes = new ArrayList<>();
        boolean ok = true;

        Model.Options opt = new Model.Options(Json.i(cfg, "n_patches"), Json.dbl(cfg, "phase_deg"),
                Json.i(cfg, "deg_min"), Json.i(cfg, "deg_max"), Json.dbl(cfg, "overlap_train"),
                Json.dbl(cfg, "overlap_use"), Json.dbl(cfg, "deg_elbow_tol"),
                Json.dbl(cfg, "amplitude_scale", 180.0), Json.str(cfg, "coord_mode"));
        double[] pitsDeg = Json.doubles(cfg, "pits_deg");
        Model m = new Model(opt, pitsDeg);
        if (pitsDeg.length > 0) {
            m.setPitShape(new Model.PitShape(Json.dbl(cfg, "sigma_deg"),
                    Json.dbl(cfg, "pit_core_sigma"), Json.dbl(cfg, "pit_window_sigma"),
                    Json.dbl(cfg, "pit_min_amp"), Json.bool(cfg, "tapering", true)));
        }
        m.fit(Json.doubles(in, "angles_deg"), Json.doubles(in, "radii_mm"));

        int[] wantDeg = Json.ints(exp, "degrees");
        int[] gotDeg = m.degrees();
        boolean degOk = wantDeg.length == gotDeg.length;
        if (degOk) {
            for (int i = 0; i < wantDeg.length; i++) if (wantDeg[i] != gotDeg[i]) degOk = false;
        }
        if (!degOk) {
            ok = false;
            notes.add("степени " + java.util.Arrays.toString(gotDeg)
                    + " != " + java.util.Arrays.toString(wantDeg));
        }

        double rel = Json.dbl(tol, "coefs_rel");
        double floor = Json.dbl(tol, "coefs_abs_floor");
        List<Object> coefs = Json.arr(exp.get("coefs"));
        double maxC = 0;
        int badC = 0;
        for (int i = 0; i < coefs.size(); i++) {
            double[] ref = toDoubles(Json.arr(coefs.get(i)));
            double[] got = i < m.patches().size() ? m.patches().get(i).coefs() : new double[0];
            if (got.length != ref.length) { ok = false; badC++; continue; }
            for (int j = 0; j < ref.length; j++) {
                maxC = Math.max(maxC, Math.abs(got[j] - ref[j]));
                if (!near(got[j], ref[j], rel, floor)) { ok = false; badC++; }
            }
        }

        List<Object> pitTerms = Json.arr(exp.get("pit_terms"));
        double maxPit = 0;
        int badPit = 0;
        for (int i = 0; i < pitTerms.size(); i++) {
            Map<String, Object> ref = Json.obj(pitTerms.get(i));
            double[] refDx = Json.doubles(ref, "dx_deg");
            double[] refAmp = Json.doubles(ref, "amp");
            double[] gotDx = i < m.patches().size()
                    ? m.patches().get(i).pitOffsetsDeg() : new double[0];
            double[] gotAmp = i < m.patches().size()
                    ? m.patches().get(i).pitCoefs() : new double[0];
            if (gotDx.length != refDx.length) { ok = false; badPit++; continue; }
            for (int j = 0; j < refDx.length; j++) {
                double da = Math.abs(gotDx[j] - refDx[j]);
                maxPit = Math.max(maxPit, Math.max(da, Math.abs(gotAmp[j] - refAmp[j])));
                if (da > 1e-9 || !near(gotAmp[j], refAmp[j], rel, floor)) { ok = false; badPit++; }
            }
        }

        Map<String, Object> curve = Json.obj(exp.get("curve"));
        double[] ca = Json.doubles(curve, "angles_deg");
        double[] cr = Json.doubles(curve, "radii_mm");
        double[] got = m.eval(ca);
        double maxR = 0;
        for (int i = 0; i < cr.length; i++) maxR = Math.max(maxR, Math.abs(got[i] - cr[i]));
        if (maxR > Json.dbl(tol, "curve_mm")) ok = false;

        String detail = String.format("степени %s, коэфф. max|Δ| %.2e (плохих %d), "
                        + "термины ям max|Δ| %.2e (плохих %d), контур max|Δ| %.2e мм",
                degOk ? "совпали" : "РАСХОДЯТСЯ", maxC, badC, maxPit, badPit, maxR);
        return new Result(ok, detail, notes);
    }
}

