// Сигнальные утилиты порта — поведение как у numpy и как в портах C/C++/Go:
// медиана (чётное n — среднее двух центральных), перцентиль с линейной
// интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
// Зависимостей нет: только стандартный JavaScript.

export function sortInPlace(x) {
  x.sort((a, b) => a - b);
  return x;
}

// Медиана: чётное n — среднее двух центральных (numpy.median).
export function median(values) {
  const n = values.length;
  if (n === 0) return 0;
  const v = sortInPlace(values.slice());
  return n % 2 === 1 ? v[(n - 1) / 2] : 0.5 * (v[n / 2 - 1] + v[n / 2]);
}

// Перцентиль с линейной интерполяцией (numpy.percentile).
export function percentileLinear(values, q) {
  const n = values.length;
  if (n === 0) return 0;
  const v = sortInPlace(values.slice());
  const pos = (q / 100) * (n - 1);
  const lo = Math.floor(pos);
  const frac = pos - lo;
  const hi = Math.min(lo + 1, n - 1);
  return v[lo] + frac * (v[hi] - v[lo]);
}

export function iqr(values) {
  if (values.length === 0) return 0;
  return percentileLinear(values, 75) - percentileLinear(values, 25);
}

export function mad(values) {
  if (values.length === 0) return 0;
  const m = median(values);
  return median(values.map((v) => Math.abs(v - m)));
}

export function robustSigma(values) {
  return 1.4826 * mad(values);
}

// Медианный шаг сетки по углам (медиана положительных разностей, иначе 1).
export function angularStep(angles) {
  if (angles.length < 2) return 1;
  const d = [];
  for (let i = 1; i < angles.length; i++) {
    const s = angles[i] - angles[i - 1];
    if (s > 0) d.push(s);
  }
  return d.length === 0 ? 1 : median(d);
}

// Ширина окна в точках: llround(span/шаг), нечётная, не шире массива.
export function windowPoints(angles, spanDeg) {
  const n = angles.length;
  if (n < 3) return Math.max(1, n);
  let w = Math.round(spanDeg / angularStep(angles));
  if (w % 2 === 0) w += 1;
  if (w < 3) w = 3;
  if (w > n) w = n % 2 === 1 ? n : n - 1;
  return Math.max(3, w);
}

// Медианный фильтр по кольцу (окно в точках).
export function medianFilterWrap(x, window) {
  const n = x.length;
  let w = window % 2 === 0 ? window + 1 : window;
  if (w < 3) w = 3;
  if (w > n) w = n % 2 === 1 ? n : n - 1;
  const out = new Array(n).fill(0);
  if (w < 3 || n < 3) {
    const m = median(x);
    return out.fill(m);
  }
  const h = (w - 1) / 2;
  const win = new Array(w);
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < w; k++) {
      win[k] = x[((i - h + k) % n + n) % n];   // замыкание кольца
    }
    out[i] = median(win);
  }
  return out;
}

// Скользящее среднее по кольцу (окно в точках).
export function smoothWrap(x, window) {
  const n = x.length;
  let w = window % 2 === 0 ? window + 1 : window;
  if (w < 3) w = 3;
  if (n < 3 || w > n) w = n % 2 === 1 ? n : n - 1;
  if (w < 3) return x.slice();
  const h = (w - 1) / 2;
  const out = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    let s = 0;
    for (let k = -h; k <= h; k++) s += x[((i + k) % n + n) % n];
    out[i] = s / w;
  }
  return out;
}

export function circDist(a, b) {
  let d = ((a - b + 180) % 360 + 360) % 360;
  return Math.abs(d - 180);
}

export function circLocal(a, b) {
  let d = ((a - b + 180) % 360 + 360) % 360;
  return d - 180;
}

export function smoothstep(t) {
  if (t < 0) return 0;
  if (t > 1) return 1;
  return t * t * (3 - 2 * t);
}
