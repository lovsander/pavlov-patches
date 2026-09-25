# вырезано из _src_pit_feature.py (рефакторинг, см. CONTEXT.md §21)
"""appa.core.pit_feature — ПРОТОТИП: оконный гаусс (яма) в базисе патча.

Форма ямы вынесена в модульную функцию pit_shape_deg(): её использует и класс
PitPatchApproximator (в нормированных координатах патча), и «Фурье + фичер ям»
(appa.analysis.fourier_study) — одна форма, один набор параметров.
"""

import time

import numpy as np

from .patch_approximator import PatchApproximator

# ЕДИНЫЙ ИСТОЧНИК параметров фичера ям. Решение 2026-09-24 (CONTEXT §25):
# остаёмся на оконном гауссе 3.2σ при общей фазе раскладки — это проще и
# надёжнее (одна раскладка на всё тело, прямые швы, паритет с C++ тривиален),
# а альтернативы (окно 2.5σ, своя фаза «под ямы») эффекта по точности не дают.
PIT_DEFAULTS = {
    "sigma_deg": 3.0,          # полуширина ядра гаусса
    "pit_core_sigma": 2.0,     # при |d| <= 2σ вес 1 (дно не искажаем)
    "pit_window_sigma": 3.2,   # при |d| = 3.2σ вес ровно 0 (выход в базис)
    "pit_min_amp": 3e-3,       # слабее этого гаусс в окне патча не тратит параметр
    "tapering": True,          # False = чистый гаусс (только для сравнений)
}

# ЕДИНЫЙ ИСТОЧНИК параметров МОДЕЛИ — раскладка и правило степени (CONTEXT §25, §27).
# Раньше эти числа были скопированы в CONFIG каждого исследования и в демо, из-за
# чего N, фаза и допуски могли разъехаться. Раскладка выбрана в §25: N=7 при общей
# фазе 24.75° (узлы уходят от трещин, паритет с портом — один параметр в файле).
MODEL_DEFAULTS = {
    "n_patches": 7,
    "phase_deg": 24.75,
    "deg_min": 4,
    "deg_max": 14,
    "amplitude_scale": 180.0,   # историческая метрика, степень НЕ выбирает
    "overlap_train": 15.0,
    "overlap_use": 5.0,
    "deg_elbow_tol": 0.05,
}

# Параметры детектора трещин (двухмасштабный band), которыми пользуется
# пайплайн, чтобы НАЙТИ центры ям для фичера. Настройка зафиксирована в §14
# (band |уровень 1° − уровень 10°|, порог k=5.5 MAD, зона не короче 2°);
# копии этих чисел по исследованиям сведены сюда, чтобы пайплайн и скрипты
# искали ямы одинаково.
DETECTOR_DEFAULTS = {
    "kind": "band",
    "window_deg": 1.0,
    "wide_deg": 10.0,
    "smooth_deg": 2.0,
    "k": 5.5,
    "min_zone_deg": 2.0,
}


def validate_pit_cfg(cfg):
    """Проверка согласованности параметров фичера: окно не уже ядра, σ > 0."""
    core = float(cfg["pit_core_sigma"]) * float(cfg["sigma_deg"])
    win = float(cfg["pit_window_sigma"]) * float(cfg["sigma_deg"])
    if float(cfg["sigma_deg"]) <= 0.0:
        raise ValueError("sigma_deg должен быть > 0")
    if win < core:
        raise ValueError(f"окно фичера ({win:.2f}°) уже ядра ({core:.2f}°)")
    return {"core_deg": core, "window_deg": win}



def pit_shape_deg(delta_deg, sigma_deg=3.0, core_sigma=2.0, window_sigma=3.2,
                  tapering=True):
    """
    Оконный гаусс как функция РАССТОЯНИЯ от центра ямы (в градусах), вес 1 в ядре.

      |d| <= core_sigma*sigma -> вес 1 (дно ямы не искажаем)
      core_sigma*sigma .. window_sigma*sigma -> smoothstep t^2(3-2t), t от 1 к 0
      |d| >= window_sigma*sigma -> ровно 0 (выход в базис без излома: у smoothstep
                                   нулевая производная на обоих краях)

    tapering=False -> чистый гаусс (как было до 2026-09-24), для сравнения.
    """
    d = np.abs(np.asarray(delta_deg, dtype=float))
    val = np.exp(-d * d / (2.0 * float(sigma_deg) ** 2))
    if not tapering:
        return val
    core = float(core_sigma) * float(sigma_deg)
    edge = float(window_sigma) * float(sigma_deg)
    if edge <= core:
        return val
    t = np.clip((edge - d) / (edge - core), 0.0, 1.0)
    return val * t * t * (3.0 - 2.0 * t)


