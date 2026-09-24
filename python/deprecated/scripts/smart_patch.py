import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')

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

# ============ ПАТЧИ v3 ============
def build_patches_v3(sec_clean, degree, overlap, n_patches):
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values
    sector = 360.0 / n_patches
    centers = [i * sector + sector / 2 for i in range(n_patches)]
    angles_ext = np.concatenate([angles - 360, angles, angles + 360])
    radii_ext = np.concatenate([radii, radii, radii])
    patches = []
    for c in centers:
        half = sector / 2 + overlap
        mask = (angles_ext >= c - half) & (angles_ext <= c + half)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], degree)
        patches.append({'center': c, 'half': half, 'coefs': coefs})
    return patches

def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return 3 * t**2 - 2 * t**3

def eval_patches_v3(angles, patches):
    fitted = np.zeros_like(angles, dtype=float)
    for i, a in enumerate(angles):
        vals, ws = [], []
        for p in patches:
            d = abs((a - p['center'] + 180) % 360 - 180)
            if d >= p['half']:
                w = 0.0
            else:
                t = 1.0 - d / p['half']
                w = smoothstep(t)
            local = (a - p['center'] + 180) % 360 - 180
            r = np.polyval(p['coefs'], local)
            vals.append(r)
            ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        if ws.sum() > 0:
            fitted[i] = np.sum(ws * vals) / np.sum(ws)
        else:
            dists = [abs((a - p['center'] + 180) % 360 - 180) for p in patches]
            j = int(np.argmin(dists))
            local = (a - patches[j]['center'] + 180) % 360 - 180
            fitted[i] = np.polyval(patches[j]['coefs'], local)
    return fitted

# ============ МЕТРИКИ ============
def compute_metrics(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values, sec_ideal['radius_ideal_mm'].values)
    rmse = np.sqrt(np.mean((fitted - ideal) ** 2))
    corr = np.corrcoef(fitted, ideal)[0, 1]
    return rmse, corr

# ============ СРАВНЕНИЕ НА СЕЧЕНИИ 0 ============
SID = 0
sec_clean = cleaned[(cleaned['section_id'] == SID) & (cleaned['is_outlier_detected'] == False)]
sec_ideal = data[data['section_id'] == SID][['angle_deg', 'radius_ideal_mm']].copy()
angles_raw = sec_clean['angle_deg'].values
radii_raw = sec_clean['radius_mm'].values
angles_grid = np.linspace(0, 360, 1440, endpoint=False)

# Фурье
best_f = {'N': None, 'rmse': 1e9, 'fitted': None}
for N in [12]:
    coefs = fourier_fit_raw(angles_raw, radii_raw, N)
    fitted = fourier_eval(angles_grid, coefs, N)
    rmse, corr = compute_metrics(angles_grid, fitted, sec_ideal)
    if rmse < best_f['rmse']:
        best_f = {'N': N, 'rmse': rmse, 'corr': corr, 'fitted': fitted}

# Патчи
N_PATCHES = 8
DEGREE = 7
OVERLAP = 25
patches = build_patches_v3(sec_clean, DEGREE, OVERLAP, N_PATCHES)
fitted_p = eval_patches_v3(angles_grid, patches)
rmse_p, corr_p = compute_metrics(angles_grid, fitted_p, sec_ideal)

print(f"Фурье N={best_f['N']}: RMSE={best_f['rmse']:.5f}, corr={best_f['corr']:.5f}")
print(f"Патчи N={N_PATCHES}, deg={DEGREE}: RMSE={rmse_p:.5f}, corr={corr_p:.5f}")

# ============ ВИЗУАЛИЗАЦИЯ: ОДИН РИСУНОК, 2 ПАНЕЛИ ============
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))

# ЛЕВАЯ ПАНЕЛЬ: ДЕКАРТОВЫ КООРДИНАТЫ
ax1.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
         'b.', markersize=2, alpha=0.25, label='Данные')
ax1.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2.5, alpha=0.7, label='Эталон')
ax1.plot(angles_grid, best_f['fitted'], 'red', lw=2,
         label=f'Фурье N={best_f["N"]} (RMSE={best_f["rmse"]:.5f})')
ax1.plot(angles_grid, fitted_p, 'orange', lw=2, linestyle='--',
         label=f'Патчи Павлова N={N_PATCHES}, deg={DEGREE} (RMSE={rmse_p:.5f})')

ax1.set_title('Декартовы координаты', fontsize=13)
ax1.set_xlabel('Угол, °')
ax1.set_ylabel('Радиус, мм')
ax1.legend(fontsize=10)
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 360)

# ПРАВАЯ ПАНЕЛЬ: ПОЛЯРНЫЕ КООРДИНАТЫ
ax2 = plt.subplot(1, 2, 2, projection='polar')

phi_data = np.deg2rad(sec_clean['angle_deg'].values)
ax2.scatter(phi_data, sec_clean['radius_mm'], s=2, c='blue', alpha=0.2, label='Данные')
phi_ideal = np.deg2rad(sec_ideal['angle_deg'].values)
ax2.plot(phi_ideal, sec_ideal['radius_ideal_mm'], 'k-', lw=2.5, alpha=0.7, label='Эталон')

phi_grid = np.deg2rad(angles_grid)
ax2.plot(phi_grid, best_f['fitted'], 'red', lw=2,
         label=f'Фурье N={best_f["N"]}')
ax2.plot(phi_grid, fitted_p, 'orange', lw=2, linestyle='--',
         label=f'Патчи N={N_PATCHES}')

ax2.set_title('Полярные координаты', fontsize=13, pad=20)
ax2.legend(loc='upper right', bbox_to_anchor=(1.15, 1.15), fontsize=9)
ax2.grid(True, alpha=0.3)

r_min = sec_clean['radius_mm'].min() - 0.5
r_max = sec_clean['radius_mm'].max() + 0.5
ax2.set_ylim(r_min, r_max)

plt.tight_layout()
plt.savefig('comparison_fourier_patches_final.png', dpi=120)
print("График: comparison_fourier_patches_final.png")