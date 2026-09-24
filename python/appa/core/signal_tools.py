# вырезано из outlier_cleaner_src.py (рефакторинг, см. CONTEXT.md §21)

import numpy as np

def mad(x):
    """MAD = median(|x - median(x)|) — разброс, устойчивый к выбросам."""
    x = np.asarray(x, dtype=float)
    return float(np.median(np.abs(x - np.median(x))))


def robust_sigma(x):
    """Робастная sigma = 1.4826 * MAD (коэффициент согласован с нормалью)."""
    return 1.4826 * mad(x)


def iqr(x):
    """Межквартильный размах Q75 - Q25."""
    x = np.asarray(x, dtype=float)
    q25, q75 = np.percentile(x, [25, 75])
    return float(q75 - q25)


def angular_step(angles):
    """Медианный шаг по углу, ° (перевод окон из градусов в точки)."""
    a = np.asarray(angles, dtype=float)
    if len(a) < 2:
        return 1.0
    d = np.diff(a)
    d = d[d > 0]
    return float(np.median(d)) if len(d) else 1.0


def window_points(angles, span_deg):
    """
    Нечётное число точек, ближайшее к span_deg (>= 3, <= длины массива).
    """
    a = np.asarray(angles, dtype=float)
    n = len(a)
    if n < 3:
        return max(1, n)
    w = int(round(span_deg / angular_step(a)))
    w = max(3, w | 1)
    if w > n:
        w = n if n % 2 == 1 else n - 1
    return max(3, w)


def median_filter_wrap(x, window):
    """
    Скользящая медиана по КОЛЬЦУ (профиль 0..360 замкнут).

    window — нечётное число точек (для чётного берётся window + 1).
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    w = max(3, int(round(window)) | 1)
    if w > n:
        w = n if n % 2 == 1 else n - 1
    if w < 3 or n < 3:
        return np.full(n, float(np.median(x)))

    h = w // 2
    ext = np.concatenate([x[-h:], x, x[:h]])
    win = np.lib.stride_tricks.sliding_window_view(ext, w)
    return np.median(win, axis=1)


def _median_filter_mad_wrap(x, window):
    """
    Скользящие медиана и MAD по кольцу (для фильтра Хампеля).

    Возвращает (med, mad) — оба длиной len(x).
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    w = max(3, int(round(window)) | 1)
    if w > n:
        w = n if n % 2 == 1 else n - 1
    if w < 3 or n < 3:
        med = float(np.median(x))
        return np.full(n, med), np.full(n, mad(x))

    h = w // 2
    ext = np.concatenate([x[-h:], x, x[:h]])
    win = np.lib.stride_tricks.sliding_window_view(ext, w)
    med = np.median(win, axis=1)
    loc_mad = np.median(np.abs(win - med[:, None]), axis=1)
    return med, loc_mad


def _two_component_gmm(x, max_iter=200, tol=1e-9):
    """
    Двухкомпонентная одномерная гауссова смесь (EM).

    Компонента 0 — «шум» (стартует около нуля), компонента 1 — «выбросы»
    (стартует по точкам, отстоящим от медианы больше чем на 3 робастные sigma).
    Возвращает апостериорную вероятность компоненты 1 для каждой точки.

    Известный простой метод, никаких порогов в мм: разделение происходит по
    данным, а решение принимается по вероятности (>= 0.5).
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 10:
        return np.zeros(n)

    s0 = robust_sigma(x)
    if s0 <= 0:
        return np.zeros(n)

    med = float(np.median(x))
    cand = np.abs(x - med) > 3.0 * s0
    if not np.any(cand):
        return np.zeros(n)

    mu0, sig0 = med, s0
    mu1 = float(np.mean(x[cand]))
    sig1 = max(float(np.std(x[cand])), s0)
    pi1 = float(np.clip(np.mean(cand), 1e-4, 0.5))
    pi0 = 1.0 - pi1

    def log_norm(x_, mu, sig):
        sig = max(sig, 1e-9)
        return -0.5 * ((x_ - mu) / sig) ** 2 - np.log(sig * np.sqrt(2.0 * np.pi))

    for _ in range(max_iter):
        l0 = np.log(max(pi0, 1e-12)) + log_norm(x, mu0, sig0)
        l1 = np.log(max(pi1, 1e-12)) + log_norm(x, mu1, sig1)
        m = np.maximum(l0, l1)
        w0 = np.exp(l0 - m)
        w1 = np.exp(l1 - m)
        denom = w0 + w1
        r1 = w1 / denom
        r0 = 1.0 - r1

        n1 = float(np.sum(r1))
        n0 = float(np.sum(r0))
        if n1 < 1e-6 or n0 < 1e-6:
            break

        new_mu0 = float(np.sum(r0 * x) / n0)
        new_mu1 = float(np.sum(r1 * x) / n1)
        new_sig0 = float(np.sqrt(max(np.sum(r0 * (x - new_mu0) ** 2) / n0, 1e-12)))
        new_sig1 = float(np.sqrt(max(np.sum(r1 * (x - new_mu1) ** 2) / n1, 1e-12)))
        new_pi1 = n1 / n

        delta = (abs(new_mu0 - mu0) + abs(new_mu1 - mu1) +
                 abs(new_sig0 - sig0) + abs(new_sig1 - sig1) + abs(new_pi1 - pi1))
        mu0, mu1, sig0, sig1, pi1 = new_mu0, new_mu1, new_sig0, new_sig1, new_pi1
        pi0 = 1.0 - pi1
        if delta < tol:
            break

    l0 = np.log(max(pi0, 1e-12)) + log_norm(x, mu0, sig0)
    l1 = np.log(max(pi1, 1e-12)) + log_norm(x, mu1, sig1)
    m = np.maximum(l0, l1)
    w0 = np.exp(l0 - m)
    w1 = np.exp(l1 - m)
    return w1 / (w0 + w1)
