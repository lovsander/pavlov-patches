import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')
print(f"Загружено {len(data)} точек, {data['section_id'].nunique()} сечений")

# ============ ОЧИСТКА ОДНОГО СЕЧЕНИЯ ============
def clean_section(sec, threshold_deriv=1.2, mad_k=6.0):
    """
    Очистка одного сечения от выбросов.

    sec: DataFrame с колонками angle_deg, radius_mm
    threshold_deriv: порог для производной
    mad_k: коэффициент для MAD

    Возвращает: sec с колонками is_outlier_detected
    """
    sec = sec.sort_values('angle_deg').reset_index(drop=True)
    r = sec['radius_mm'].values
    n = len(r)

    # --- Метод 1: по производной ---
    # Производная (разница между соседними точками)
    dr = np.diff(r, prepend=r[0])
    # Замыкаем: учитываем переход через 360 -> 0
    dr[0] = r[0] - r[-1]

    # Маска выбросов по производной
    mask_deriv = np.abs(dr) > threshold_deriv

    # --- Метод 2: MAD (робастная статистика) ---
    # Медиана радиусов
    median_r = np.median(r)
    # Абсолютные отклонения от медианы
    abs_dev = np.abs(r - median_r)
    # Медиана отклонений (MAD)
    mad = np.median(abs_dev)
    # Порог
    threshold_mad = mad_k * mad
    # Маска выбросов по MAD
    mask_mad = abs_dev > threshold_mad

    # --- Объединяем ---
    mask = mask_deriv | mask_mad

    sec['is_outlier_detected'] = mask
    return sec


# ============ ПРИМЕНЯЕМ КО ВСЕМ СЕЧЕНИЯМ ============
cleaned = []
for sid in data['section_id'].unique():
    sec = data[data['section_id'] == sid].copy()
    sec = clean_section(sec)
    cleaned.append(sec)

cleaned = pd.concat(cleaned, ignore_index=True)

# ============ МЕТРИКИ ============
# True Positive: выброс, найден как выброс
# False Positive: чистый, найден как выброс
# False Negative: выброс, не найден

tp = ((cleaned['is_outlier'] == True) & (cleaned['is_outlier_detected'] == True)).sum()
fp = ((cleaned['is_outlier'] == False) & (cleaned['is_outlier_detected'] == True)).sum()
fn = ((cleaned['is_outlier'] == True) & (cleaned['is_outlier_detected'] == False)).sum()
tn = ((cleaned['is_outlier'] == False) & (cleaned['is_outlier_detected'] == False)).sum()

precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

print(f"\n=== МЕТРИКИ ОЧИСТКИ ===")
print(f"True Positives:  {tp} (выбросы, найдены)")
print(f"False Positives: {fp} (чистые, ошибочно помечены)")
print(f"False Negatives: {fn} (выбросы, пропущены)")
print(f"True Negatives:  {tn} (чистые, верно оставлены)")
print(f"\nPrecision: {precision:.3f}")
print(f"Recall:    {recall:.3f}")
print(f"F1:        {f1:.3f}")

# ============ ВИЗУАЛИЗАЦИЯ ============
SECTIONS_TO_SHOW = [0, 3, 6, 9]
fig, axes = plt.subplots(2, 2, figsize=(14, 14))
axes = axes.flatten()

for ax, sid in zip(axes, SECTIONS_TO_SHOW):
    sec = cleaned[cleaned['section_id'] == sid]

    # Чистые (не выбросы по эталону)
    clean = sec[sec['is_outlier'] == False]
    # Истинные выбросы
    true_out = sec[sec['is_outlier'] == True]
    # Найденные выбросы (но чистые по эталону) — ложные
    false_out = sec[(sec['is_outlier'] == False) & (sec['is_outlier_detected'] == True)]

    ax.scatter(clean['x_mm'], clean['y_mm'], s=3, c='blue', label='Чистые')
    ax.scatter(true_out['x_mm'], true_out['y_mm'], s=25, c='red',
               label='Истинные выбросы', zorder=5)
    ax.scatter(false_out['x_mm'], false_out['y_mm'], s=25, c='orange',
               marker='x', label='Ложные срабатывания', zorder=6)

    # Центр
    ax.plot(0, 0, 'k+', markersize=15, markeredgewidth=2)

    ax.set_aspect('equal')
    ax.set_title(f'Сечение {sid}: TP={((sec["is_outlier"]==True) & (sec["is_outlier_detected"]==True)).sum()}, '
                 f'FP={len(false_out)}, FN={((sec["is_outlier"]==True) & (sec["is_outlier_detected"]==False)).sum()}')
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-25, 25)
    ax.set_ylim(-25, 25)

plt.tight_layout()
plt.savefig('cleaning.png', dpi=120)
print("\nГрафик: cleaning.png")