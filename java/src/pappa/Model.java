package pappa;

import java.util.ArrayList;
import java.util.List;

/**
 * Модель PAPPA (Java): патчи с адаптивной степенью по нормированной координате,
 * smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
 * Совпадает с референсом Python и портами C/C++/Go/JS: тот же базис, та же политика
 * степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней — ОДНИМ
 * накоплением Грама в базисе Чебышёва + RMSE по явным остаткам.
 */
public final class Model {

    public record Options(int nPatches, double phaseDeg, int degMin, int degMax,
                          double overlapTrain, double overlapUse, double degElbowTol,
                          double amplitudeScale, String coordMode) {
        public static Options defaults() {
            return new Options(7, 24.75, 4, 14, 15.0, 5.0, 0.05, 180.0, "normalized");
        }
    }

    public record PitShape(double sigmaDeg, double coreSigma, double windowSigma,
                           double pitMinAmp, boolean tapering) {
        public static PitShape defaults() { return new PitShape(3.0, 2.0, 3.2, 3e-3, true); }
    }

    public record Metrics(double amplitudeMm, double meanRadiusMm, double amplitudeNorm,
                          double degElbowTol, double rmseSelectedMm, double rmseBestMm,
                          int nTrainPoints) { }

    public record Stats(double rmseMm, double maeMm, double maxErrMm, double correlation) { }

    public record Patch(double centerDeg, int degree, int nPoints, double[] coefs,
                        double[] pitOffsetsDeg, double[] pitCoefs,
                        Metrics metrics, Stats stats) { }

    private final Options opt;
    private PitShape pit = PitShape.defaults();
    private double[] pits = new double[0];
    private final List<Patch> patches = new ArrayList<>();
    private double[] centers = new double[0];
    private double halfSector;
    private boolean fitted;

    public Model(Options opt) { this.opt = opt; }

    public Model(Options opt, double[] pitsDeg) {
        this.opt = opt;
        setPits(pitsDeg);
    }

    public void setPits(double[] centersDeg) {
        pits = new double[centersDeg.length];
        for (int i = 0; i < centersDeg.length; i++) {
            pits[i] = ((centersDeg[i] % 360) + 360) % 360;
        }
    }

    public void setPitShape(PitShape shape) { this.pit = shape; }

    public boolean hasPits() { return pits.length > 0; }

    public double[] pits() { return pits; }

    public Options options() { return opt; }

    public PitShape pitShape() { return pit; }

    public List<Patch> patches() { return patches; }

    public double halfSector() { return halfSector; }

    public double halfTrain() { return halfSector + opt.overlapTrain(); }

    public double halfUse() { return halfSector + opt.overlapUse(); }

    public boolean isFitted() { return fitted; }

    /** Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg). */
    public double pitShapeDeg(double dDeg) {
        double d = Math.abs(dDeg);
        double val = Math.exp(-(d * d) / (2 * pit.sigmaDeg() * pit.sigmaDeg()));
        if (!pit.tapering()) return val;
        double core = pit.coreSigma() * pit.sigmaDeg();
        double edge = pit.windowSigma() * pit.sigmaDeg();
        if (edge <= core) return val;
        double t = (edge - d) / (edge - core);
        t = Math.min(1, Math.max(0, t));
        return val * t * t * (3 - 2 * t);
    }

    /** Смещения видимых ям в локальной системе патча (°). */
    public double[] pitOffsets(double centerDeg, double halfWinDeg) {
        List<Double> out = new ArrayList<>();
        for (double p : pits) {
            double dx = Signal.circLocal(p, centerDeg);
            if (Math.abs(dx) <= halfWinDeg) out.add(dx);
        }
        double[] a = new double[out.size()];
        for (int i = 0; i < a.length; i++) a[i] = out.get(i);
        return a;
    }

    public double weight(double dDeg, double halfUse) {
        if (dDeg <= halfSector) return 1;
        if (dDeg <= halfUse) {
            double t = 1 - (dDeg - halfSector) / (halfUse - halfSector);
            return Signal.smoothstep(t);
        }
        return 0;
    }

    public int[] degrees() {
        int[] d = new int[patches.size()];
        for (int i = 0; i < d.length; i++) d[i] = patches.get(i).degree();
        return d;
    }

    private record DegreeChoice(int deg, double rmseSelected, double rmseBest, int nTrain) { }