def build_model(cfg=None, pits=None):
    """
    ЕДИНАЯ точка сборки модели (CONTEXT §27, шаг 2).

    Возвращает НЕобученную модель: вызывающий сам зовёт fit(). Это единственное
    место, где собираются раскладка (MODEL_DEFAULTS) и форма фичера ям
    (PIT_DEFAULTS) — исследования, пайплайн и порт должны ходить сюда, чтобы
    N / фаза / допуски / форма ямы не разъезжались.

    cfg  — словарь параметров; недостающие ключи берутся из MODEL_DEFAULTS,
           параметры ямы — с именами из PIT_DEFAULTS (sigma_deg, pit_core_sigma,
           pit_window_sigma, pit_min_amp, tapering) + degree_with_pits;
    pits — углы центров ям, °; пусто/None -> чистая полиномиальная модель,
           иначе полином + оконный гаусс (PitPatchApproximator).
    """
    cfg = dict(cfg or {})
    mk = dict(MODEL_DEFAULTS)
    mk.update({k: v for k, v in cfg.items() if k in MODEL_DEFAULTS})

    if not pits:
        return PatchApproximator(**mk)

    pk = {
        "sigma_deg": cfg.get("sigma_deg", PIT_DEFAULTS["sigma_deg"]),
        "core_sigma": cfg.get("pit_core_sigma", PIT_DEFAULTS["pit_core_sigma"]),
        "window_sigma": cfg.get("pit_window_sigma", PIT_DEFAULTS["pit_window_sigma"]),
        "pit_min_amp": cfg.get("pit_min_amp", PIT_DEFAULTS["pit_min_amp"]),
        "tapering": cfg.get("tapering", PIT_DEFAULTS["tapering"]),
        "degree_with_pits": cfg.get("degree_with_pits", False),
    }
    return PitPatchApproximator(pits=list(pits), **pk, **mk)


