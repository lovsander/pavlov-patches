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

# ============ АППРОКСИМАЦИЯ: 4 ЛОСКУТА ============
def approximate_4patches(sec_clean, degree=6, overlap=25):
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values

    centers = [45, 135, 225, 315]
    half = 45 + overlap

    angles_ext = np.concatenate([angles - 360, angles, angles + 360])
    radii_ext = np.concatenate([radii, radii, radii])

    coefs_list = []
    for c in centers:
        mask = (angles_ext >= c - half) & (angles_ext <= c + half)
        local_angles = angles_ext[mask] - c
        coefs = np.polyfit(local_angles, radii_ext[mask], degree)
        coefs_list.append((c, coefs))

    return coefs_list

def blend_4patches(angles, coefs_list, overlap=25):
    fitted = np.zeros_like(angles, dtype=float)
    centers = [c for c, _ in coefs_list]
    half = 45 + overlap

    for i, a in enumerate(angles):
        weighted_sum = 0.0
        total_w = 0.0

        for j, (c, coefs) in enumerate(coefs_list):
            d = abs((a - c + 180) % 360 - 180)

            if d >= half:
                continue

            local = (a - c + 180) % 360 - 180
            r = np.polyval(coefs, local)

            t = 1.0 - d / half
            w = 3 * t ** 2 - 2 * t ** 3

            weighted_sum += w * r
            total_w += w

        if total_w > 0:
            fitted[i] = weighted_sum / total_w
        else:
            fitted[i] = np.nan

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
OVERLAP = 25

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
axes = axes.flatten()

for sid in data['section_id'].unique():
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    if len(sec_clean) < 20:
        continue

    coefs_list = approximate_4patches(sec_clean, degree=DEGREE, overlap=OVERLAP)

    angles_grid = np.linspace(0, 360, 360, endpoint=False)
    fitted = blend_4patches(angles_grid, coefs_list, overlap=OVERLAP)

    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()
    rmse, corr, max_err = compute_metrics(angles_grid, fitted, sec_ideal)

    results.append({'section_id': sid, 'rmse': rmse, 'corr': corr, 'max_err': max_err})

    if sid in SECTIONS_TO_SHOW:
        ax = axes[SECTIONS_TO_SHOW.index(sid)]

        ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
                'b.', markersize=2, label='Данные (чистые)', alpha=0.4)

        # ===== ЛОСКУТЫ =====
        colors = ['red', 'magenta', 'purple', 'brown']
        for j, (c, coefs) in enumerate(coefs_list):
            half = 45 + OVERLAP
            a_local = np.linspace(-half, half, 200)
            a_global = c + a_local

            r_vals = np.polyval(coefs, a_local)

            # Разбиваем на отрезки, если выход за 0 или 360
            if a_global.min() < 0:
                mask_neg = a_global < 0
                a_neg = a_global[mask_neg] + 360
                r_neg = r_vals[mask_neg]
                ax.plot(a_neg, r_neg, color=colors[j], lw=1.2, linestyle='--',
                        label=f'Лоскут {j+1} ({c}°)')

                mask_pos = ~mask_neg
                a_pos = a_global[mask_pos]
                r_pos = r_vals[mask_pos]
                ax.plot(a_pos, r_pos, color=colors[j], lw=1.2, linestyle='--')

            elif a_global.max() > 360:
                mask_over = a_global > 360
                a_over = a_global[mask_over] - 360
                r_over = r_vals[mask_over]
                ax.plot(a_over, r_over, color=colors[j], lw=1.2, linestyle='--',
                        label=f'Лоскут {j+1} ({c}°)')

                mask_rest = ~mask_over
                a_rest = a_global[mask_rest]
                r_rest = r_vals[mask_rest]
                ax.plot(a_rest, r_rest, color=colors[j], lw=1.2, linestyle='--')

            else:
                ax.plot(a_global, r_vals, color=colors[j], lw=1.2, linestyle='--',
                        label=f'Лоскут {j+1} ({c}°)')

        ax.plot(angles_grid, fitted, 'orange', lw=2.5, label='Blend (итог)')
        ax.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
                'green', lw=1.5, linestyle=':', label='Эталон', alpha=0.8)

        ax.set_title(f'Сечение {sid}: RMSE={rmse:.3f}, corr={corr:.4f}')
        ax.set_xlabel('Угол, °')
        ax.set_ylabel('Радиус, мм')
        ax.legend(fontsize=7, loc='best')
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('approximation_4patches.png', dpi=120)
print("График: approximation_4patches.png")

# ============ ИТОГИ ============
print("\n=== РЕЗУЛЬТАТЫ (4 ЛОСКУТА) ===")
print(f"{'Сечение':<10} {'RMSE, мм':<12} {'Корреляция':<12} {'Макс. ошибка':<12}")
for r in results:
    print(f"{r['section_id']:<10} {r['rmse']:<12.4f} {r['corr']:<12.6f} {r['max_err']:<12.4f}")

avg_rmse = np.mean([r['rmse'] for r in results])
avg_corr = np.mean([r['corr'] for r in results])
print(f"\nСредний RMSE: {avg_rmse:.4f} мм")
print(f"Средняя корреляция: {avg_corr:.6f}")