// Линейная алгебра порта: МНК через QR отражениями Хаусхолдера (как np.polyfit /
// np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени.
// A — массив строк (m×n), b — длина m; возвращает коэффициенты длины n.

export function lstsqQR(A, b) {
  const m = A.length;
  if (m === 0) throw new Error('lstsqQR: пустая матрица');
  const n = A[0].length;
  if (b.length !== m) throw new Error('lstsqQR: длины A и b не совпадают');
  if (m < n) throw new Error('lstsqQR: нужно m >= n');

  for (let k = 0; k < n; k++) {
    let norm = 0;
    for (let i = k; i < m; i++) norm += A[i][k] * A[i][k];
    norm = Math.sqrt(norm);
    if (norm < 1e-300) continue;

    const alpha = A[k][k] > 0 ? -norm : norm;
    const v = new Array(m).fill(0);
    for (let i = k; i < m; i++) v[i] = A[i][k];
    v[k] -= alpha;
    let vnorm2 = 0;
    for (let i = k; i < m; i++) vnorm2 += v[i] * v[i];
    if (vnorm2 < 1e-300) continue;

    for (let j = k; j < n; j++) {
      let s = 0;
      for (let i = k; i < m; i++) s += v[i] * A[i][j];
      const c = (2 * s) / vnorm2;
      for (let i = k; i < m; i++) A[i][j] -= c * v[i];
    }
    let sb = 0;
    for (let i = k; i < m; i++) sb += v[i] * b[i];
    const cb = (2 * sb) / vnorm2;
    for (let i = k; i < m; i++) b[i] -= cb * v[i];
  }

  const x = new Array(n).fill(0);
  for (let i = n - 1; i >= 0; i--) {
    let s = b[i];
    for (let j = i + 1; j < n; j++) s -= A[i][j] * x[j];
    const d = A[i][i];
    if (Math.abs(d) < 1e-300) throw new Error('lstsqQR: вырожденная система');
    x[i] = s / d;
  }
  return x;
}

// Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval в портах).
export function polyval(coefs, x) {
  let r = 0;
  for (const c of coefs) r = r * x + c;
  return r;
}

export function polyfit(xs, ys, deg) {
  const m = xs.length;
  const n = deg + 1;
  const A = [];
  for (let i = 0; i < m; i++) {
    const row = new Array(n).fill(0);
    let p = 1;
    for (let j = 0; j < n; j++) {
      row[n - 1 - j] = p;
      p *= xs[i];
    }
    A.push(row);
  }
  return lstsqQR(A, ys.slice());
}

// T_0(x)..T_degMax(x) — базис Чебышёва (x ∈ [-1, 1]).
export function chebRow(x, degMax) {
  const T = new Array(degMax + 1).fill(0);
  T[0] = 1;
  if (degMax >= 1) T[1] = x;
  for (let k = 2; k <= degMax; k++) T[k] = 2 * x * T[k - 1] - T[k - 2];
  return T;
}

// Сумма Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
export function chebSum(c, deg, x) {
  let b1 = 0;
  let b2 = 0;
  for (let k = deg; k >= 1; k--) {
    const b0 = 2 * x * b1 - b2 + c[k];
    b2 = b1;
    b1 = b0;
  }
  return x * b1 - b2 + c[0];
}
