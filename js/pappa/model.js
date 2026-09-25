// Модель PAPPA (JS): патчи с адаптивной степенью по нормированной координате,
// smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
// Совпадает с референсом Python и портами C/C++/Go: тот же базис, та же политика
// степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней — ОДНИМ
// накоплением Грама в базисе Чебышёва + RMSE по явным остаткам (наработка из
// embedded-экспериментов, см. docs/embedded.md §11-13).
import {
  circDist, circLocal, percentileLinear, median, iqr, robustSigma,
  windowPoints, smoothstep,
} from './signal.js';
import { chebRow, chebSum, lstsqQR, polyval } from './linalg.js';

export const MODEL_DEFAULTS = {
  nPatches: 7,
  phaseDeg: 24.75,
  degMin: 4,
  degMax: 14,
  overlapTrain: 15.0,
  overlapUse: 5.0,
  degElbowTol: 0.05,
  amplitudeScale: 180.0,
  coordMode: 'normalized',
};

export const PIT_DEFAULTS = {
  sigmaDeg: 3.0,
  coreSigma: 2.0,
  windowSigma: 3.2,
  pitMinAmp: 3e-3,
  tapering: true,
};

export class PatchApproximator {
  constructor(options = {}) {
    this.opt = { ...MODEL_DEFAULTS, ...options };
    this.pit = { ...PIT_DEFAULTS };
    this.pits = [];
    this.patches = [];
    this.centers = [];
    this.halfSector = 0;
    this.isFitted = false;
  }

  setPits(centersDeg) {
    this.pits = centersDeg.map((c) => ((c % 360) + 360) % 360);
  }

  setPitShape(shape = {}) {
    this.pit = { ...PIT_DEFAULTS, ...shape };
  }

  get hasPits() { return this.pits.length > 0; }
  get halfTrain() { return this.halfSector + this.opt.overlapTrain; }
  get halfUse() { return this.halfSector + this.opt.overlapUse; }

  // Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg).
  pitShapeDeg(dDeg) {
    const d = Math.abs(dDeg);
    const { sigmaDeg, coreSigma, windowSigma, tapering } = this.pit;
    const val = Math.exp(-(d * d) / (2 * sigmaDeg * sigmaDeg));
    if (!tapering) return val;
    const core = coreSigma * sigmaDeg;
    const edge = windowSigma * sigmaDeg;
    if (edge <= core) return val;
    let t = (edge - d) / (edge - core);
    t = Math.min(1, Math.max(0, t));
    return val * t * t * (3 - 2 * t);
  }

  // Смещения видимых ям в локальной системе патча (°).
  pitOffsets(centerDeg, halfWinDeg) {
    const out = [];
    for (const p of this.pits) {
      const dx = circLocal(p, centerDeg);
      if (Math.abs(dx) <= halfWinDeg) out.push(dx);
    }
    return out;
  }

  weight(dDeg, halfUse) {
    if (dDeg <= this.halfSector) return 1;
    if (dDeg <= halfUse) {
      const t = 1 - (dDeg - this.halfSector) / (halfUse - this.halfSector);
      return smoothstep(t);
    }
    return 0;
  }

  // Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна не
  // хуже лучшей более чем на degElbowTol. Быстрая ветка (normalized) — одно
  // накопление Грама в базисе Чебышёва + явные остатки (Кленшоу).
  estimateDegree(xs, ys) {
    const { degMin, degMax, degElbowTol, coordMode } = this.opt;
    const n = xs.length;
    if (n < 5) return { deg: degMin, rmseSelected: 0, rmseBest: 0, nTrain: n };

    const rows = [];
    let bestDeg = degMin;
    let best = Infinity;

    if (coordMode === 'raw') {
      // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
      for (let deg = degMin; deg <= degMax; deg += 2) {
        const A = [];
        for (let i = 0; i < n; i++) {
          const row = new Array(deg + 1);
          let p = 1;
          for (let j = 0; j <= deg; j++) { row[deg - j] = p; p *= xs[i]; }
          A.push(row);
        }
        const c = lstsqQR(A, ys.slice());
        let sse = 0;
        for (let i = 0; i < n; i++) {
          const e = polyval(c, xs[i]) - ys[i];
          sse += e * e;
        }
        const r = Math.sqrt(sse / n);
        rows.push([deg, r]);
        if (r < best) { best = r; bestDeg = deg; }
      }
    } else {
      const dmax = degMax;
      const p = dmax + 1;
      let yref = 0;
      for (const v of ys) yref += v;
      yref /= n;
      const gram = Array.from({ length: p }, () => new Array(p).fill(0));
      const rhs = new Array(p).fill(0);
      for (let i = 0; i < n; i++) {
        const T = chebRow(xs[i], dmax);
        const yc = ys[i] - yref;
        for (let a = 0; a < p; a++) {
          rhs[a] += T[a] * yc;
          for (let c = a; c < p; c++) gram[a][c] += T[a] * T[c];
        }
      }
      for (let a = 0; a < p; a++) {
        for (let c = a + 1; c < p; c++) gram[c][a] = gram[a][c];
      }

      for (let deg = degMin; deg <= dmax; deg += 2) {
        const nn = deg + 1;
        const A = [];
        const b = rhs.slice(0, nn);
        for (let r = 0; r < nn; r++) A.push(gram[r].slice(0, nn));
        const c = lstsqQR(A, b);
        let sse = 0;
        for (let i = 0; i < n; i++) {
          const e = chebSum(c, deg, xs[i]) - (ys[i] - yref);
          sse += e * e;
        }
        const r = Math.sqrt(sse / n);
        rows.push([deg, r]);
        if (r < best) { best = r; bestDeg = deg; }
      }
    }

    const limit = best * (1 + degElbowTol);
    let sel = bestDeg;
    for (const [deg, r] of rows) {
      if (r <= limit) { sel = deg; break; }   // строки по возрастанию степени
    }
    let rmseSelected = best;
    for (const [deg, r] of rows) if (deg === sel) rmseSelected = r;
    return { deg: sel, rmseSelected, rmseBest: best, nTrain: n };
  }


  // Точки обучающего окна патча: локальная координата (нормированная или сырая).
  windowOf(angles, radii, center) {
    const half = this.halfTrain;
    const norm = this.opt.coordMode !== 'raw';
    const xs = [];
    const ys = [];
    for (const shift of [-360, 0, 360]) {
      for (let i = 0; i < angles.length; i++) {
        const dx = angles[i] + shift - center;
        if (dx >= -half && dx <= half) {
          xs.push(norm ? dx / half : dx);
          ys.push(radii[i]);
        }
      }
    }
    return { xs, ys };
  }