class PitPatchApproximator(PatchApproximator):
    """
    Копия PatchApproximator, у которой базис патча расширен ОКОННЫМИ гауссовыми
    ямами (tapered gaussian).

    Отличия от базового класса ровно два:
      * коэффициенты считаются МНК по расширенному базису
        [x^deg ... x^1, 1, phi_1(x), ... phi_K(x)]; phi_k = оконный гаусс,
        см. _pit_shape: ядро exp(-d^2/2sigma^2), вес 1 при |d| <= core_sigma*sigma
        и плавный (smoothstep, с нулевой производной на краях) уход в 0 при
        |d| = window_sigma*sigma. Именно это убирает излом на выходе ямы в
        полином и обнуляет вклад ямы в зоне перекрытия соседних патчей;
      * value = полином(x) + sum a_k * phi_k(x) — и при вычислении контура, и при
        выборе степени (degree_with_pits=True).

    Центры ям c_k — глобальные углы из детектора трещин; в каждом патче в базис
    попадают только те ямы, что видны в его обучающем окне (|dx| <= half_train),
    поэтому «чужие» ямы не тратят коэффициент. Смешивание патчей (smoothstep)
    не меняется: оконный гаусс живёт внутри кривой своего патча, как и полином.
    """

    def __init__(self, pits, sigma_deg=3.0, tapering=True, core_sigma=2.0,
                 window_sigma=3.2, degree_with_pits=False, pit_min_amp=3e-3,
                 **kwargs):
        super().__init__(**kwargs)
        self.pits = [float(p) % 360.0 for p in pits]
        self.sigma_deg = float(sigma_deg)
        self.tapering = bool(tapering)      # False = чистый гаусс (вариант pit_raw)
        self.core_sigma = float(core_sigma)
        self.window_sigma = float(window_sigma)
        self.degree_with_pits = bool(degree_with_pits)
        self.pit_min_amp = float(pit_min_amp)

    # --- форма ямы --------------------------------------------------------

    def pit_window_deg(self):
        """Полуширина окна фичера в градусах (где вес уже ровно 0)."""
        return self.window_sigma * self.sigma_deg

    def _pit_shape(self, xs, dx, s):
        """
        Оконный гаусс в нормированных координатах патча: xs, dx — в единицах
        half_train, s = sigma_deg / half_train. Делегирует в общую форму
        pit_shape_deg (одна форма на патчи и на Фурье-вариант).
        """
        d_deg = np.abs(np.asarray(xs, dtype=float) - dx) * self.half_train_
        return pit_shape_deg(d_deg, self.sigma_deg, self.core_sigma,
                             self.window_sigma, self.tapering)

    # --- базис -----------------------------------------------------------

    def _pit_offsets(self, center_deg, half_win_deg):
        """Смещения видимых ям в локальной системе патча (dx в градусах)."""
        dx = np.mod(np.asarray(self.pits) - center_deg + 180.0, 360.0) - 180.0
        return [float(v) for v in dx if abs(v) <= half_win_deg]

    def _design(self, xs, deg, dx_scaled):
        """
        Матрица базиса: полином (степени по убыванию) + оконные гауссовы ямы.

        xs и dx_scaled — в НОРМИРОВАННЫХ координатах (деление на half_train):
        без нормировки x^14 в градусах даёт cond ~1e20 и МНК выдаёт мусор
        (проверено: разлеталось до 7.7 мм RMSE).
        """
        cols = [xs ** k for k in range(deg, -1, -1)]
        s = self.sigma_deg / self.half_train_
        for dx in dx_scaled:
            cols.append(self._pit_shape(xs, dx, s))
        return np.column_stack(cols)

    def _train_window(self, angles, radii, center, half_train):
        """Обучающее окно патча — ровно как в PatchApproximator.fit()."""
        angles_ext = np.concatenate([angles - 360, angles, angles + 360])
        radii_ext = np.concatenate([radii, radii, radii])
        mask = (angles_ext >= center - half_train) & (angles_ext <= center + half_train)
        return angles_ext[mask] - center, radii_ext[mask]

    def _estimate_degree(self, angles, radii, center):
        """
        Правило «локтя» по остаткам. degree_with_pits=False — вызываем базовый
        метод (степени получаются ТАКИЕ ЖЕ, как у baseline, и виден чистый вклад
        фичера). degree_with_pits=True — тот же перебор, но базис уже с ямами.
        """
        if not self.degree_with_pits:
            return super()._estimate_degree(angles, radii, center)

        half_train = 180.0 / self.n_patches + self.overlap_train
        self.half_train_ = half_train
        local_x, local_y = self._train_window(angles, radii, center, half_train)
        offsets = self._pit_offsets(center, half_train)

        if len(local_x) < 5:
            return self.deg_min, {'rmse_selected_mm': 0.0, 'rmse_best_mm': 0.0,
                                  'n_train_points': int(len(local_x))}

        xs = local_x / half_train
        dx_scaled = [d / half_train for d in offsets]
        results = []
        for deg in range(self.deg_min, self.deg_max + 1, 2):
            A = self._design(xs, deg, dx_scaled)
            coef, *_ = np.linalg.lstsq(A, local_y, rcond=None)
            res = A @ coef - local_y
            results.append((deg, float(np.sqrt(np.mean(res ** 2)))))

        best_deg, best_rmse = min(results, key=lambda t: t[1])
        limit = best_rmse * (1.0 + self.deg_elbow_tol)
        sel_deg, sel_rmse = next(((d, r) for d, r in results if r <= limit),
                                 (best_deg, best_rmse))
        return int(sel_deg), {'rmse_selected_mm': float(sel_rmse),
                              'rmse_best_mm': float(best_rmse),
                              'n_train_points': int(len(local_x)),
                              'n_pit_terms': int(len(offsets))}

    # --- обучение и вычисление контура ------------------------------------

    def fit(self, angles, radii):
        """МНК по расширенному базису; схема окон — как в базовом классе."""
        import time
        t0 = time.perf_counter()

        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)

        self.half_sector_ = 180.0 / self.n_patches
        half_train = self.half_sector_ + self.overlap_train
        self.half_train_ = half_train
        self.centers_ = [
            (i * 2.0 * self.half_sector_ + self.half_sector_ + self.phase_deg) % 360.0
            for i in range(self.n_patches)
        ]

        self.patches_ = []
        self.degrees_ = []

        for c in self.centers_:
            deg, metrics = self._estimate_degree(angles, radii, c)
            self.degrees_.append(deg)

            local_x, local_y = self._train_window(angles, radii, c, half_train)
            offsets = self._pit_offsets(c, half_train)
            xs = local_x / half_train
            dx_scaled = [d / half_train for d in offsets]

            A = self._design(xs, deg, dx_scaled)
            coef, *_ = np.linalg.lstsq(A, local_y, rcond=None)
            poly_coef = coef[:deg + 1]
            pit_coef = coef[deg + 1:]

            # оконный гаусс, который в окне патча «не виден», коэффициент не тратит
            s = self.sigma_deg / half_train
            keep = [i for i, a in enumerate(pit_coef)
                    if float(np.max(np.abs(a * self._pit_shape(
                        xs, dx_scaled[i], s)))) >= self.pit_min_amp]
            offsets = [offsets[i] for i in keep]
            pit_coef = pit_coef[keep]

            r_fit = A @ coef
            res = r_fit - local_y

            self.patches_.append({
                'center': c,
                'degree': int(deg),
                'coefs': poly_coef,                     # как в базовом классе
                'pit_offsets': np.array(offsets, dtype=float),
                'pit_coefs': np.array(pit_coef, dtype=float),
                'n_points': int(len(local_x)),
                'half_sector': self.half_sector_,
                'half_train': half_train,
                'half_use': self.half_sector_ + self.overlap_use,
                'metrics': metrics,
                'stats': {'rmse_mm': float(np.sqrt(np.mean(res ** 2))),
                          'max_err_mm': float(np.max(np.abs(res)))},
            })

        self.degrees_ = np.array(self.degrees_)
        self.is_fitted_ = True
        self.statistics_ = {'n_points_total': int(len(angles)),
                            'fit_time_ms': (time.perf_counter() - t0) * 1000.0}
        return self

    def eval_part(self, angles, part="total"):
        """
        Контур модели. part: "total" — полином + ямы, "poly" — только полином,
        "pit" — только гауссовы члены (нужно для наглядности на рисунке).

        Смешивание (smoothstep по перекрытию) — точно как в базовом eval().
        """
        if not self.is_fitted_:
            raise RuntimeError("Сначала вызовите fit()")
        angles = np.asarray(angles, dtype=float)
        M = len(angles)
        N = self.n_patches

        vals_matrix = np.zeros((M, N))
        weights_matrix = np.zeros((M, N))

        for idx, p in enumerate(self.patches_):
            c = p['center']
            d = np.abs((angles - c + 180) % 360 - 180)
            local_coord = (angles - c + 180) % 360 - 180

            w = np.zeros(M)
            w[d <= self.half_sector_] = 1.0
            blend = (d > self.half_sector_) & (d <= p['half_use'])
            if np.any(blend):
                t = 1.0 - (d[blend] - self.half_sector_) / (p['half_use']
                                                            - self.half_sector_)
                w[blend] = t * t * (3.0 - 2.0 * t)

            vals = np.zeros(M)
            s = self.sigma_deg / self.half_train_
            xs = local_coord / self.half_train_
            if part in ("total", "poly"):
                vals += np.polyval(p['coefs'], xs)
            if part in ("total", "pit"):
                for dx, a in zip(p['pit_offsets'], p['pit_coefs']):
                    vals += a * self._pit_shape(xs, dx / self.half_train_, s)

            vals_matrix[:, idx] = vals
            weights_matrix[:, idx] = w

        sum_w = np.sum(weights_matrix, axis=1)
        out = np.zeros(M)
        ok = sum_w > 0
        out[ok] = np.sum(weights_matrix[ok] * vals_matrix[ok], axis=1) / sum_w[ok]
        out[~ok] = np.nan
        return out

    def eval(self, angles):
        """Совместимость с PatchApproximator: полный контур (полином + ямы)."""
        return self.eval_part(angles, "total")

    # --- отчётность -------------------------------------------------------

    def pit_report(self):
        """Сводка по ямам: сколько их в каждом патче и какой амплитуды."""
        out = []
        for i, p in enumerate(self.patches_):
            out.append({
                'patch': i,
                'center': float(p['center']),
                'degree': int(p['degree']),
                'n_pits': int(len(p['pit_offsets'])),
                'n_coefs': int(len(p['coefs']) + len(p['pit_coefs'])),
                'pit_amp_mm': [float(a) for a in p['pit_coefs']],
                'pit_dx_deg': [float(d) for d in p['pit_offsets']],
            })
        return out
