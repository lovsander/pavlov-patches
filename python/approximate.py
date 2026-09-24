import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')
print(f"Загружено {len(data)} точек, {data['section_id'].nunique()} сечений")

# ============ ОЧИСТКА ============
def clean_section(sec, threshold_deriv=1.2, mad_k=6.0):
    sec = sec.sort_values('angle_deg').reset_index(drop=True)
    r = sec['radius_mm'].values
    dr = np.diff(r, prepend=r[0])
    dr[0] = r[0] - r[-1]
    mask_deriv = np.abs(dr) > threshold_deriv
    median_r = np.median(r)
    abs_dev = np.abs(r - median_r)
    mad = np.median(abs_dev)
    mask_mad = abs_dev > (mad_k * mad)
    sec['is_outlier_detected'] = mask_deriv | mask_mad
    return sec

cleaned = []
for sid in data['section_id'].unique():
    sec = data[data['section_id'] == sid].copy()
    cleaned.append(clean_section(sec))
cleaned = pd.concat(cleaned, ignore_index=True)


# ============ АППРОКСИМАЦИЯ (2 ЛОСКУТА) — ПО ВСЕМ ЧИСТЫМ ТОЧКАМ ============
def approximate_2patches(sec_clean, degree=16, overlap=30):
    """
    2 лоскута полинома — как в Delphi.
    
    Лоскут 1: углы 0..360 (глобальный).
    Лоскут 2: углы сдвинуты на +360, если < 180.
    """
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values

    # --- Лоскут 1: как есть ---
    coefs1 = np.polyfit(angles, radii, degree)

    # --- Лоскут 2: сдвиг для углов < 180 ---
    angles2 = angles.copy()
    mask_small = angles2 < 180.0
    angles2[mask_small] = angles2[mask_small] + 360.0
    coefs2 = np.polyfit(angles2, radii, degree)

    return coefs1, coefs2


def blend_2patches(angles, coefs1, coefs2, overlap=45):
    """
    Blend — точно как в Polinom_Blend_Equation.
    
    Зоны:
    - 135–225: только лоскут 1
    - 315–45: только лоскут 2
    - 45–135: blend
    - 225–315: blend
    """
    fitted = np.zeros_like(angles, dtype=float)

    for i, a in enumerate(angles):
        r1 = np.polyval(coefs1, a)

        # Для лоскута 2 — сдвигаем угол, если < 180
        a2 = a
        if a < 180.0:
            a2 = a + 360.0
        r2 = np.polyval(coefs2, a2)

        # Определяем зону
        if 135 <= a < 225:
            # Только лоскут 1
            fitted[i] = r1
        elif a >= 315 or a < 45:
            # Только лоскут 2
            fitted[i] = r2
        elif 45 <= a < 135:
            # Blend: лоскут 2 -> лоскут 1
            koef1 = (135 - a) / 90
            fitted[i] = r1 * (1 - koef1) + r2 * koef1
        elif 225 <= a < 315:
            # Blend: лоскут 1 -> лоскут 2
            koef1 = 1 - (315 - a) / 90
            fitted[i] = r1 * (1 - koef1) + r2 * koef1

    return fitted


# ============ МЕТРИКИ ============
def compute_metrics(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values, sec_ideal['radius_ideal_mm'].values)
    rmse = np.sqrt(np.mean((fitted - ideal) ** 2))
    corr = np.corrcoef(fitted, ideal)[0, 1]
    max_err = np.max(np.abs(fitted - ideal))
    return rmse, corr, max_err


# ============ ОБРАБОТКА ============
results = []
SECTIONS_TO_SHOW = [0, 3, 6, 9]
DEGREE = 6
OVERLAP = 45

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
axes = axes.flatten()

for sid in data['section_id'].unique():
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    if len(sec_clean) < 20:
        continue

    # --- Аппроксимация ПО ВСЕМ ЧИСТЫМ ТОЧКАМ ---
    coefs1, coefs2 = approximate_2patches(sec_clean, degree=DEGREE, overlap=OVERLAP)

    # --- Восстановление на 360 точках (только для визуализации и метрик) ---
    angles_grid = np.linspace(0, 360, 360, endpoint=False)
    fitted = blend_2patches(angles_grid, coefs1, coefs2, overlap=OVERLAP)

    # Метрики — сравнение с эталоном
    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()
    rmse, corr, max_err = compute_metrics(angles_grid, fitted, sec_ideal)

    results.append({'section_id': sid, 'rmse': rmse, 'corr': corr, 'max_err': max_err})

    # --- Визуализация ---
    if sid in SECTIONS_TO_SHOW:
        ax = axes[SECTIONS_TO_SHOW.index(sid)]

        # Чистые данные (все, не ресемпленные!)
        ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
                'b.', markersize=2, label='Данные (чистые, все)', alpha=0.5)

        # Лоскут 1 — только на 0..180
        a1 = np.linspace(0, 180, 180)
        ax.plot(a1, np.polyval(coefs1, a1), 'r--', lw=1.5, label='Лоскут 1 (0–180)')

        # Лоскут 2 — только на 180..360
        a2 = np.linspace(180, 360, 180)
        ax.plot(a2, np.polyval(coefs2, a2), 'm--', lw=1.5, label='Лоскут 2 (180–360)')

        # Blend (итог)
        ax.plot(angles_grid, fitted, 'orange', lw=2.5, label='Blend (итог)')

        # Эталон
        ax.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
                'green', lw=1.5, linestyle=':', label='Эталон', alpha=0.8)

        # Зоны перекрытия
        ax.axvspan(0, OVERLAP, color='yellow', alpha=0.15)
        ax.axvspan(180 - OVERLAP, 180 + OVERLAP, color='yellow', alpha=0.15, label='Зона blend')
        ax.axvspan(360 - OVERLAP, 360, color='yellow', alpha=0.15)

        ax.set_title(f'Сечение {sid}: RMSE={rmse:.3f}, corr={corr:.4f}')
        ax.set_xlabel('Угол, °')
        ax.set_ylabel('Радиус, мм')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('approximation_2patches.png', dpi=120)
print("График: approximation_2patches.png")

# ============ ИТОГИ ============
print("\n=== РЕЗУЛЬТАТЫ (2 ЛОСКУТА, ПО ВСЕМ ЧИСТЫМ ТОЧКАМ) ===")
print(f"{'Сечение':<10} {'RMSE, мм':<12} {'Корреляция':<12} {'Макс. ошибка':<12}")
for r in results:
    print(f"{r['section_id']:<10} {r['rmse']:<12.4f} {r['corr']:<12.6f} {r['max_err']:<12.4f}")

avg_rmse = np.mean([r['rmse'] for r in results])
avg_corr = np.mean([r['corr'] for r in results])
print(f"\nСредний RMSE: {avg_rmse:.4f} мм")
print(f"Средняя корреляция: {avg_corr:.6f}")