  fit(angles, radii) {
    if (angles.length !== radii.length) throw new Error('fit: длины не совпадают');
    if (angles.length < 10) throw new Error('fit: слишком мало точек');
    const o = this.opt;
    const sector = 360 / o.nPatches;
    this.halfSector = sector / 2;
    this.centers = [];
    for (let i = 0; i < o.nPatches; i++) {
      let c = (i * sector + this.halfSector + o.phaseDeg) % 360;
      if (c < 0) c += 360;
      this.centers.push(c);
    }
    const halfTrain = this.halfTrain;
    const halfUse = this.halfUse;
    this.patches = [];

    for (const c of this.centers) {
      const { xs, ys } = this.windowOf(angles, radii, c);
      const n = xs.length;
      if (n < 5) continue;
      const est = this.estimateDegree(xs, ys);
      const deg = est.deg;

      const offs = this.pitOffsets(c, halfTrain);
      const ncol = deg + 1 + offs.length;
      const A = [];
      for (let i = 0; i < n; i++) {
        const row = new Array(ncol).fill(0);
        let p = 1;
        for (let k = deg; k >= 0; k--) { row[k] = p; p *= xs[i]; }
        for (let j = 0; j < offs.length; j++) {
          const dDeg = Math.abs(xs[i] * halfTrain - offs[j]);
          row[deg + 1 + j] = this.pitShapeDeg(dDeg);
        }
        A.push(row);
      }
      const coef = lstsqQR(A, ys.slice());
      const polyCoef = coef.slice(0, deg + 1);
      const pitCoef = coef.slice(deg + 1);

      // Отсечка ям, которые в окне патча «не видны» (pitMinAmp).
      const keptOffsets = [];
      const keptCoefs = [];
      for (let j = 0; j < offs.length; j++) {
        let maxAbs = 0;
        for (let i = 0; i < n; i++) {
          const dDeg = Math.abs(xs[i] * halfTrain - offs[j]);
          maxAbs = Math.max(maxAbs, Math.abs(pitCoef[j] * this.pitShapeDeg(dDeg)));
        }
        if (maxAbs >= this.pit.pitMinAmp) {
          keptOffsets.push(offs[j]);
          keptCoefs.push(pitCoef[j]);
        }
      }

      // Статистика по остаткам обучающего окна (по полному базису).
      let sse = 0;
      let sae = 0;
      let mx = 0;
      const fitVals = new Array(n).fill(0);
      for (let i = 0; i < n; i++) {
        let v = polyval(polyCoef, xs[i]);
        for (let j = 0; j < keptOffsets.length; j++) {
          const dDeg = Math.abs(xs[i] * halfTrain - keptOffsets[j]);
          v += keptCoefs[j] * this.pitShapeDeg(dDeg);
        }
        fitVals[i] = v;
        const e = v - ys[i];
        sse += e * e;
        sae += Math.abs(e);
        mx = Math.max(mx, Math.abs(e));
      }
      let mf = 0;
      let my = 0;
      for (let i = 0; i < n; i++) { mf += fitVals[i]; my += ys[i]; }
      mf /= n;
      my /= n;
      let cov = 0;
      let vf = 0;
      let vy = 0;
      for (let i = 0; i < n; i++) {
        const df = fitVals[i] - mf;
        const dy = ys[i] - my;
        cov += df * dy;
        vf += df * df;
        vy += dy * dy;
      }
      const corr = vf > 0 && vy > 0 ? cov / Math.sqrt(vf * vy) : 0;

      // Справочные метрики сектора: P95 - P5 и среднее по точкам сектора.
      const sec = [];
      for (let i = 0; i < angles.length; i++) {
        if (circDist(angles[i], c) <= this.halfSector) sec.push(radii[i]);
      }
      let amp = 0;
      let meanSec = 0;
      if (sec.length >= 5) {
        amp = percentileLinear(sec, 95) - percentileLinear(sec, 5);
        meanSec = sec.reduce((s, v) => s + v, 0) / sec.length;
      }

      this.patches.push({
        center: c,
        halfSector: this.halfSector,
        halfTrain,
        halfUse,
        coefs: polyCoef,
        degree: deg,
        nPoints: n,
        pitOffsets: keptOffsets,
        pitCoefs: keptCoefs,
        metrics: {
          amplitude_mm: amp,
          mean_radius_mm: meanSec,
          amplitude_norm: meanSec > 0 ? amp / meanSec : 0,
          deg_elbow_tol: o.degElbowTol,
          rmse_selected_mm: est.rmseSelected,
          rmse_best_mm: est.rmseBest,
          n_train_points: n,
        },
        stats: {
          rmse_mm: Math.sqrt(sse / n),
          mae_mm: sae / n,
          max_err_mm: mx,
          correlation: corr,
        },
      });
    }
    this.isFitted = true;
    return this;
  }

  // Контур: нормированное smoothstep-смешивание патчей (partition of unity).
  evalPart(angles, part = 'total') {
    if (!this.isFitted) throw new Error('Сначала вызовите fit()');
    const halfUse = this.halfUse;
    return angles.map((a) => {
      let sumWv = 0;
      let sumW = 0;
      for (const p of this.patches) {
        const w = this.weight(circDist(a, p.center), halfUse);
        if (w <= 0) continue;
        const dx = circLocal(a, p.center);
        const x = this.opt.coordMode === 'raw' ? dx : dx / p.halfTrain;
        let v = 0;
        if (part !== 'pit') v += polyval(p.coefs, x);
        if (part !== 'poly') {
          for (let j = 0; j < p.pitOffsets.length; j++) {
            const dDeg = Math.abs(x * p.halfTrain - p.pitOffsets[j]);
            v += p.pitCoefs[j] * this.pitShapeDeg(dDeg);
          }
        }
        sumWv += w * v;
        sumW += w;
      }
      return sumW > 0 ? sumWv / sumW : 0;
    });
  }

  eval(angles) { return this.evalPart(angles, 'total'); }

  getDegrees() { return this.patches.map((p) => p.degree); }
}
