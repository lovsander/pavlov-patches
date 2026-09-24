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


# ============ АППРОКСИМАЦИЯ: N ЛОСКУТОВ ============
def approximate_npatches(sec_clean, degree=6, overlap=35, n_patches=8):
    """
    N лоскутов полинома.
    n_patches: число секторов (должно быть >= 2)
    Каждый лоскут работает на секторе 360/n_patches с перекрытием overlap.
    """
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values

    sector = 360 / n_patches
    half_sector = sector / 2

    # Центры секторов
    centers = [i * sector + half_sector for i in range(n_patches)]
    half = half_sector + overlap

    # Обёртка: дублируем данные с ±360 для непрерывности
    angles_ext = np.concatenate([angles - 360, angles, angles + 360])
    radii_ext = np.concatenate([radii, radii, radii])

    coefs_list = []
    for c in centers:
        mask = (angles_ext >= c - half) & (angles_ext <= c + half)
        local_angles = angles_ext[mask] - c
        coefs = np.polyfit(local_angles, radii_ext[mask], degree)
        coefs_list.append((c, coefs))

    return coefs_list


def blend_npatches(angles, coefs_list, overlap=35, n_patches=8):
    """
    Blend N лоскутов.
    """
    fitted = np.zeros_like(angles, dtype=float)
    sector = 360 / n_patches
    half_sector = sector / 2
    half = half_sector + overlap

    for i, a in enumerate(angles):
        weighted_sum = 0.0
        total_w = 0.0

        for j, (c, coefs) in enumerate(coefs_list):
            d = abs((a - c + 180) % 360 - 180)

            if d >= half:
                continue

            local = (a - c + 180) % 360 - 180
            r = np.polyval(coefs, local)

            # Smoothstep
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

# === ПАРАМЕТРЫ ===
N_PATCHES = 8
DEGREE = 6
OVERLAP = 35

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
axes = axes.flatten()

for sid in data['section_id'].unique():
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    if len(sec_clean) < 20:
        continue

    coefs_list = approximate_npatches(sec_clean, degree=DEGREE, overlap=OVERLAP, n_patches=N_PATCHES)

    angles_grid = np.linspace(0, 360, 720, endpoint=False)
    fitted = blend_npatches(angles_grid, coefs_list, overlap=OVERLAP, n_patches=N_PATCHES)

    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()
    rmse, corr, max_err = compute_metrics(angles_grid, fitted, sec_ideal)

    results.append({'section_id': sid, 'rmse': rmse, 'corr': corr, 'max_err': max_err})

    if sid in SECTIONS_TO_SHOW:
        ax = axes[SECTIONS_TO_SHOW.index(sid)]

        ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
                'b.', markersize=2, label='Данные (чистые)', alpha=0.4)

        # Лоскуты
        colors = plt.cm.tab10(np.linspace(0, 1, N_PATCHES))
        sector = 360 / N_PATCHES
        half_sector = sector / 2
        half = half_sector + OVERLAP

        for j, (c, coefs) in enumerate(coefs_list):
            a_local = np.linspace(-half, half, 200)
            a_global = c + a_local
            r_vals = np.polyval(coefs, a_local)

            # Разбиваем на отрезки, если выход за 0 или 360
            if a_global.min() < 0:
                mask_neg = a_global < 0
                ax.plot(a_global[mask_neg] + 360, r_vals[mask_neg],
                        color=colors[j], lw=1.0, linestyle='--', alpha=0.8)
                mask_pos = ~mask_neg
                ax.plot(a_global[mask_pos], r_vals[mask_pos],
                        color=colors[j], lw=1.0, linestyle='--', alpha=0.8,
                        label=f'Лоскут {j+1}')
            elif a_global.max() > 360:
                mask_over = a_global > 360
                ax.plot(a_global[mask_over] - 360, r_vals[mask_over],
                        color=colors[j], lw=1.0, linestyle='--', alpha=0.8)
                mask_rest = ~mask_over
                ax.plot(a_global[mask_rest], r_vals[mask_rest],
                        color=colors[j], lw=1.0, linestyle='--', alpha=0.8,
                        label=f'Лоскут {j+1}')
            else:
                ax.plot(a_global, r_vals, color=colors[j], lw=1.0,
                        linestyle='--', alpha=0.8, label=f'Лоскут {j+1}')

        ax.plot(angles_grid, fitted, 'orange', lw=2.5, label='Blend (итог)')
        ax.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
                'green', lw=1.5, linestyle=':', label='Эталон', alpha=0.9)

        ax.set_title(f'Сечение {sid}: RMSE={rmse:.4f}, corr={corr:.4f}, макс={max_err:.3f}')
        ax.set_xlabel('Угол, °')
        ax.set_ylabel('Радиус, мм')
        ax.legend(fontsize=6, loc='best', ncol=3)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('approximation_8patches.png', dpi=120)
print("График: approximation_8patches.png")

# ============ ИТОГИ ============
print(f"\n=== РЕЗУЛЬТАТЫ ({N_PATCHES} ЛОСКУТОВ, степень {DEGREE}, overlap {OVERLAP}°) ===")
print(f"{'Сечение':<10} {'RMSE, мм':<12} {'Корреляция':<12} {'Макс. ошибка':<12}")
for r in results:
    print(f"{r['section_id']:<10} {r['rmse']:<12.4f} {r['corr']:<12.6f} {r['max_err']:<12.4f}")

avg_rmse = np.mean([r['rmse'] for r in results])
avg_corr = np.mean([r['corr'] for r in results])
avg_max = np.mean([r['max_err'] for r in results])
print(f"\nСредний RMSE: {avg_rmse:.4f} мм")
print(f"Средняя корреляция: {avg_corr:.6f}")
print(f"Средняя макс. ошибка: {avg_max:.4f} мм")