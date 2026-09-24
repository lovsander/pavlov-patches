"""
patch_approximator.py

Класс PatchApproximator — аппроксимация замкнутых форм
(тел вращения) кусочно-полиномиальными патчами с адаптивной степенью.

Метод Павлова (patch method):
- N патчей с перекрытием
- адаптивная степень по ОСТАТКАМ обучения (правило «локтя»): берём
  наименьшую чётную степень, на которой RMSE обучающего окна не хуже
  лучшей более чем на deg_elbow_tol. Историческая метрика «по
  нормализованной амплитуде сектора» (P95-P5) оставлена только как
  справочная в metrics: она измеряет размах, а не сложность формы,
  поэтому недооценивала узкие глубокие ямы и переоценивала пологие
  широкие секторы.
- чётные степени
- обучение шире (train_overlap), blend уже (use_overlap)
- smoothstep-веса с доминированием в своём секторе
- фаза сетки (phase_deg): центры патчей повёрнуты на заданный угол;
  phase_deg=0 — историческое поведение (первый сектор начинается с 0°)
"""

import numpy as np


class PatchApproximator:
    def __init__(self, n_patches=8, deg_min=4, deg_max=14, amplitude_scale=180.0,
                 overlap_train=15.0, overlap_use=5.0, phase_deg=0.0,
                 deg_elbow_tol=0.05):
        if deg_min % 2 != 0:
            deg_min += 1
        if deg_max % 2 != 0:
            deg_max += 1
        self.n_patches = n_patches
        self.deg_min = deg_min
        self.deg_max = deg_max
        # Историческая амплитудная шкала: больше НЕ влияет на выбор степени,
        # хранится для совместимости форматов (.npz/.pmodel) и отчётов.
        self.amplitude_scale = amplitude_scale
        # Правило «локтя»: допуск по RMSE относительно лучшей степени, доли.
        self.deg_elbow_tol = float(deg_elbow_tol)
        self.overlap_train = overlap_train
        self.overlap_use = overlap_use
        # Фазовый сдвиг сетки патчей, °. 0 — первый сектор начинается с 0°.
        self.phase_deg = float(phase_deg) % 360.0
        self.centers_ = None
        self.half_sector_ = None
        self.patches_ = []
        self.degrees_ = None
        self.is_fitted_ = False

    def _smoothstep_vec(self, t):
        """Векторизованный Smoothstep, ограниченный диапазоном [0, 1]."""
        t = np.clip(t, 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)


    def _estimate_degree(self, angles, radii, center):
        """
        Степень патча по ОСТАТКАМ на обучающем окне (правило «локтя»).

        Почему не по амплитуде: P95-P5 измеряет размах сектора, а не
        сложность формы. Узкая глубокая яма даёт маленький размах (мало
        точек ниже перцентиля) и получала заниженную степень, а широкий
        пологий сектор с шумом/волнистостью — завышенную. Остатки же
        напрямую показывают, сколько структуры полином не описывает.

        Алгоритм: считаем МНК-RMSE на обучающем окне (half_train) для всех
        чётных степеней deg_min..deg_max и берём НАИМЕНЬШУЮ степень, где
        RMSE не хуже лучшей более чем на deg_elbow_tol.

        Возвращает (degree, metrics) — metrics только из чисел (формат
        .pmodel требует float-значений).
        """
        sector = 360.0 / self.n_patches
        half_sector = sector / 2.0
        mask_sec = np.abs((angles - center + 180) % 360 - 180) <= half_sector
        r_sec = radii[mask_sec]

        # Справочная (историческая) амплитудная метрика — для отчётов.
        if len(r_sec) >= 5:
            amp = float(np.percentile(r_sec, 95) - np.percentile(r_sec, 5))
            mean_r_sec = float(np.mean(r_sec))
        else:
            amp, mean_r_sec = 0.0, 0.0
        amp_norm = amp / mean_r_sec if mean_r_sec > 0 else 0.0

        base_metrics = {
            'amplitude_mm': amp,
            'mean_radius_mm': mean_r_sec,
            'amplitude_norm': amp_norm,
            'deg_elbow_tol': float(self.deg_elbow_tol),
        }

        half_train = half_sector + self.overlap_train
        # Окно строим ровно так же, как в fit(): разворачиваем кольцо на ±360°
        # и берём точки в [center - half_train, center + half_train], поэтому
        # остатки кандидатов считаются на том же наборе точек, что и финальный МНК.
        angles_ext = np.concatenate([angles - 360, angles, angles + 360])
        radii_ext = np.concatenate([radii, radii, radii])
        mask = (angles_ext >= center - half_train) & (angles_ext <= center + half_train)
        local_x = angles_ext[mask] - center
        local_y = radii_ext[mask]

        if len(local_x) < 5:
            base_metrics.update({'rmse_selected_mm': 0.0, 'rmse_best_mm': 0.0,
                                 'n_train_points': int(len(local_x))})
            return self.deg_min, base_metrics

        best_rmse, best_deg = None, self.deg_min
        results = []
        for deg in range(self.deg_min, self.deg_max + 1, 2):
            coefs = np.polyfit(local_x, local_y, deg)
            rmse = float(np.sqrt(np.mean(
                (np.polyval(coefs, local_x) - local_y) ** 2)))
            results.append((deg, rmse))
            if best_rmse is None or rmse < best_rmse:
                best_rmse, best_deg = rmse, deg

        limit = best_rmse * (1.0 + self.deg_elbow_tol)
        selected_deg, selected_rmse = next(
            ((deg, rmse) for deg, rmse in results if rmse <= limit),
            (best_deg, best_rmse))                 # страховка: лучшая степень

        base_metrics.update({
            'rmse_selected_mm': float(selected_rmse),
            'rmse_best_mm': float(best_rmse),
            'n_train_points': int(len(local_x)),
        })
        return int(selected_deg), base_metrics

    def fit(self, angles, radii):
        import time
        t0 = time.perf_counter()

        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)

        sector = 360.0 / self.n_patches
        self.half_sector_ = sector / 2
        # Центры патчей повёрнуты на phase_deg. Порядок патчей сохраняется
        # (i-й патч = i-й центр) — так же, как в .npz и .pmodel.
        self.centers_ = [
            (i * sector + self.half_sector_ + self.phase_deg) % 360.0
            for i in range(self.n_patches)
        ]

        angles_ext = np.concatenate([angles - 360, angles, angles + 360])
        radii_ext = np.concatenate([radii, radii, radii])

        self.patches_ = []
        self.degrees_ = []

        for c in self.centers_:
            deg, metrics = self._estimate_degree(angles, radii, c)
            self.degrees_.append(deg)

            half_train = self.half_sector_ + self.overlap_train
            half_use = self.half_sector_ + self.overlap_use

            mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
            local_x = angles_ext[mask] - c
            local_y = radii_ext[mask]

            coefs = np.polyfit(local_x, local_y, deg)

            # stats по остаткам
            r_fit = np.polyval(coefs, local_x)
            residuals = r_fit - local_y
            rmse = float(np.sqrt(np.mean(residuals ** 2)))
            mae = float(np.mean(np.abs(residuals)))
            max_err = float(np.max(np.abs(residuals)))
            if np.std(r_fit) > 0 and np.std(local_y) > 0:
                corr = float(np.corrcoef(r_fit, local_y)[0, 1])
            else:
                corr = 0.0

            self.patches_.append({
                'center': c,
                'degree': deg,
                'n_points': int(mask.sum()),
                'coefs': coefs,
                'half_sector': self.half_sector_,
                'half_train': half_train,
                'half_use': half_use,
                'metrics': metrics,
                'stats': {
                    'rmse_mm': rmse,
                    'mae_mm': mae,
                    'max_err_mm': max_err,
                    'correlation': corr,
                },
            })

        self.degrees_ = np.array(self.degrees_)
        self.is_fitted_ = True

        fit_time_ms = (time.perf_counter() - t0) * 1000.0
        self.statistics_ = {
            'n_points_total': int(len(angles)),
            'n_outliers_removed': 0,   # задаётся снаружи, если нужно
            'fit_time_ms': fit_time_ms,
        }
        return self

    def eval(self, angles):
        """
        ПОЛНОСТЬЮ ВЕКТОРИЗОВАННЫЙ МЕТОД РАСЧЕТА КОНТУРА.
        Работает без циклов Python по точкам геометрии.
        """
        if not self.is_fitted_:
            raise RuntimeError("Сначала вызовите fit()")
        angles = np.asarray(angles, dtype=float)

        # Результирующие матрицы: строки - точки углов (M), столбцы - патчи (N)
        M = len(angles)
        N = self.n_patches

        vals_matrix = np.zeros((M, N))
        weights_matrix = np.zeros((M, N))

        # Проходим только по количеству патчей (их всего 8, а не 3600 точек)
        for idx, p in enumerate(self.patches_):
            c = p['center']

            # Расчет кратчайшего расстояния по дуге (циклическая метрика) - векторно для всех углов
            d = np.abs((angles - c + 180) % 360 - 180)
            local_coord = (angles - c + 180) % 360 - 180

            # Векторизованный расчет весов для текущего патча по всему массиву углов
            w = np.zeros(M)
            # Внутри своего сектора вес = 1
            w[d <= self.half_sector_] = 1.0

            # В зоне блендинга (перекрытия) - плавное затухание smoothstep
            blend_mask = (d > self.half_sector_) & (d <= p['half_use'])
            if np.any(blend_mask):
                t = 1.0 - (d[blend_mask] - self.half_sector_) / \
                    (p['half_use'] - self.half_sector_)
                # встроенный smoothstep
                w[blend_mask] = t * t * (3.0 - 2.0 * t)

            # Расчет значения полинома p['coefs'] сразу для всей сетки локальных координат
            vals_matrix[:, idx] = np.polyval(p['coefs'], local_coord)
            weights_matrix[:, idx] = w

        # Векторизованное взвешенное среднее по строкам (ось 1)
        sum_weights = np.sum(weights_matrix, axis=1)

        # Защита от деления на ноль (если точка выпала из всех секторов)
        safe_mask = sum_weights > 0
        fitted = np.zeros(M)
        fitted[safe_mask] = np.sum(
            weights_matrix[safe_mask] * vals_matrix[safe_mask], axis=1) / sum_weights[safe_mask]
        fitted[~safe_mask] = np.nan

        return fitted

    def get_degrees(self):
        """Список степеней по патчам."""
        if not self.is_fitted_:
            raise RuntimeError("Сначала вызовите fit()")
        return self.degrees_.tolist()

    def get_coefficients(self):
        """Словарь: центр патча → коэффициенты полинома."""
        if not self.is_fitted_:
            raise RuntimeError("Сначала вызовите fit()")
        return {p['center']: p['coefs'].tolist() for p in self.patches_}

    def save(self, path):
        """Сохранение в .npz (коэффициенты + параметры)."""
        if not self.is_fitted_:
            raise RuntimeError("Сначала вызовите fit()")

        data = {
            'n_patches': self.n_patches,
            'deg_min': self.deg_min,
            'deg_max': self.deg_max,
            'amplitude_scale': self.amplitude_scale,
            'deg_elbow_tol': self.deg_elbow_tol,
            'overlap_train': self.overlap_train,
            'overlap_use': self.overlap_use,
            'phase_deg': self.phase_deg,
            'centers': np.array(self.centers_),
            'degrees': np.array(self.degrees_),
        }
        for j, p in enumerate(self.patches_):
            data[f'coefs_{j}'] = p['coefs']
            data[f'n_points_{j}'] = p['n_points']

        np.savez(path, **data)

    @classmethod
    def load(cls, path):
        """Загрузка из .npz."""
        d = np.load(path)
        obj = cls(
            n_patches=int(d['n_patches']),
            deg_min=int(d['deg_min']),
            deg_max=int(d['deg_max']),
            amplitude_scale=float(d['amplitude_scale']),
            overlap_train=float(d['overlap_train']),
            overlap_use=float(d['overlap_use']),
            # старые .npz без поля фазы читаются как phase_deg = 0
            phase_deg=float(d['phase_deg']) if 'phase_deg' in d else 0.0,
            # старые .npz без поля допуска читаются как deg_elbow_tol = 0.05
            deg_elbow_tol=float(d['deg_elbow_tol']) if 'deg_elbow_tol' in d else 0.05,
        )
        obj.centers_ = list(d['centers'])
        obj.half_sector_ = 360.0 / obj.n_patches / 2
        obj.degrees_ = np.array(d['degrees'])

        obj.patches_ = []
        for j, c in enumerate(obj.centers_):
            obj.patches_.append({
                'center': c,
                'half_sector': obj.half_sector_,
                'half_train': obj.half_sector_ + obj.overlap_train,
                'half_use': obj.half_sector_ + obj.overlap_use,
                'coefs': d[f'coefs_{j}'],
                'degree': int(d['degrees'][j]),
                'n_points': int(d[f'n_points_{j}']),
            })

        obj.is_fitted_ = True
        return obj