    /**
     * Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
     * не хуже лучшей более чем на degElbowTol. Быстрая ветка (normalized) — одно
     * накопление Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
     */
    private DegreeChoice estimateDegree(double[] xs, double[] ys) {
        int n = xs.length;
        if (n < 5) return new DegreeChoice(opt.degMin(), 0, 0, n);

        List<Integer> degs = new ArrayList<>();
        List<Double> rmses = new ArrayList<>();
        int bestDeg = opt.degMin();
        double best = Double.POSITIVE_INFINITY;

        if ("raw".equals(opt.coordMode())) {
            // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
            for (int deg = opt.degMin(); deg <= opt.degMax(); deg += 2) {
                double[][] a = new double[n][deg + 1];
                for (int i = 0; i < n; i++) {
                    double p = 1;
                    for (int j = 0; j <= deg; j++) {
                        a[i][deg - j] = p;
                        p *= xs[i];
                    }
                }
                double[] c = Linalg.lstsqQR(a, ys);
                double sse = 0;
                for (int i = 0; i < n; i++) {
                    double e = Linalg.polyval(c, xs[i]) - ys[i];
                    sse += e * e;
                }
                double r = Math.sqrt(sse / n);
                degs.add(deg);
                rmses.add(r);
                if (r < best) { best = r; bestDeg = deg; }
            }
        } else {
            int dmax = opt.degMax();
            int p = dmax + 1;
            double yref = 0;
            for (double v : ys) yref += v;
            yref /= n;
            double[][] gram = new double[p][p];
            double[] rhs = new double[p];
            for (int i = 0; i < n; i++) {
                double[] t = Linalg.chebRow(xs[i], dmax);
                double yc = ys[i] - yref;
                for (int a = 0; a < p; a++) {
                    rhs[a] += t[a] * yc;
                    for (int c = a; c < p; c++) gram[a][c] += t[a] * t[c];
                }
            }
            for (int a = 0; a < p; a++) {
                for (int c = a + 1; c < p; c++) gram[c][a] = gram[a][c];
            }
            for (int deg = opt.degMin(); deg <= dmax; deg += 2) {
                int nn = deg + 1;
                double[][] a = new double[nn][nn];
                double[] b = new double[nn];
                for (int r = 0; r < nn; r++) {
                    System.arraycopy(gram[r], 0, a[r], 0, nn);
                    b[r] = rhs[r];
                }
                double[] c = Linalg.lstsqQR(a, b);
                double sse = 0;
                for (int i = 0; i < n; i++) {
                    double e = Linalg.chebSum(c, deg, xs[i]) - (ys[i] - yref);
                    sse += e * e;
                }
                double r = Math.sqrt(sse / n);
                degs.add(deg);
                rmses.add(r);
                if (r < best) { best = r; bestDeg = deg; }
            }
        }

        double limit = best * (1 + opt.degElbowTol());
        int sel = bestDeg;
        double rmseSel = best;
        for (int k = 0; k < degs.size(); k++) {          // степени по возрастанию
            if (rmses.get(k) <= limit) { sel = degs.get(k); rmseSel = rmses.get(k); break; }
        }
        return new DegreeChoice(sel, rmseSel, best, n);
    }

    /** Точки обучающего окна патча (локальная координата: нормированная или сырая). */
    private record Window(double[] xs, double[] ys) { }

    private Window windowOf(double[] angles, double[] radii, double center) {
        double half = halfTrain();
        boolean norm = !"raw".equals(opt.coordMode());
        List<Double> xs = new ArrayList<>();
        List<Double> ys = new ArrayList<>();
        for (double shift : new double[] { -360, 0, 360 }) {
            for (int i = 0; i < angles.length; i++) {
                double dx = angles[i] + shift - center;
                if (dx >= -half && dx <= half) {
                    xs.add(norm ? dx / half : dx);
                    ys.add(radii[i]);
                }
            }
        }
        double[] ax = new double[xs.size()];
        double[] ay = new double[ys.size()];
        for (int i = 0; i < ax.length; i++) {
            ax[i] = xs.get(i);
            ay[i] = ys.get(i);
        }
        return new Window(ax, ay);
    }

    public Model fit(double[] angles, double[] radii) {
        if (angles.length != radii.length) {
            throw new IllegalArgumentException("fit: длины не совпадают");
        }
        if (angles.length < 10) throw new IllegalArgumentException("fit: слишком мало точек");

        double sector = 360.0 / opt.nPatches();
        halfSector = sector / 2;
        centers = new double[opt.nPatches()];
        for (int i = 0; i < opt.nPatches(); i++) {
            double c = (i * sector + halfSector + opt.phaseDeg()) % 360;
            if (c < 0) c += 360;
            centers[i] = c;
        }
        double halfTrain = halfTrain();
        patches.clear();

        for (double c : centers) {
            Window win = windowOf(angles, radii, c);
            double[] xs = win.xs();
            double[] ys = win.ys();
            int n = xs.length;
            if (n < 5) continue;
            DegreeChoice est = estimateDegree(xs, ys);
            int deg = est.deg();

            double[] offs = pitOffsets(c, halfTrain);
            int ncol = deg + 1 + offs.length;
            double[][] a = new double[n][ncol];
            for (int i = 0; i < n; i++) {
                double p = 1;
                for (int k = deg; k >= 0; k--) {
                    a[i][k] = p;
                    p *= xs[i];
                }
                for (int j = 0; j < offs.length; j++) {
                    a[i][deg + 1 + j] = pitShapeDeg(Math.abs(xs[i] * halfTrain - offs[j]));
                }
            }
            double[] coef = Linalg.lstsqQR(a, ys);
            double[] polyCoef = new double[deg + 1];
            System.arraycopy(coef, 0, polyCoef, 0, deg + 1);

            // Отсечка ям, которые в окне патча «не видны» (pitMinAmp).
            List<Double> ko = new ArrayList<>();
            List<Double> kc = new ArrayList<>();
            for (int j = 0; j < offs.length; j++) {
                double maxAbs = 0;
                for (int i = 0; i < n; i++) {
                    double dDeg = Math.abs(xs[i] * halfTrain - offs[j]);
                    maxAbs = Math.max(maxAbs, Math.abs(coef[deg + 1 + j] * pitShapeDeg(dDeg)));
                }
                if (maxAbs >= pit.pitMinAmp()) {
                    ko.add(offs[j]);
                    kc.add(coef[deg + 1 + j]);
                }
            }
            double[] keptOffsets = new double[ko.size()];
            double[] keptCoefs = new double[kc.size()];
            for (int j = 0; j < ko.size(); j++) {
                keptOffsets[j] = ko.get(j);
                keptCoefs[j] = kc.get(j);
            }
            patches.add(buildPatch(c, deg, xs, ys, polyCoef, keptOffsets, keptCoefs,
                    est, angles, radii));
        }
        fitted = true;
        return this;
    }

