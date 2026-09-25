// Детектор ям (трещин) — повторение python/pappa/analysis/zones.py и портов:
//   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
//   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
//   зоны = участки, где индикатор > k, длиной не короче minZoneDeg.
import {
  medianFilterWrap, smoothWrap, robustSigma, windowPoints, median,
} from './signal.js';

export const DETECTOR_DEFAULTS = {
  windowDeg: 1.0,     // узкая медиана
  wideDeg: 10.0,      // широкая медиана
  smoothDeg: 2.0,     // сглаживание индикатора
  k: 5.5,             // порог в MAD-ах
  minZoneDeg: 2.0,    // минимальная длина зоны
};

export function bandIndicator(angles, radii, options = {}) {
  const o = { ...DETECTOR_DEFAULTS, ...options };
  const wNarrow = windowPoints(angles, o.windowDeg);
  const wWide = windowPoints(angles, o.wideDeg);
  const wSmooth = windowPoints(angles, o.smoothDeg);

  const narrow = medianFilterWrap(radii, wNarrow);
  const wide = medianFilterWrap(radii, wWide);
  const band = radii.map((_, i) => Math.abs(narrow[i] - wide[i]));
  const out = smoothWrap(band, wSmooth);

  const s = robustSigma(out);
  if (s > 1e-12) {
    for (let i = 0; i < out.length; i++) out[i] /= s;
  } else {
    out.fill(0);
  }
  return out;
}

// Непрерывные зоны по маске: [[начало, конец], ...] в градусах.
export function maskToZones(angles, mask, options = {}) {
  const o = { ...DETECTOR_DEFAULTS, ...options };
  const n = angles.length;
  if (!mask.some(Boolean)) return [];

  const diffs = [];
  for (let i = 1; i < n; i++) diffs.push(angles[i] - angles[i - 1]);
  const step = diffs.length ? median(diffs) : 1;

  let zones = [];
  let i = 0;
  while (i < n) {
    if (!mask[i]) { i++; continue; }
    let j = i;
    while (j + 1 < n && mask[j + 1]) j++;
    zones.push([angles[i] - step / 2, angles[j] + step / 2]);
    i = j + 1;
  }

  // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
  if (zones.length > 1 && mask[0] && mask[n - 1]) {
    const first = zones[0];
    const last = zones[zones.length - 1];
    zones = [[last[0] - 360, first[1]], ...zones.slice(1, -1)];
  }
  return zones.filter(([a, b]) => b - a >= o.minZoneDeg);
}

export function zones(angles, values, options = {}) {
  const o = { ...DETECTOR_DEFAULTS, ...options };
  return maskToZones(angles, values.map((v) => v > o.k), o);
}

// Центры ям (°) — середины найденных зон.
export function pits(angles, radii, options = {}) {
  const band = bandIndicator(angles, radii, options);
  return zones(angles, band, options).map(([a, b]) => 0.5 * (a + b));
}
