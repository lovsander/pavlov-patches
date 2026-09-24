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

# ============ РЕСЕМПЛИНГ (для Фурье) ============
def resample_to_grid(sec_clean, n_target=720):
    if len(sec_clean) < 10:
        return None
    sec_clean = sec_clean.sort_values('angle_deg').reset_index(drop=True)
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values
    angles = np.append(angles, 360.0)
    radii = np.append(radii, radii[0])
    target_angles = np.linspace(0, 360, n_target, endpoint=False)
    target_radii = np.interp(target_angles, angles, radii)
    return pd.DataFrame({'angle_deg': target_angles, 'radius_mm': target_radii})

# ============ ФУРЬЕ ============
def fourier_fit(angles_deg, radii, n_harmonics):
    phi = np.deg2rad(angles_deg)
    n = len(phi)
    A = np.ones((n, 1 + 2 * n_harmonics))
    for k in range(1, n_harmonics + 1):
        A[:, 2*k - 1] = np.cos(k * phi)
        A[:, 2*k] = np.sin(k * phi)
    coefs, _, _, _ = np.linalg.lstsq(A, radii, rcond=None)
    return coefs

def fourier_eval(angles_deg, coefs, n_harmonics):
    phi = np.deg2rad(angles_deg)
    result = np.full_like(phi, coefs[0], dtype=float)
    for k in range(1, n_harmonics + 1):
        result += coefs[2*k - 1] * np.cos(k * phi)
        result += coefs[2*k] * np.sin(k * phi)
    return result

# ============ 8 ЛОСКУТОВ (для сравнения) ============
def approximate_npatches(sec_clean, degree=6, overlap=35, n_patches=8):
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values
    sector = 360 / n_patches
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(n_patches)]
    half = half_sector + overlap
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
    fitted = np.zeros_like(angles, dtype=float)
    sector = 360 / n_patches
    half = sector / 2 + overlap
    for i, a in enumerate(angles):
        weighted_sum = 0.0
        total_w = 0.0
        for c, coefs in coefs_list:
            d = abs((a - c + 180) % 360 - 180)
            if d >= half:
                continue
            local = (a - c + 180) % 360 - 180
            r = np.polyval(coefs, local)
            t = 1.0 - d / half
            w = 3 * t ** 2 - 2 * t ** 3
            weighted_sum += w * r
            total_w += w
        fitted[i] = weighted_sum / total_w if total_w > 0 else np.nan
    return fitted

# ============ МЕТРИКИ ============
def compute_metrics(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values, sec_ideal['radius_ideal_mm'].values)
    rmse = np.sqrt(np.mean((fitted - ideal) ** 2))
    corr = np.corrcoef(fitted, ideal)[0, 1]
    max_err = np.max(np.abs(fitted - ideal))
    return rmse, corr, max_err

# ============ СРАВНЕНИЕ ============
HARMONICS_LIST = [5,8,10,12,14,16]
N_PATCHES = 8
DEGREE = 6
OVERLAP = 35

# Сводная таблица: для каждого сечения и каждого метода — RMSE
comparison = []

for sid in data['section_id'].unique():
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    if len(sec_clean) < 20:
        continue

    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()
    angles_grid = np.linspace(0, 360, 720, endpoint=False)

    # 8 лоскутов
    coefs_list = approximate_npatches(sec_clean, degree=DEGREE, overlap=OVERLAP, n_patches=N_PATCHES)
    fitted_patches = blend_npatches(angles_grid, coefs_list, overlap=OVERLAP, n_patches=N_PATCHES)
    rmse_p, corr_p, max_p = compute_metrics(angles_grid, fitted_patches, sec_ideal)

    # Фурье — для каждого N
    sec_res = resample_to_grid(sec_clean, n_target=720)
    row = {
        'section_id': sid,
        'patches_rmse': rmse_p,
        'patches_corr': corr_p,
        'patches_max': max_p,
    }
    for N in HARMONICS_LIST:
        coefs = fourier_fit(sec_res['angle_deg'].values, sec_res['radius_mm'].values, N)
        fitted = fourier_eval(angles_grid, coefs, N)
        rmse, corr, max_err = compute_metrics(angles_grid, fitted, sec_ideal)
        row[f'fourier_{N}_rmse'] = rmse
        row[f'fourier_{N}_corr'] = corr
        row[f'fourier_{N}_max'] = max_err
    comparison.append(row)

