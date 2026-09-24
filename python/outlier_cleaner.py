"""
outlier_cleaner.py

Очистка данных от выбросов.

1) OutlierCleaner — «ручной» режим (как раньше): три метода с порогами,
   заданными в мм/сигмах (порог производной 0.5 мм/точку, MAD×9.5,
   modified z-score 3.5). Пороги подбирались под конкретный датчик/файл,
   поэтому по умолчанию поведение класса не меняется.

2) AutoOutlierCleaner — авторежим: пороги вычисляются по самим данным
   известными простыми методами (см. докстринг класса). Ключевое отличие —
   отклонение считается не от ГЛОБАЛЬНОЙ медианы, а от локального робастного
   уровня (медианный фильтр): сама форма (ямы/трещины, эллипсность, конусность)
   следится за профилем и выбросами не считается, а одиночные всплески
   остаются видимыми. Именно из-за глобальной медианы ручной режим
   отбраковывал точки на дне глубоких ям (см. compare_cleaner_auto.py).

3) build_cleaner(cfg) — фабрика: собирает нужный класс по секции конфига
   {"mode": "manual" | "auto", ...}.
"""

import numpy as np


class OutlierCleaner:
    def __init__(self,
                 threshold_deriv=0.5,
                 mad_k=9.5,
                 z_threshold=3.5):
        """
        Параметры:
            threshold_deriv — порог производной (мм/точку)
            mad_k           — множитель MAD
            z_threshold     — порог modified z-score
        """
        self.threshold_deriv = threshold_deriv
        self.mad_k = mad_k
        self.z_threshold = z_threshold

    def clean(self, angles, radii):
        """
        Возвращает маску выбросов: True = выброс.
        
        angles, radii — numpy массивы одинаковой длины.
        """
        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)

        if len(angles) != len(radii):
            raise ValueError("angles и radii должны быть одинаковой длины")
        if len(angles) < 3:
            return np.zeros(len(angles), dtype=bool)

        n = len(radii)

        # --- 1. Производная ---
        dr = np.diff(radii, prepend=radii[0])
        dr[0] = radii[0] - radii[-1]  # замыкание
        mask_deriv = np.abs(dr) > self.threshold_deriv

        # --- 2. MAD ---
        median_r = np.median(radii)
        abs_dev = np.abs(radii - median_r)
        mad = np.median(abs_dev)
        if mad > 0:
            mask_mad = abs_dev > (self.mad_k * mad)
        else:
            mask_mad = np.zeros(n, dtype=bool)

        # --- 3. Modified z-score ---
        if mad > 0:
            z_score = 0.6745 * abs_dev / mad
            mask_z = z_score > self.z_threshold
        else:
            mask_z = np.zeros(n, dtype=bool)

        # --- Объединяем ---
        mask = mask_deriv | mask_mad | mask_z
        return mask

    def stats(self, angles, radii):
        """
        Возвращает словарь с детальной статистикой.
        Полезно для диагностики.
        """
        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)

        dr = np.diff(radii, prepend=radii[0])
        dr[0] = radii[0] - radii[-1]
        mask_deriv = np.abs(dr) > self.threshold_deriv

        median_r = np.median(radii)
        abs_dev = np.abs(radii - median_r)
        mad = np.median(abs_dev)
        mask_mad = abs_dev > (self.mad_k * mad) if mad > 0 else np.zeros(len(radii), dtype=bool)

        if mad > 0:
            z_score = 0.6745 * abs_dev / mad
            mask_z = z_score > self.z_threshold
        else:
            mask_z = np.zeros(len(radii), dtype=bool)

        mask_total = mask_deriv | mask_mad | mask_z

        return {
            'n_total': len(radii),
            'n_deriv': int(mask_deriv.sum()),
            'n_mad': int(mask_mad.sum()),
            'n_z': int(mask_z.sum()),
            'n_total_outliers': int(mask_total.sum()),
            'percent_outliers': 100.0 * mask_total.sum() / len(radii),
            'mad_value': float(mad),
        }

    def apply(self, angles, radii):
        """
        Возвращает (angles_clean, radii_clean) — без выбросов.
        """
        mask = self.clean(angles, radii)
        return angles[~mask], radii[~mask]


