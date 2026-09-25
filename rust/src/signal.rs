//! Сигнальные утилиты — поведение как у numpy и как в остальных портах:
//! медиана (чётное n — среднее двух центральных), перцентиль с линейной
//! интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.

/// Медиана: чётное n — среднее двух центральных (numpy.median).
pub fn median(values: &[f64]) -> f64 {
    let n = values.len();
    if n == 0 {
        return 0.0;
    }
    let mut v = values.to_vec();
    v.sort_by(f64::total_cmp);
    if n % 2 == 1 {
        v[n / 2]
    } else {
        0.5 * (v[n / 2 - 1] + v[n / 2])
    }
}

/// Перцентиль с линейной интерполяцией (numpy.percentile).
pub fn percentile_linear(values: &[f64], q: f64) -> f64 {
    let n = values.len();
    if n == 0 {
        return 0.0;
    }
    let mut v = values.to_vec();
    v.sort_by(f64::total_cmp);
    let pos = (q / 100.0) * (n as f64 - 1.0);
    let lo = pos.floor() as usize;
    let frac = pos - lo as f64;
    let hi = (lo + 1).min(n - 1);
    v[lo] + frac * (v[hi] - v[lo])
}

pub fn iqr(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    percentile_linear(values, 75.0) - percentile_linear(values, 25.0)
}

pub fn mad(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let m = median(values);
    let dev: Vec<f64> = values.iter().map(|v| (v - m).abs()).collect();
    median(&dev)
}

pub fn robust_sigma(values: &[f64]) -> f64 {
    1.4826 * mad(values)
}

/// Медианный шаг сетки по углам (медиана положительных разностей, иначе 1).
pub fn angular_step(angles: &[f64]) -> f64 {
    if angles.len() < 2 {
        return 1.0;
    }
    let d: Vec<f64> = (1..angles.len())
        .map(|i| angles[i] - angles[i - 1])
        .filter(|s| *s > 0.0)
        .collect();
    if d.is_empty() {
        1.0
    } else {
        median(&d)
    }
}

/// Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная, не шире массива.
///
/// `round_ties_even`, а не `round`: Python `round(2.5) == 2` (как math.RoundToEven в Go
/// и Math.rint в JVM-портах), а Rust `round()` округляет половину от нуля.
pub fn window_points(angles: &[f64], span_deg: f64) -> usize {
    let n = angles.len();
    if n < 3 {
        return n.max(1);
    }
    let mut w = (span_deg / angular_step(angles)).round_ties_even() as i64;
    if w % 2 == 0 {
        w += 1;
    }
    if w < 3 {
        w = 3;
    }
    if w > n as i64 {
        w = if n % 2 == 1 { n as i64 } else { n as i64 - 1 };
    }
    w.max(3) as usize
}

fn odd_window(window: usize, n: usize) -> usize {
    let mut w = if window % 2 == 0 { window + 1 } else { window };
    if w < 3 {
        w = 3;
    }
    if w > n {
        w = if n % 2 == 1 { n } else { n - 1 };
    }
    w
}

pub fn wrap_index(i: isize, n: usize) -> usize {
    (((i % n as isize) + n as isize) % n as isize) as usize
}

/// Медианный фильтр по кольцу (окно в точках).
pub fn median_filter_wrap(x: &[f64], window: usize) -> Vec<f64> {
    let n = x.len();
    let w = odd_window(window, n);
    if w < 3 || n < 3 {
        return vec![median(x); n];
    }
    let h = (w as isize - 1) / 2;
    let mut out = vec![0.0; n];
    let mut win = vec![0.0; w];
    for i in 0..n {
        for k in 0..w {
            win[k] = x[wrap_index(i as isize - h + k as isize, n)];
        }
        out[i] = median(&win);
    }
    out
}

/// Скользящее среднее по кольцу (окно в точках).
pub fn smooth_wrap(x: &[f64], window: usize) -> Vec<f64> {
    let n = x.len();
    let w = odd_window(window, n);
    if w < 3 || n < 3 {
        return x.to_vec();
    }
    let h = (w as isize - 1) / 2;
    let mut out = vec![0.0; n];
    for i in 0..n {
        let mut s = 0.0;
        for k in -h..=h {
            s += x[wrap_index(i as isize + k, n)];
        }
        out[i] = s / w as f64;
    }
    out
}

pub fn circ_dist(a: f64, b: f64) -> f64 {
    let d = ((a - b + 180.0) % 360.0 + 360.0) % 360.0;
    (d - 180.0).abs()
}

pub fn circ_local(a: f64, b: f64) -> f64 {
    let d = ((a - b + 180.0) % 360.0 + 360.0) % 360.0;
    d - 180.0
}

pub fn smoothstep(t: f64) -> f64 {
    if t < 0.0 {
        0.0
    } else if t > 1.0 {
        1.0
    } else {
        t * t * (3.0 - 2.0 * t)
    }
}
