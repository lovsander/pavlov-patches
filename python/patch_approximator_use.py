"""
demo_patch_approximator.py

Демонстрация: OutlierCleaner + PatchApproximator.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from outlier_cleaner import OutlierCleaner
from patch_approximator import PatchApproximator


# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')


# ============ ОЧИСТКА (через класс) ============
cleaner = OutlierCleaner(
    threshold_deriv=0.5,
    mad_k=9.5,
    z_threshold=3.5,
)

print("=== ОЧИСТКА ===")
cleaned_list = []
for sid in data['section_id'].unique():
    sec = data[data['section_id'] == sid].copy().sort_values('angle_deg').reset_index(drop=True)
    angles = sec['angle_deg'].values
    radii = sec['radius_mm'].values

    mask = cleaner.clean(angles, radii)
    sec['is_outlier_detected'] = mask
    cleaned_list.append(sec)

    stats = cleaner.stats(angles, radii)
    print(f"  Сечение {sid}: "
          f"deriv={stats['n_deriv']}, "
          f"mad={stats['n_mad']}, "
          f"z={stats['n_z']}, "
          f"итого {stats['n_total_outliers']}/{stats['n_total']} "
          f"({stats['percent_outliers']:.1f}%)")

cleaned = pd.concat(cleaned_list, ignore_index=True)


# ============ ПОДГОТОВКА ============
SID = 0
sec_full = cleaned[cleaned['section_id'] == SID].copy()
sec_clean = sec_full[~sec_full['is_outlier_detected']]

angles_raw = sec_clean['angle_deg'].values
radii_raw = sec_clean['radius_mm'].values

sec_ideal = data[data['section_id'] == SID][['angle_deg', 'radius_ideal_mm']].copy()

print(f"\nСечение {SID}: всего {len(sec_full)}, чистых {len(sec_clean)}")


# ============ ОБУЧЕНИЕ ============
print("\n=== ОБУЧЕНИЕ PatchApproximator ===")

approx = PatchApproximator(
    n_patches=8,
    deg_min=4,
    deg_max=14,
    amplitude_scale=180.0,
    overlap_train=15.0,
    overlap_use=5.0,
)

approx.fit(angles_raw, radii_raw)

degrees = approx.get_degrees()
print(f"Степени: {degrees}")
print(f"Суммарно коэффициентов: {sum(d + 1 for d in degrees)}")


# ============ ВОССТАНОВЛЕНИЕ ============
angles_grid = np.linspace(0, 360, 1440, endpoint=False)
fitted = approx.eval(angles_grid)

ideal_grid = np.interp(angles_grid, sec_ideal['angle_deg'].values,
                       sec_ideal['radius_ideal_mm'].values)

rmse = np.sqrt(np.mean((fitted - ideal_grid) ** 2))
mae = np.mean(np.abs(fitted - ideal_grid))
max_err = np.max(np.abs(fitted - ideal_grid))

print(f"\n=== МЕТРИКИ ===")
print(f"RMSE:         {rmse:.5f} мм")
print(f"MAE:          {mae:.5f} мм")
print(f"Макс. ошибка: {max_err:.5f} мм")


# ============ СОХРАНЕНИЕ / ЗАГРУЗКА ============
model_path = f'model_pavlov_section{SID}.npz'
approx.save(model_path)
print(f"\nМодель сохранена: {model_path}")

approx_loaded = PatchApproximator.load(model_path)
fitted_loaded = approx_loaded.eval(angles_grid)
print(f"Воспроизведение: {np.allclose(fitted, fitted_loaded)}")


# ============ ВИЗУАЛИЗАЦИЯ ============
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10),
                                gridspec_kw={'height_ratios': [3, 1]})

# Верх
ax1.plot(sec_full['angle_deg'], sec_full['radius_mm'],
         'b.', markersize=2, alpha=0.2, label='Данные')

# Найденные выбросы
sec_out = sec_full[sec_full['is_outlier_detected']]
ax1.scatter(sec_out['angle_deg'], sec_out['radius_mm'],
            s=30, c='red', marker='x', linewidths=1.5,
            label=f'Выбросы ({len(sec_out)})', zorder=5)

ax1.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2, alpha=0.5, label='Эталон')
ax1.plot(angles_grid, fitted, 'orange', lw=3,
         label=f'Модель (RMSE={rmse:.5f})', zorder=10)

# Патчи
colors = plt.cm.tab10(np.linspace(0, 1, approx.n_patches))
for j, p in enumerate(approx.patches_):
    a_local = np.linspace(-p['half_train'], p['half_train'], 300)
    a_global_raw = p['center'] + a_local
    r_poly = np.polyval(p['coefs'], a_local)

    mask_neg = a_global_raw < 0
    mask_over = a_global_raw > 360
    mask_ok = ~mask_neg & ~mask_over

    if mask_ok.any():
        ax1.plot(a_global_raw[mask_ok], r_poly[mask_ok],
                 color=colors[j], lw=1, alpha=0.3)
    if mask_neg.any():
        ax1.plot(a_global_raw[mask_neg] + 360, r_poly[mask_neg],
                 color=colors[j], lw=1, alpha=0.3)
    if mask_over.any():
        ax1.plot(a_global_raw[mask_over] - 360, r_poly[mask_over],
                 color=colors[j], lw=1, alpha=0.3)

ax1.set_title(f'Сечение {SID}: очистка + PatchApproximator (RMSE={rmse:.5f})')
ax1.set_xlabel('Угол, °')
ax1.set_ylabel('Радиус, мм')
ax1.legend(fontsize=9, loc='upper right')
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 360)

# Низ: остатки
residuals = fitted - ideal_grid
ax2.plot(angles_grid, residuals, 'purple', lw=1.5, label='Остаток')
ax2.axhline(0, color='k', lw=0.5)
ax2.axhline(0.05, color='r', lw=0.8, linestyle='--', alpha=0.5, label='±0.05')
ax2.axhline(-0.05, color='r', lw=0.8, linestyle='--', alpha=0.5)
ax2.set_title(f'Остатки: RMSE={rmse:.5f}, max={max_err:.5f}')
ax2.set_xlabel('Угол, °')
ax2.set_ylabel('Остаток, мм')
ax2.legend()
ax2.grid(True, alpha=0.3)
ax2.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('demo_full_pipeline.png', dpi=120)
print(f"\nГрафик: demo_full_pipeline.png")


# ============ ПРОГОН ПО ВСЕМ СЕЧЕНИЯМ ============
print("\n=== ПРОГОН ПО ВСЕМ СЕЧЕНИЯМ ===")

results = []
for sid in data['section_id'].unique():
    sec_full_i = cleaned[cleaned['section_id'] == sid]
    sec_clean_i = sec_full_i[~sec_full_i['is_outlier_detected']]

    if len(sec_clean_i) < 20:
        continue

    a_raw = sec_clean_i['angle_deg'].values
    r_raw = sec_clean_i['radius_mm'].values

    approx_i = PatchApproximator(
        n_patches=8, deg_min=4, deg_max=14,
        amplitude_scale=180.0, overlap_train=15.0, overlap_use=5.0,
    )
    approx_i.fit(a_raw, r_raw)
    fitted_i = approx_i.eval(angles_grid)

    sec_ideal_i = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']]
    ideal_i = np.interp(angles_grid, sec_ideal_i['angle_deg'].values,
                         sec_ideal_i['radius_ideal_mm'].values)
    rmse_i = np.sqrt(np.mean((fitted_i - ideal_i) ** 2))

    degrees_i = approx_i.get_degrees()
    results.append({'section': sid, 'rmse': rmse_i, 'degrees': degrees_i})

    print(f"  Сечение {sid}: RMSE={rmse_i:.5f}, deg={degrees_i}")

avg_rmse = np.mean([r['rmse'] for r in results])
print(f"\nСредний RMSE: {avg_rmse:.5f}")