# ============================================================================
# РОБАСТНЫЕ ОЦЕНКИ МАСШТАБА (нужны авторежиму; пороги берутся из данных)
# ============================================================================

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


# ============================================================================
# АВТОРЕЖИМ: ПОРОГИ ВЫЧИСЛЯЮТСЯ ПО ДАННЫМ
# ============================================================================

class AutoOutlierCleaner:
    """
    Очистка выбросов с АВТОПОДБОРОМ порогов по самим данным.

    Общая идея (простая и стандартная): сначала снимаем «форму» профиля
    локальным робастным уровнем — скользящей медианой по кольцу; остаток
    res = r - baseline содержит только шум и всплески. Пороги считаются от
    робастных оценок этого остатка (MAD/IQR) или от локального MAD, поэтому
    не зависят ни от единиц измерения, ни от глубины ям. В ручном режиме
    отклонение считалось от ГЛОБАЛЬНОЙ медианы, поэтому дно глубокой ямы
    (1.2-1.8 мм) выглядело как выброс и точки ямы выбрасывались.

    Методы (каждый порог — общепринятая константа, считается от данных):
      "hampel" — фильтр Хампеля: окно hampel_window точек (по умолчанию 7),
                 точка — выброс, если |r - med окна| > k_sigma * 1.4826 * MAD окна;
      "mad"    — modified z-score Иглевица-Хоглина: |res| > z_threshold * sigma(res),
                 sigma = 1.4826 * MAD(res), стандартный порог 3.5;
      "iqr"    — усы Тьюки: |res - med(res)| > iqr_k * IQR(res), стандарт 3.0;
      "gmm"    — двухкомпонентная гауссова смесь (EM): выброс — точка, у которой
                 апостериорная вероятность «широкой» компоненты >= 0.5.

    Дополнительно (deriv_gate, по умолчанию выключен) — шлюз по производной:
    |dr| > deriv_k * sigma(dr), т.е. тот же смысл, что ручной threshold_deriv,
    но порог вычисляется из данных (в мм/точку). На синтетике шлюз ухудшает
    точность (см. докстринг __init__), поэтому в авторежиме он не нужен.

    Профиль считается замкнутым (0..360): медианный фильтр, производная и
    сортировка по углу учитывают замыкание. Если angles не отсортированы,
    порядок восстанавливается внутри clean(), а маска возвращается в исходном
    порядке точек.

    Публичные атрибуты после clean():
        self.params_   — выбранные пороги (в мм и в сигмах) для протокола;
        self.severity_ — «степень ненормальности» точек (для диагностики).

    tune(...) — подбор порога по внешнему критерию (например, честной RMSE
    подгонки по равномерной сетке), если нужен не стандартный порог, а
    оптимум под конкретную задачу.
    """

    METHODS = ("hampel", "mad", "iqr", "gmm")
    # как называется подстраиваемый порог у каждого метода
    _TUNED_PARAM = {"mad": "z_threshold", "hampel": "k_sigma", "iqr": "iqr_k"}

    def __init__(self, method="iqr", baseline_deg=1.0, hampel_window=7,
                 hampel_scale="local", z_threshold=3.5, iqr_k=3.0, k_sigma=3.0,
                 n_reclip=2, deriv_gate=False, deriv_k=4.0, gmm_max_iter=200,
                 gmm_tol=1e-9, max_removed_frac=0.5, min_points=20):
        """
        Параметры:
            method          — "iqr" (по умолчанию) | "mad" | "gmm" | "hampel".
                              На синтетике лучшие результаты показали iqr
                              (precision 1.00, recall 0.98) и gmm (0.98 / 0.99);
                              см. compare_cleaner_auto.py.
            baseline_deg    — ширина окна снятия формы, ° (для mad/iqr/gmm).
                              Должна быть много меньше ширины ям (иначе яма
                              спишется в тренд) и много больше шага точек.
            hampel_window   — окно фильтра Хампеля, точек (метод "hampel")
            hampel_scale    — "local" (по умолчанию, «учебный» Хампель: масштаб
                              по MAD внутри окна) | "global" — центр локальный,
                              масштаб общий по остатку (устойчивее на коротких
                              окнах; на синтетике 7 точек: P 0.31 -> 0.60)
            z_threshold     — порог modified z-score (метод "mad"), стандарт 3.5
            iqr_k           — множитель IQR (метод "iqr"), стандарт 3.0
            k_sigma         — множитель локального MAD (метод "hampel"), стандарт 3.0
            n_reclip        — число повторных переоценок sigma по оставшимся точкам
                              (метод "mad"; 1 = без повторов)
            deriv_gate      — шлюз по производной с автопорогом. ПО УМОЛЧАНИЮ ВЫКЛЮЧЕН:
                              одиночный всплеск даёт перепад и «до», и «после» себя,
                              поэтому шлюз добавляет ещё одну ложную точку на каждый
                              настоящий выброс (замер: precision падает с ~0.98 до ~0.35)
            deriv_k         — множитель sigma(dr) для шлюза производной
            max_removed_frac — предохранитель: максимум отбрасываемой доли точек
            min_points      — при меньшем числе точек выбросы не ищутся
        """
        if method not in self.METHODS:
            raise ValueError(f"Неизвестный метод автоочистки: {method!r}; "
                             f"ожидается один из {self.METHODS}")
        self.method = method
        self.baseline_deg = float(baseline_deg)
        self.hampel_window = int(hampel_window)
        if hampel_scale not in ("global", "local"):
            raise ValueError("hampel_scale: ожидается 'global' или 'local'")
        self.hampel_scale = hampel_scale
        self.z_threshold = float(z_threshold)
        self.iqr_k = float(iqr_k)
        self.k_sigma = float(k_sigma)
        self.n_reclip = int(n_reclip)
        self.deriv_gate = bool(deriv_gate)
        self.deriv_k = float(deriv_k)
        self.gmm_max_iter = int(gmm_max_iter)
        self.gmm_tol = float(gmm_tol)
        self.max_removed_frac = float(max_removed_frac)
        self.min_points = int(min_points)

        self.params_ = {}
        self.severity_ = None
        self.tuned_ = False

    # --------------------------------------------------------------- утилиты
    def _threshold(self):
        """Текущий подстраиваемый порог метода."""
        return getattr(self, self._TUNED_PARAM[self.method])

    def _set_threshold(self, value):
        setattr(self, self._TUNED_PARAM[self.method], float(value))

    def threshold_name(self):
        """Имя подстраиваемого порога метода."""
        return self._TUNED_PARAM[self.method]

    def _prepare(self, angles, radii):
        """Сортировка по углу с запоминанием перестановки (профиль — кольцо)."""
        a = np.asarray(angles, dtype=float)
        r = np.asarray(radii, dtype=float)
        if len(a) != len(r):
            raise ValueError("angles и radii должны быть одинаковой длины")
        if len(a) < 2 or np.all(np.diff(a) >= 0):
            return a, r, None
        order = np.argsort(a, kind="stable")
        inv = np.empty_like(order)
        inv[order] = np.arange(len(order))
        return a[order], r[order], inv

    # ------------------------------------------------------------ вычисления
    def _statistics(self, angles, radii):
        """
        Степень ненормальности точек и маска по основному методу.

        Возвращает (mask, severity, info), где severity — безразмерная
        «зэд-подобная» величина (больше = сильнее похоже на выброс).
        """
        n = len(radii)
        info = {}

        if self.method == "hampel":
            w = max(3, self.hampel_window | 1)
            med = median_filter_wrap(radii, w)
            sig_glob = robust_sigma(radii - med)
            if self.hampel_scale == "local":
                # «учебный» Хампель: масштаб по MAD внутри окна
                _, loc_mad = _median_filter_mad_wrap(radii, w)
                sig_loc = 1.4826 * loc_mad
                sig = np.where(sig_loc > 1e-12, sig_loc,
                               sig_glob if sig_glob > 1e-12 else 1.0)
                info_sigma = float(np.median(sig_loc))
            else:
                # стабилизированный вариант: центр локальный, масштаб — общий
                # по остатку (локальный MAD по 7 точкам слишком неустойчив)
                sig = np.full(len(radii), sig_glob if sig_glob > 1e-12 else 1.0)
                info_sigma = sig_glob
            severity = np.abs(radii - med) / sig
            mask = severity > self.k_sigma
            info = {
                "hampel_window_points": w,
                "hampel_window_deg": w * angular_step(angles),
                "hampel_scale": self.hampel_scale,
                "sigma_res_mm": float(info_sigma),
            }
        else:
            w = window_points(angles, self.baseline_deg)
            baseline = median_filter_wrap(radii, w)
            res = radii - baseline
            sig = robust_sigma(res)
            info = {
                "baseline_window_points": w,
                "baseline_window_deg": w * angular_step(angles),
                "sigma_res_mm": sig,
            }

            if self.method == "mad":
                # modified z-score с повторной переоценкой МАСШТАБА по оставшимся
                # точкам (центр фиксирован — иначе порог «уезжает» и часть
                # настоящих выбросов перестаёт обнаруживаться)
                center = float(np.median(res))
                severity = np.abs(res - center) / (sig if sig > 1e-12 else 1.0)
                for _ in range(max(1, self.n_reclip)):
                    mask = np.abs(severity) > self.z_threshold
                    if not np.any(mask) or np.all(mask):
                        break
                    sig_new = robust_sigma(res[~mask] - center)
                    if sig_new <= 1e-12:
                        break
                    sev_new = np.abs(res - center) / sig_new
                    severity, sig = sev_new, sig_new
                info["sigma_res_mm"] = sig
                info["threshold_mm"] = self.z_threshold * sig
                mask = severity > self.z_threshold
            elif self.method == "iqr":
                q_spread = iqr(res)
                severity = np.abs(res - np.median(res)) / \
                    (q_spread if q_spread > 1e-12 else 1.0)
                info["iqr_res_mm"] = q_spread
                info["threshold_mm"] = self.iqr_k * q_spread
                mask = severity > self.iqr_k
            else:  # gmm
                severity = _two_component_gmm(res, self.gmm_max_iter, self.gmm_tol)
                info["threshold_mm"] = None
                mask = severity >= 0.5

        # предохранитель: не отбрасываем больше max_removed_frac точек
        cap = int(np.floor(self.max_removed_frac * n))
        if 0 < cap < n and int(mask.sum()) > cap:
            keep_level = np.sort(severity[mask])[::-1][cap - 1]
            mask = mask & (severity >= keep_level)
            info["capped"] = True

        return mask, severity, info

    def _deriv_threshold(self, radii):
        """Автопорог производной: deriv_k * sigma(dr), мм/точку."""
        d = np.diff(np.concatenate([radii, radii[:1]]))
        sig_d = robust_sigma(d)
        if sig_d <= 1e-12:
            return None, None
        return sig_d, self.deriv_k * sig_d

    # -------------------------------------------------------------------- API
    def clean(self, angles, radii):
        """
        Маска выбросов (True = выброс). Пороги вычисляются по этим же данным.

        Интерфейс совпадает с OutlierCleaner.clean().
        """
        a, r, inv = self._prepare(angles, radii)
        n = len(r)
        if n < max(3, self.min_points):
            self.severity_ = np.zeros(n)
            self.params_ = {}
            return np.zeros(n, dtype=bool)

        mask, severity, info = self._statistics(a, r)

        if self.deriv_gate:
            sig_d, thr_d = self._deriv_threshold(r)
            if thr_d is not None:
                d = np.abs(np.diff(np.concatenate([r, r[:1]])))
                mask_d = d > thr_d
                # скачок i -> i+1 «портит» обе точки пары
                mask = mask | mask_d | np.roll(mask_d, 1)
                info["sigma_diff_mm"] = sig_d
                info["threshold_deriv_mm"] = thr_d

        info["method"] = self.method
        info["tuned"] = self.tuned_
        if self.method in self._TUNED_PARAM:
            info[self.threshold_name()] = self._threshold()
        info["n_total"] = int(n)
        info["n_total_outliers"] = int(mask.sum())
        info["percent_outliers"] = 100.0 * float(mask.sum()) / n

        if inv is None:
            self.severity_ = severity
            self.params_ = info
            return mask

        self.severity_ = severity[inv]
        self.params_ = info
        return mask[inv]

    def apply(self, angles, radii):
        """Возвращает (angles_clean, radii_clean) — без выбросов."""
        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)
        mask = self.clean(angles, radii)
        return angles[~mask], radii[~mask]

    def stats(self, angles, radii):
        """Статистика очистки (совместима по духу с OutlierCleaner.stats())."""
        mask = self.clean(angles, radii)
        out = dict(self.params_)
        out["n_total_outliers"] = int(mask.sum())
        return out

    def tune(self, angles, radii, score_fn, candidates=None, min_kept_frac=0.5):
        """
        Подбор порога метода по внешнему критерию.

        score_fn(angles_kept, radii_kept) -> float, меньше = лучше.
        Штатный критерий для этого проекта — RMSE подгонки, посчитанная по
        РАВНОМЕРНОЙ сетке (честная метрика всего кольца, см. compare_cleaner_auto.py).

        candidates     — значения порога (по умолчанию 2.0 ... 6.0 с шагом 0.25);
        min_kept_frac  — не пробовать варианты, отбрасывающие больше этой доли точек.

        Возвращает отчёт: [{threshold, n_kept, score, best}, ...].
        """
        if self.method not in self._TUNED_PARAM:
            raise ValueError(f"Метод {self.method!r} порогов не имеет — tune() "
                             "к нему не применим")
        if candidates is None:
            candidates = [round(2.0 + 0.25 * i, 2) for i in range(17)]  # 2.0 ... 6.0

        original = self._threshold()
        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)
        n = len(radii)

        rows = []
        best = None
        for value in candidates:
            self._set_threshold(value)
            mask = self.clean(angles, radii)
            n_kept = int((~mask).sum())
            row = {"threshold": float(value), "n_kept": n_kept, "score": None}
            if n_kept >= max(3, int(min_kept_frac * n)):
                row["score"] = float(score_fn(angles[~mask], radii[~mask]))
            rows.append(row)
            if row["score"] is not None and (best is None or row["score"] < best["score"]):
                best = row

        if best is None:
            self._set_threshold(original)
            raise RuntimeError("tune(): ни один вариант порога не дал корректного score")

        self._set_threshold(best["threshold"])
        self.tuned_ = True
        self.clean(angles, radii)  # обновить params_ под выбранный порог
        for row in rows:
            row["best"] = row is best
        return rows


def build_cleaner(cleaner_cfg=None):
    """
    Фабрика чистильщиков по секции конфига.

    Примеры:
        {"mode": "manual", "threshold_deriv": 0.5, "mad_k": 9.5, "z_threshold": 3.5}
        {"mode": "auto", "auto": {"method": "hampel", "hampel_window": 7}}
        {"mode": "auto", "method": "gmm"}   # авто-параметры можно и без вложенности

    Если передан готовый объект-чистильщик, он возвращается как есть.
    """
    if isinstance(cleaner_cfg, (OutlierCleaner, AutoOutlierCleaner)):
        return cleaner_cfg

    cfg = dict(cleaner_cfg or {})
    mode = cfg.pop("mode", "manual")
    nested = cfg.pop("auto", None)
    auto_cfg = dict(nested) if nested else {}

    if mode == "manual":
        return OutlierCleaner(**cfg)
    if mode == "auto":
        return AutoOutlierCleaner(**(auto_cfg or cfg))
    raise ValueError(f"Неизвестный режим очистки: {mode!r} "
                     "(ожидается 'manual' или 'auto')")