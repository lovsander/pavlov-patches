import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')

# ============ УСИЛЕННАЯ ОЧИСТКА ============
def clean_section(sec,
                  threshold_deriv=0.5,
                  mad_k=9.5,
                  z_threshold=3.5):
    sec = sec.sort_values('angle_deg').reset_index(drop=True)
    r = sec['radius_mm'].values
    n = len(r)

    dr = np.diff(r, prepend=r[0])
    dr[0] = r[0] - r[-1]
    mask_deriv = np.abs(dr) > threshold_deriv

    median_r = np.median(r)
    abs_dev = np.abs(r - median_r)
    mad = np.median(abs_dev)
    mask_mad = abs_dev > (mad_k * mad)

    if mad > 0:
        z_score = 0.6745 * abs_dev / mad
        mask_z = z_score > z_threshold
    else:
        mask_z = np.zeros(n, dtype=bool)

    sec['is_outlier_detected'] = mask_deriv | mask_mad | mask_z
    return sec


cleaned = []
for sid in data['section_id'].unique():
    sec = data[data['section_id'] == sid].copy()
    cleaned.append(clean_section(sec))
cleaned = pd.concat(cleaned, ignore_index=True)

# ============ СТАТИСТИКА ОЧИСТКИ ============
print("\n=== СТАТИСТИКА ОЧИСТКИ ===")
for sid in data['section_id'].unique():
    sub = cleaned[cleaned['section_id'] == sid]
    n_total = len(sub)
    n_detected = sub['is_outlier_detected'].sum()
    n_true = sub['is_outlier'].sum()
    tp = ((sub['is_outlier']) & (sub['is_outlier_detected'])).sum()
    fp = ((~sub['is_outlier']) & (sub['is_outlier_detected'])).sum()
    fn = ((sub['is_outlier']) & (~sub['is_outlier_detected'])).sum()
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    print(f"  Сечение {sid}: TP={tp}, FP={fp}, FN={fn}, "
          f"Precision={precision:.2f}, Recall={recall:.2f}")


# ============ ЛИНЕЙНЫЕ ГРАФИКИ ОЧИСТКИ ============
SECTIONS_TO_SHOW = [0, 3, 6, 9]
fig, axes = plt.subplots(2, 2, figsize=(16, 10))
axes = axes.flatten()

for ax, sid in zip(axes, SECTIONS_TO_SHOW):
    sub = cleaned[cleaned['section_id'] == sid].sort_values('angle_deg')

    # Чистые по истине
    clean_true = sub[~sub['is_outlier']]
    # Истинные выбросы
    true_out = sub[sub['is_outlier']]
    # Найденные выбросы (но чистые по истине) — ложные
    false_out = sub[(~sub['is_outlier']) & (sub['is_outlier_detected'])]
    # Найденные (истинные) — правильные
    true_pos = sub[(sub['is_outlier']) & (sub['is_outlier_detected'])]

    ax.plot(clean_true['angle_deg'], clean_true['radius_mm'],
            'b.', markersize=4, alpha=0.4, label='Чистые')
    ax.scatter(true_out['angle_deg'], true_out['radius_mm'],
               s=40, c='red', marker='o', label=f'Истинные выбросы (n={len(true_out)})',
               zorder=5, edgecolors='black', linewidths=0.5)
    ax.scatter(false_out['angle_deg'], false_out['radius_mm'],
               s=60, c='orange', marker='x', label=f'Ложные (n={len(false_out)})',
               zorder=6, linewidths=1.5)
    ax.scatter(true_pos['angle_deg'], true_pos['radius_mm'],
               s=80, c='lime', marker='^', label=f'Найдено верно (n={len(true_pos)})',
               zorder=7, edgecolors='black', linewidths=0.5)

    ax.set_title(f'Сечение {sid}: TP={len(true_pos)}, FP={len(false_out)}, FN={len(true_out)-len(true_pos)}')
    ax.set_xlabel('Угол, °')
    ax.set_ylabel('Радиус, мм')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('cleaning_linear.png', dpi=120)
print("\nСохранено: cleaning_linear.png")