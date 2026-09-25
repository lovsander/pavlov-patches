// Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
// по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
// Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py) и порты.
import { medianFilterWrap, median, iqr, windowPoints } from './signal.js';

export const CLEANER_DEFAULTS = {
  baselineDeg: 1.0,
  iqrK: 3.0,
  maxRemovedFrac: 0.5,
  minPoints: 20,
};

export function cleanIqr(angles, radii, options = {}) {
  const o = { ...CLEANER_DEFAULTS, ...options };
  const n = radii.length;
  const mask = new Array(n).fill(false);
  if (n < o.minPoints) return { mask, nOutliers: 0, window: 0 };

  const w = windowPoints(angles, o.baselineDeg);
  const base = medianFilterWrap(radii, w);
  const res = radii.map((r, i) => r - base[i]);
  const center = median(res);
  const spread = iqr(res);
  const denom = spread > 1e-12 ? spread : 1.0;   // защита референса (см. spec/conformance/README)
  const sev = res.map((r) => Math.abs(r - center) / denom);
  for (let i = 0; i < n; i++) mask[i] = sev[i] > o.iqrK;

  // Предохранитель: не выбрасываем больше maxRemovedFrac точек.
  const cap = Math.floor(o.maxRemovedFrac * n);
  const flagged = mask.reduce((s, b) => s + (b ? 1 : 0), 0);
  if (cap > 0 && cap < n && flagged > cap) {
    const kept = sev.filter((_, i) => mask[i]).sort((a, b) => a - b);
    const level = kept[kept.length - cap];
    for (let i = 0; i < n; i++) mask[i] = mask[i] && sev[i] >= level;
  }
  return { mask, nOutliers: mask.reduce((s, b) => s + (b ? 1 : 0), 0), window: w };
}
