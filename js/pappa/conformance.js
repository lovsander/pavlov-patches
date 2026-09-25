// Проверка порта по конформанс-векторам (spec/conformance/vectors).
// Допуски — те же, что у C++/Go/C: контур 1e-6 мм, коэффициенты
// max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { PatchApproximator } from './model.js';
import { bandIndicator, zones } from './detector.js';
import { cleanIqr } from './cleaner.js';

export function loadVectors(vecDir) {
  return readdirSync(vecDir).filter((f) => f.endsWith('.json')).sort()
    .map((f) => ({ file: f, vector: JSON.parse(readFileSync(join(vecDir, f), 'utf8')) }));
}

const near = (a, b, rel, floor) => Math.abs(a - b) <= Math.max(floor, rel * Math.abs(b));

export function checkModel(v) {
  const cfg = v.config;
  const exp = v.expected;
  const tol = v.tolerance;
  const notes = [];

  const m = new PatchApproximator({
    nPatches: cfg.n_patches,
    phaseDeg: cfg.phase_deg,
    degMin: cfg.deg_min,
    degMax: cfg.deg_max,
    overlapTrain: cfg.overlap_train,
    overlapUse: cfg.overlap_use,
    degElbowTol: cfg.deg_elbow_tol,
    coordMode: cfg.coord_mode,
  });
  if (cfg.pits_deg && cfg.pits_deg.length) {
    m.setPitShape({
      sigmaDeg: cfg.sigma_deg,
      coreSigma: cfg.pit_core_sigma,
      windowSigma: cfg.pit_window_sigma,
      pitMinAmp: cfg.pit_min_amp,
      tapering: cfg.tapering,
    });
    m.setPits(cfg.pits_deg);
  }
  m.fit(v.input.angles_deg, v.input.radii_mm);

  let ok = true;
  const gotDeg = m.getDegrees();
  const degOk = gotDeg.length === exp.degrees.length
    && gotDeg.every((d, i) => d === exp.degrees[i]);
  if (!degOk) { ok = false; notes.push(`степени ${gotDeg} != ${exp.degrees}`); }

  let maxC = 0;
  let badC = 0;
  exp.coefs.forEach((ref, i) => {
    const got = m.patches[i] ? m.patches[i].coefs : [];
    if (got.length !== ref.length) { ok = false; badC++; return; }
    ref.forEach((r, j) => {
      const d = Math.abs(got[j] - r);
      maxC = Math.max(maxC, d);
      if (!near(got[j], r, tol.coefs_rel, tol.coefs_abs_floor)) { ok = false; badC++; }
    });
  });

  let maxPit = 0;
  let badPit = 0;
  exp.pit_terms.forEach((ref, i) => {
    const got = m.patches[i]
      ? { dx_deg: m.patches[i].pitOffsets, amp: m.patches[i].pitCoefs }
      : { dx_deg: [], amp: [] };
    if (got.dx_deg.length !== ref.dx_deg.length) { ok = false; badPit++; return; }
    ref.dx_deg.forEach((r, j) => {
      const da = Math.abs(got.dx_deg[j] - r);
      const dp = Math.abs(got.amp[j] - ref.amp[j]);
      maxPit = Math.max(maxPit, da, dp);
      if (da > 1e-9 || !near(got.amp[j], ref.amp[j], tol.coefs_rel, tol.coefs_abs_floor)) {
        ok = false; badPit++;
      }
    });
  });

  const curve = m.eval(exp.curve.angles_deg);
  let maxR = 0;
  exp.curve.radii_mm.forEach((r, i) => { maxR = Math.max(maxR, Math.abs(curve[i] - r)); });
  if (maxR > tol.curve_mm) ok = false;

  const detail = `степени ${degOk ? 'совпали' : 'РАСХОДЯТСЯ'}, `
    + `коэфф. max|Δ| ${maxC.toExponential(2)} (плохих ${badC}), `
    + `термины ям max|Δ| ${maxPit.toExponential(2)} (плохих ${badPit}), `
    + `контур max|Δ| ${maxR.toExponential(2)} мм`;
  return { ok, detail, notes };
}

export function checkDetector(v) {
  const cfg = v.config;
  const exp = v.expected;
  const band = bandIndicator(v.input.angles_deg, v.input.radii_mm, {
    windowDeg: cfg.window_deg,
    wideDeg: cfg.wide_deg,
    smoothDeg: cfg.smooth_deg,
    k: cfg.k,
    minZoneDeg: cfg.min_zone_deg,
  });
  const zn = zones(v.input.angles_deg, band, { minZoneDeg: cfg.min_zone_deg });
  const notes = [];
  let ok = zn.length === exp.zones_deg.length;
  if (!ok) notes.push(`зон ${zn.length} != ${exp.zones_deg.length}`);
  let dev = 0;
  exp.zones_deg.forEach(([a0, a1], i) => {
    if (i < zn.length) dev = Math.max(dev, Math.abs(zn[i][0] - a0), Math.abs(zn[i][1] - a1));
  });
  const centers = zn.map(([a, b]) => 0.5 * (a + b));
  if (centers.length !== exp.pits_deg.length) {
    ok = false;
    notes.push(`ям ${centers.length} != ${exp.pits_deg.length}`);
  }
  exp.pits_deg.forEach((p, i) => {
    if (i < centers.length) {
      const d = Math.abs(centers[i] - p);
      dev = Math.max(dev, d);
      if (d > 1e-6) ok = false;
    }
  });
  const detail = `зон ${zn.length}/${exp.zones_deg.length}, `
    + `ям ${centers.length}/${exp.pits_deg.length}, max|Δ| ${dev.toExponential(2)}°`;
  return { ok, detail, notes };
}

export function checkCleaner(v) {
  const cfg = v.config;
  const exp = v.expected;
  const { mask, nOutliers } = cleanIqr(v.input.angles_deg, v.input.radii_mm, {
    baselineDeg: cfg.baseline_deg,
    iqrK: cfg.iqr_k,
  });
  const n = mask.length;
  const got = new Set();
  mask.forEach((b, i) => { if (b) got.add(i); });
  const ref = new Set(exp.mask_true_indices);
  const tol = Math.max(1, Math.floor(Number(v.tolerance.frac ?? 0.02) * n));
  let extra = 0;
  let missing = 0;
  for (const i of got) if (!ref.has(i)) extra++;
  for (const i of ref) if (!got.has(i)) missing++;
  const ok = extra <= tol && missing <= tol && Math.abs(got.size - exp.n_outliers) <= tol;
  const detail = `выбросов ${got.size} (эталон ${exp.n_outliers}), `
    + `лишних ${extra}, пропущено ${missing}`;
  return { ok, detail, notes: [] };
}

export function checkVector(v) {
  if (v.kind === 'model') return checkModel(v);
  if (v.kind === 'detector') return checkDetector(v);
  return checkCleaner(v);
}
