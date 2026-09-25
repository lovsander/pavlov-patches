package pappa;

import java.util.ArrayList;
import java.util.List;

/**
 * Детектор ям (трещин) — повторение python/pappa/analysis/zones.py и портов:
 *   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
 *   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
 *   зоны = участки, где индикатор > k, длиной не короче minZoneDeg.
 */
public final class Detector {

    private Detector() { }

    public record Options(double windowDeg, double wideDeg, double smoothDeg,
                          double k, double minZoneDeg) {
        public static Options defaults() { return new Options(1.0, 10.0, 2.0, 5.5, 2.0); }
    }

    public static double[] bandIndicator(double[] angles, double[] radii, Options o) {
        int n = radii.length;
        int wNarrow = Signal.windowPoints(angles, o.windowDeg());
        int wWide = Signal.windowPoints(angles, o.wideDeg());
        int wSmooth = Signal.windowPoints(angles, o.smoothDeg());

        double[] narrow = Signal.medianFilterWrap(radii, wNarrow);
        double[] wide = Signal.medianFilterWrap(radii, wWide);
        double[] band = new double[n];
        for (int i = 0; i < n; i++) band[i] = Math.abs(narrow[i] - wide[i]);

        double[] out = Signal.smoothWrap(band, wSmooth);
        double s = Signal.robustSigma(out);
        if (s > 1e-12) {
            for (int i = 0; i < n; i++) out[i] /= s;
        } else {
            java.util.Arrays.fill(out, 0);
        }
        return out;
    }

    /** Непрерывные зоны по маске: {{начало, конец}, ...} в градусах. */
    public static double[][] maskToZones(double[] angles, boolean[] mask, Options o) {
        int n = angles.length;
        boolean any = false;
        for (boolean b : mask) any |= b;
        if (!any) return new double[0][];

        double[] diffs = new double[Math.max(0, n - 1)];
        for (int i = 1; i < n; i++) diffs[i - 1] = angles[i] - angles[i - 1];
        double step = diffs.length > 0 ? Signal.median(diffs) : 1;

        List<double[]> zones = new ArrayList<>();
        int i = 0;
        while (i < n) {
            if (!mask[i]) { i++; continue; }
            int j = i;
            while (j + 1 < n && mask[j + 1]) j++;
            zones.add(new double[] { angles[i] - step / 2, angles[j] + step / 2 });
            i = j + 1;
        }

        // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
        if (zones.size() > 1 && mask[0] && mask[n - 1]) {
            double[] first = zones.get(0);
            double[] last = zones.get(zones.size() - 1);
            List<double[]> merged = new ArrayList<>();
            merged.add(new double[] { last[0] - 360, first[1] });
            merged.addAll(zones.subList(1, zones.size() - 1));
            zones = merged;
        }

        List<double[]> kept = new ArrayList<>();
        for (double[] z : zones) if (z[1] - z[0] >= o.minZoneDeg()) kept.add(z);
        return kept.toArray(new double[0][]);
    }

    public static double[][] zones(double[] angles, double[] values, Options o) {
        boolean[] mask = new boolean[values.length];
        for (int i = 0; i < values.length; i++) mask[i] = values[i] > o.k();
        return maskToZones(angles, mask, o);
    }

    /** Центры ям (°) — середины найденных зон. */
    public static double[] pits(double[] angles, double[] radii, Options o) {
        double[] band = bandIndicator(angles, radii, o);
        double[][] zs = zones(angles, band, o);
        double[] out = new double[zs.length];
        for (int i = 0; i < zs.length; i++) out[i] = 0.5 * (zs[i][0] + zs[i][1]);
        return out;
    }
}