    /** Метрики и статистика патча по его обучающему окну (полный базис). */
    private Patch buildPatch(double c, int deg, double[] xs, double[] ys, double[] polyCoef,
                             double[] keptOffsets, double[] keptCoefs, DegreeChoice est,
                             double[] angles, double[] radii) {
        int n = xs.length;
        double sse = 0;
        double sae = 0;
        double mx = 0;
        double[] fitVals = new double[n];
        for (int i = 0; i < n; i++) {
            double v = Linalg.polyval(polyCoef, xs[i]);
            for (int j = 0; j < keptOffsets.length; j++) {
                v += keptCoefs[j] * pitShapeDeg(Math.abs(xs[i] * halfTrain() - keptOffsets[j]));
            }
            fitVals[i] = v;
            double e = v - ys[i];
            sse += e * e;
            sae += Math.abs(e);
            mx = Math.max(mx, Math.abs(e));
        }
        double mf = 0;
        double my = 0;
        for (int i = 0; i < n; i++) {
            mf += fitVals[i];
            my += ys[i];
        }
        mf /= n;
        my /= n;
        double cov = 0;
        double vf = 0;
        double vy = 0;
        for (int i = 0; i < n; i++) {
            double df = fitVals[i] - mf;
            double dy = ys[i] - my;
            cov += df * dy;
            vf += df * df;
            vy += dy * dy;
        }
        double corr = (vf > 0 && vy > 0) ? cov / Math.sqrt(vf * vy) : 0;

        // Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
        List<Double> secList = new ArrayList<>();
        for (int i = 0; i < angles.length; i++) {
            if (Signal.circDist(angles[i], c) <= halfSector) secList.add(radii[i]);
        }
        double amp = 0;
        double meanSec = 0;
        if (secList.size() >= 5) {
            double[] sec = new double[secList.size()];
            for (int i = 0; i < sec.length; i++) sec[i] = secList.get(i);
            amp = Signal.percentileLinear(sec, 95) - Signal.percentileLinear(sec, 5);
            for (double v : sec) meanSec += v;
            meanSec /= sec.length;
        }

        Metrics metrics = new Metrics(amp, meanSec, meanSec > 0 ? amp / meanSec : 0,
                opt.degElbowTol(), est.rmseSelected(), est.rmseBest(), n);
        Stats stats = new Stats(Math.sqrt(sse / n), sae / n, mx, corr);
        return new Patch(c, deg, n, polyCoef, keptOffsets, keptCoefs, metrics, stats);
    }

    /** Контур: нормированное smoothstep-смешивание патчей (partition of unity). */
    public double[] evalPart(double[] angles, String part) {
        if (!fitted) throw new IllegalStateException("Сначала вызовите fit()");
        double halfUse = halfUse();
        double halfTrain = halfTrain();
        double[] out = new double[angles.length];
        for (int k = 0; k < angles.length; k++) {
            double a = angles[k];
            double sumWv = 0;
            double sumW = 0;
            for (Patch p : patches) {
                double w = weight(Signal.circDist(a, p.centerDeg()), halfUse);
                if (w <= 0) continue;
                double dx = Signal.circLocal(a, p.centerDeg());
                double x = "raw".equals(opt.coordMode()) ? dx : dx / halfTrain;
                double v = 0;
                if (!"pit".equals(part)) v += Linalg.polyval(p.coefs(), x);
                if (!"poly".equals(part)) {
                    for (int j = 0; j < p.pitOffsetsDeg().length; j++) {
                        double dDeg = Math.abs(x * halfTrain - p.pitOffsetsDeg()[j]);
                        v += p.pitCoefs()[j] * pitShapeDeg(dDeg);
                    }
                }
                sumWv += w * v;
                sumW += w;
            }
            out[k] = sumW > 0 ? sumWv / sumW : 0;
        }
        return out;
    }

    public double[] eval(double[] angles) { return evalPart(angles, "total"); }
}

