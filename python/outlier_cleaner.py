"""
outlier_cleaner.py

Класс OutlierCleaner — очистка данных от выбросов.

Три независимых метода:
1. По производной (резкие скачки)
2. По MAD (отклонения от медианы)
3. По modified z-score (статистические выбросы)

Все три объединяются логическим ИЛИ.
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