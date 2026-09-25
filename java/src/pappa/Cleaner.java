package pappa;

/**
 * Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
 * по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
 * Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py) и порты C/C++/Go/JS.
 */
public final class Cleaner {

    private Cleaner() { }

    public record Options(double baselineDeg, double iqrK, double maxRemovedFrac, int minPoints) {
        public static Options defaults() { return new Options(1.0, 3.0, 0.5, 20); }
    }

    public record Result(boolean[] mask, int nOutliers, int window) { }

    public static Result cleanIqr(double[] angles, double[] radii, Options o) {
        int n = radii.length;
        boolean[] mask = new boolean[n];
        if (n < o.minPoints()) return new Result(mask, 0, 0);

        int w = Signal.windowPoints(angles, o.baselineDeg());
        double[] base = Signal.medianFilterWrap(radii, w);
        double[] res = new double[n];
        for (int i = 0; i < n; i++) res[i] = radii[i] - base[i];

        double center = Signal.median(res);
        double spread = Signal.iqr(res);
        double denom = spread > 1e-12 ? spread : 1.0;   // защита референса (spec/conformance/README)

        double[] sev = new double[n];
        int flagged = 0;
        for (int i = 0; i < n; i++) {
            sev[i] = Math.abs(res[i] - center) / denom;
            mask[i] = sev[i] > o.iqrK();
            if (mask[i]) flagged++;
        }

        // Предохранитель: не выбрасываем больше maxRemovedFrac точек.
        int cap = (int) Math.floor(o.maxRemovedFrac() * n);
        if (cap > 0 && cap < n && flagged > cap) {
            double[] kept = new double[flagged];
            int k = 0;
            for (int i = 0; i < n; i++) if (mask[i]) kept[k++] = sev[i];
            java.util.Arrays.sort(kept);
            double level = kept[kept.length - cap];
            flagged = 0;
            for (int i = 0; i < n; i++) {
                mask[i] = mask[i] && sev[i] >= level;
                if (mask[i]) flagged++;
            }
        }
        return new Result(mask, flagged, w);
    }
}