comp_df = pd.DataFrame(comparison)

# ============ ИТОГОВАЯ ТАБЛИЦА (СРЕДНИЕ) ============
print("\n=== СРАВНЕНИЕ: 8 ЛОСКУТОВ vs ФУРЬЕ (разное число гармоник) ===\n")
print(f"{'Метод':<25} {'RMSE (ср.)':<15} {'Корр. (ср.)':<15} {'Макс (ср.)':<15}")
print("-" * 70)

print(f"{'8 лоскутов':<25} {comp_df['patches_rmse'].mean():<15.5f} "
      f"{comp_df['patches_corr'].mean():<15.6f} {comp_df['patches_max'].mean():<15.5f}")

for N in HARMONICS_LIST:
    print(f"{'Фурье N=' + str(N):<25} {comp_df[f'fourier_{N}_rmse'].mean():<15.5f} "
          f"{comp_df[f'fourier_{N}_corr'].mean():<15.6f} {comp_df[f'fourier_{N}_max'].mean():<15.5f}")

# ============ ГРАФИК RMSE(N) ============
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# График 1: RMSE vs N гармоник
axes[0].plot(HARMONICS_LIST,
             [comp_df[f'fourier_{N}_rmse'].mean() for N in HARMONICS_LIST],
             'bo-', label='Фурье')
axes[0].axhline(comp_df['patches_rmse'].mean(), color='orange', lw=2,
                linestyle='--', label='8 лоскутов')
axes[0].set_xlabel('Число гармоник N')
axes[0].set_ylabel('Средний RMSE, мм')
axes[0].set_title('RMSE vs Число гармоник Фурье')
axes[0].legend()
axes[0].grid(True, alpha=0.3)

# График 2: Корреляция vs N
axes[1].plot(HARMONICS_LIST,
             [comp_df[f'fourier_{N}_corr'].mean() for N in HARMONICS_LIST],
             'bo-', label='Фурье')
axes[1].axhline(comp_df['patches_corr'].mean(), color='orange', lw=2,
                linestyle='--', label='8 лоскутов')
axes[1].set_xlabel('Число гармоник N')
axes[1].set_ylabel('Средняя корреляция')
axes[1].set_title('Корреляция vs Число гармоник Фурье')
axes[1].legend()
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('comparison_fourier_patches.png', dpi=120)
print("\nГрафик: comparison_fourier_patches.png")

# ============ ДЕТАЛЬНЫЙ ГРАФИК ПО СЕЧЕНИЯМ ============
fig2, axes2 = plt.subplots(2, 2, figsize=(14, 12))
axes2 = axes2.flatten()
SECTIONS_TO_SHOW = [0, 3, 6, 9]

for sid in SECTIONS_TO_SHOW:
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()
    angles_grid = np.linspace(0, 360, 720, endpoint=False)

    # 8 лоскутов
    coefs_list = approximate_npatches(sec_clean, degree=DEGREE, overlap=OVERLAP, n_patches=N_PATCHES)
    fitted_p = blend_npatches(angles_grid, coefs_list, overlap=OVERLAP, n_patches=N_PATCHES)

    # Фурье 
    sec_res = resample_to_grid(sec_clean, n_target=720)
    coefs = fourier_fit(sec_res['angle_deg'].values, sec_res['radius_mm'].values, 6)
    fitted_f = fourier_eval(angles_grid, coefs, 6)

    ax = axes2[SECTIONS_TO_SHOW.index(sid)]
    ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'], 'b.', markersize=2, alpha=0.3, label='Данные')
    ax.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'], 'green', lw=2, linestyle=':', label='Эталон')
    ax.plot(angles_grid, fitted_p, 'orange', lw=2, label='8 лоскутов')
    ax.plot(angles_grid, fitted_f, 'red', lw=1.5, linestyle='--', label='Фурье N=6')

    # Метрики
    rmse_p, corr_p, _ = compute_metrics(angles_grid, fitted_p, sec_ideal)
    rmse_f, corr_f, _ = compute_metrics(angles_grid, fitted_f, sec_ideal)

    ax.set_title(f'Сечение {sid}: лоскуты RMSE={rmse_p:.4f}, Фурье RMSE={rmse_f:.4f}')
    ax.set_xlabel('Угол, °')
    ax.set_ylabel('Радиус, мм')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('detail_comparison.png', dpi=120)
print("График: detail_comparison.png")