"""
demo_pmodel.py

Полный цикл: fit → save → load → validate → summary → сравнение eval.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


import numpy as np
import pandas as pd

from appa.core.patch_approximator import PatchApproximator
from appa.io.pmodel import load_model, save_model, summary, validate_model


# ============ Загрузка и очистка ============
data = pd.read_csv('synthetic_data.csv')
sec = data[data['section_id'] == 0].copy().sort_values('angle_deg').reset_index(drop=True)

# Простая очистка — как в pipeline
r = sec['radius_mm'].values
median_r = np.median(r)
abs_dev = np.abs(r - median_r)
mad = np.median(abs_dev)
mask_out = abs_dev > 9.5 * mad
sec_clean = sec[~mask_out]

angles = sec_clean['angle_deg'].values
radii = sec_clean['radius_mm'].values
print(f"Всего: {len(sec)}, чистых: {len(sec_clean)}")


# ============ Обучение ============
approx = PatchApproximator(
    n_patches=8, deg_min=4, deg_max=14,
    amplitude_scale=180.0, overlap_train=15.0, overlap_use=5.0,
)
approx.fit(angles, radii)
approx.statistics_['n_outliers_removed'] = int(mask_out.sum())

# RMSE против эталона
angles_grid = np.linspace(0, 360, 3600, endpoint=False)
fitted = approx.eval(angles_grid)
ideal = np.interp(angles_grid,
                  sec['angle_deg'].values,
                  sec['radius_ideal_mm'].values)
rmse_global = float(np.sqrt(np.mean((fitted - ideal) ** 2)))
approx.statistics_['rmse_global_mm'] = rmse_global
print(f"RMSE global: {rmse_global:.6f} мм")
print(f"Степени патчей: {approx.get_degrees()}")


# ============ Сохранение ============
save_model(
    approx,
    'section_0.pmodel.json',
    meta={
        'section_id': 0,
        'height_mm': 0.0,
        'source': 'synthetic_data.csv',
        'description': 'Сечение 0, сфера R=15',
    },
)
print("Сохранено: section_0.pmodel.json")


# ============ Валидация ============
ok, errors = validate_model('section_0.pmodel.json')
print(f"\nВалидация: {'OK' if ok else 'ОШИБКИ'}")
for e in errors:
    print(f"  - {e}")


# ============ Summary ============
print()
summary('section_0.pmodel.json')


# ============ Загрузка и проверка ============
loaded = load_model('section_0.pmodel.json')
fitted2 = loaded.eval(angles_grid)

max_diff = float(np.max(np.abs(fitted - fitted2)))
print(f"\nМаксимальное расхождение после load: {max_diff:.2e}")
assert max_diff < 1e-12, "Загрузка не воспроизводит модель!"
print("OK: модель воспроизводится точно")
