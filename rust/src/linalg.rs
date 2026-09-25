//! Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
//! np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени.

/// Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится.
pub fn lstsq_qr(a_in: &[Vec<f64>], b_in: &[f64]) -> Vec<f64> {
    let m = a_in.len();
    assert!(m > 0, "lstsq_qr: пустая матрица");
    let n = a_in[0].len();
    assert_eq!(b_in.len(), m, "lstsq_qr: длины A и b не совпадают");
    assert!(m >= n, "lstsq_qr: нужно m >= n");

    let mut a = a_in.to_vec();
    let mut b = b_in.to_vec();

    for k in 0..n {
        let mut norm = 0.0;
        for i in k..m {
            norm += a[i][k] * a[i][k];
        }
        norm = norm.sqrt();
        if norm < 1e-300 {
            continue;
        }

        let alpha = if a[k][k] > 0.0 { -norm } else { norm };
        let mut v = vec![0.0; m];
        for i in k..m {
            v[i] = a[i][k];
        }
        v[k] -= alpha;
        let mut vnorm2 = 0.0;
        for i in k..m {
            vnorm2 += v[i] * v[i];
        }
        if vnorm2 < 1e-300 {
            continue;
        }

        for j in k..n {
            let mut s = 0.0;
            for i in k..m {
                s += v[i] * a[i][j];
            }
            let c = 2.0 * s / vnorm2;
            for i in k..m {
                a[i][j] -= c * v[i];
            }
        }
        let mut sb = 0.0;
        for i in k..m {
            sb += v[i] * b[i];
        }
        let cb = 2.0 * sb / vnorm2;
        for i in k..m {
            b[i] -= cb * v[i];
        }
    }

    let mut x = vec![0.0; n];
    for i in (0..n).rev() {
        let mut s = b[i];
        for j in i + 1..n {
            s -= a[i][j] * x[j];
        }
        let d = a[i][i];
        assert!(d.abs() >= 1e-300, "lstsq_qr: вырожденная система");
        x[i] = s / d;
    }
    x
}

/// Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval).
pub fn polyval(coefs: &[f64], x: f64) -> f64 {
    let mut r = 0.0;
    for c in coefs {
        r = r * x + c;
    }
    r
}

pub fn polyfit(xs: &[f64], ys: &[f64], deg: usize) -> Vec<f64> {
    let m = xs.len();
    let n = deg + 1;
    let mut a = vec![vec![0.0; n]; m];
    for i in 0..m {
        let mut p = 1.0;
        for j in 0..n {
            a[i][n - 1 - j] = p;
            p *= xs[i];
        }
    }
    lstsq_qr(&a, ys)
}

/// T_0(x)..T_deg_max(x) — базис Чебышёва (x ∈ [-1, 1]).
pub fn cheb_row(x: f64, deg_max: usize) -> Vec<f64> {
    let mut t = vec![0.0; deg_max + 1];
    t[0] = 1.0;
    if deg_max >= 1 {
        t[1] = x;
    }
    for k in 2..=deg_max {
        t[k] = 2.0 * x * t[k - 1] - t[k - 2];
    }
    t
}

/// Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
pub fn cheb_sum(c: &[f64], deg: usize, x: f64) -> f64 {
    let mut b1 = 0.0;
    let mut b2 = 0.0;
    for k in (1..=deg).rev() {
        let b0 = 2.0 * x * b1 - b2 + c[k];
        b2 = b1;
        b1 = b0;
    }
    x * b1 - b2 + c[0]
}
