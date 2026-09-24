import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')
print(f"Загружено {len(data)} точек")

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

# ============ ФУРЬЕ ============
def fourier_fit_raw(angles_deg, radii, n_harmonics):
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

# ============ ЛОСКУТЫ ============
def approximate_npatches(sec_clean, degree, overlap, n_patches):
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

def blend_npatches(angles, coefs_list, overlap, n_patches):
    fitted = np.zeros_like(angles, dtype=float)
    sector = 360 / n_patches
    half = sector / 2 + overlap
    for i, a in enumerate(angles):
        ws, ts = 0.0, 0.0
        for c, coefs in coefs_list:
            d = abs((a - c + 180) % 360 - 180)
            if d >= half:
                continue
            local = (a - c + 180) % 360 - 180
            r = np.polyval(coefs, local)
            t = 1.0 - d / half
            w = 3 * t ** 2 - 2 * t ** 3
            ws += w * r
            ts += w
        fitted[i] = ws / ts if ts > 0 else np.nan
    return fitted

# ============ МЕТРИКИ ============
def compute_metrics(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values, sec_ideal['radius_ideal_mm'].values)
    rmse = np.sqrt(np.mean((fitted - ideal) ** 2))
    corr = np.corrcoef(fitted, ideal)[0, 1]
    return rmse, corr

# ============ ПАРАМЕТРЫ ДЛЯ ОБЗОРА ============
FOURIER_LIST = [3, 4, 5, 6, 7, 8, 10, 12]
PATCHES_LIST = [
    (2, 7, 25), (2, 8, 35), (2, 10, 45),
    (3, 7, 25), (3, 8, 35),
    (4, 7, 35), (4, 8, 45),
    (6, 7, 35), (6, 8, 45),
    (8, 7, 45), (8, 8, 35), (8, 10, 25),
]

# ============ СЕЧЕНИЕ ДЛЯ ОБЗОРА ============
SID = 0
sec_clean = cleaned[(cleaned['section_id'] == SID) & (cleaned['is_outlier_detected'] == False)]
sec_ideal = data[data['section_id'] == SID][['angle_deg', 'radius_ideal_mm']].copy()
angles_raw = sec_clean['angle_deg'].values
radii_raw = sec_clean['radius_mm'].values

angles_grid = np.linspace(0, 360, 720, endpoint=False)

# ============ ГРАФИК 1: ВСЕ ФУРЬЕ ============
fig1, ax1 = plt.subplots(figsize=(14, 7))

ax1.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
         'b.', markersize=2, alpha=0.25, label='Данные')
ax1.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2.5, label='Эталон', alpha=0.6)

cmap_f = plt.cm.viridis
for i, N in enumerate(FOURIER_LIST):
    coefs = fourier_fit_raw(angles_raw, radii_raw, N)
    fitted = fourier_eval(angles_grid, coefs, N)
    rmse, corr = compute_metrics(angles_grid, fitted, sec_ideal)
    color = cmap_f(i / len(FOURIER_LIST))
    ax1.plot(angles_grid, fitted, color=color, lw=0.9,
             label=f'Фурье N={N} (RMSE={rmse:.5f})')

ax1.set_title(f'Сечение {SID}: все Фурье (N={FOURIER_LIST})')
ax1.set_xlabel('Угол, °')
ax1.set_ylabel('Радиус, мм')
ax1.legend(fontsize=8, ncol=2, loc='best')
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 360)
plt.tight_layout()
plt.savefig('all_fourier.png', dpi=120)
print("График: all_fourier.png")

# ============ ГРАФИК 2: ВСЕ ЛОСКУТЫ ============
fig2, ax2 = plt.subplots(figsize=(14, 7))

ax2.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
         'b.', markersize=2, alpha=0.25, label='Данные')
ax2.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2.5, label='Эталон', alpha=0.6)

cmap_p = plt.cm.plasma
for i, (n_p, deg, ov) in enumerate(PATCHES_LIST):
    coefs_list = approximate_npatches(sec_clean, deg, ov, n_p)
    fitted = blend_npatches(angles_grid, coefs_list, ov, n_p)
    rmse, corr = compute_metrics(angles_grid, fitted, sec_ideal)
    color = cmap_p(i / len(PATCHES_LIST))
    ax2.plot(angles_grid, fitted, color=color, lw=0.9,
             label=f'N={n_p}, deg={deg}, ov={ov} (RMSE={rmse:.5f})')

ax2.set_title(f'Сечение {SID}: все лоскуты (разные параметры)')
ax2.set_xlabel('Угол, °')
ax2.set_ylabel('Радиус, мм')
ax2.legend(fontsize=7, ncol=2, loc='best')
ax2.grid(True, alpha=0.3)
ax2.set_xlim(0, 360)
plt.tight_layout()
plt.savefig('all_patches.png', dpi=120)
print("График: all_patches.png")

# ============ ГРАФИК 3: СВОДКА — ЛУЧШИЙ ФУРЬЕ vs ЛУЧШИЙ ЛОСКУТ ============
best_f = {'N': None, 'rmse': 1e9, 'fitted': None}
for N in FOURIER_LIST:
    coefs = fourier_fit_raw(angles_raw, radii_raw, N)
    fitted = fourier_eval(angles_grid, coefs, N)
    rmse, _ = compute_metrics(angles_grid, fitted, sec_ideal)
    if rmse < best_f['rmse']:
        best_f = {'N': N, 'rmse': rmse, 'fitted': fitted}

best_p = {'params': None, 'rmse': 1e9, 'fitted': None}
for (n_p, deg, ov) in PATCHES_LIST:
    coefs_list = approximate_npatches(sec_clean, deg, ov, n_p)
    fitted = blend_npatches(angles_grid, coefs_list, ov, n_p)
    rmse, _ = compute_metrics(angles_grid, fitted, sec_ideal)
    if rmse < best_p['rmse']:
        best_p = {'params': (n_p, deg, ov), 'rmse': rmse, 'fitted': fitted}

fig3, ax3 = plt.subplots(figsize=(14, 7))
ax3.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
         'b.', markersize=2, alpha=0.25, label='Данные')
ax3.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2.5, label='Эталон', alpha=0.7)
ax3.plot(angles_grid, best_f['fitted'], 'red', lw=1.5,
         label=f'Лучший Фурье N={best_f["N"]} (RMSE={best_f["rmse"]:.5f})')
ax3.plot(angles_grid, best_p['fitted'], 'orange', lw=1.5, linestyle='--',
         label=f'Лучшие лоскуты {best_p["params"]} (RMSE={best_p["rmse"]:.5f})')
ax3.set_title(f'Сечение {SID}: лучший Фурье vs лучшие лоскуты')
ax3.set_xlabel('Угол, °')
ax3.set_ylabel('Радиус, мм')
ax3.legend(fontsize=9)
ax3.grid(True, alpha=0.3)
ax3.set_xlim(0, 360)
plt.tight_layout()
plt.savefig('best_vs_best.png', dpi=120)
print("График: best_vs_best.png")

print("\nГотово. Смотри:")
print("  all_fourier.png   — все Фурье на одном графике")
print("  all_patches.png   — все лоскуты на одном графике")
print("  best_vs_best.png  — лучший Фурье vs лучшие лоскуты")