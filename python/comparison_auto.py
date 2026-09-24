import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

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
    max_err = np.max(np.abs(fitted - ideal))
    return rmse, corr, max_err

# ============ АВТОПОДБОР (по каждому методу отдельно) ============
def auto_select_both(sec_clean, sec_ideal):
    """
    Возвращает best_fourier, best_patches, best_overall.
    """
    angles_grid = np.linspace(0, 360, 720, endpoint=False)
    angles_raw = sec_clean['angle_deg'].values
    radii_raw = sec_clean['radius_mm'].values

    # --- Фурье ---
    best_f = {'params': None, 'rmse': 1e9, 'corr': 0.0, 'max_err': 1e9}
    for N in [3, 4, 5, 6, 7, 8, 10, 12]:
        coefs = fourier_fit_raw(angles_raw, radii_raw, N)
        fitted = fourier_eval(angles_grid, coefs, N)
        rmse, corr, max_err = compute_metrics(angles_grid, fitted, sec_ideal)
        if rmse < best_f['rmse'] - 1e-6:
            best_f = {'params': {'N': N}, 'rmse': rmse, 'corr': corr, 'max_err': max_err}

    # --- Лоскуты ---
    best_p = {'params': None, 'rmse': 1e9, 'corr': 0.0, 'max_err': 1e9}
    for n_p in [2, 3, 4, 6, 8]:
        for degree in [7, 8,10,12]:
            for overlap in [25, 35, 45]:
                try:
                    coefs_list = approximate_npatches(sec_clean, degree, overlap, n_p)
                    fitted = blend_npatches(angles_grid, coefs_list, overlap, n_p)
                    rmse, corr, max_err = compute_metrics(angles_grid, fitted, sec_ideal)
                    if rmse < best_p['rmse'] - 1e-6:
                        best_p = {'params': {'n': n_p, 'degree': degree, 'overlap': overlap},
                                  'rmse': rmse, 'corr': corr, 'max_err': max_err}
                except Exception:
                    continue

    best_overall = best_f if best_f['rmse'] <= best_p['rmse'] else best_p
    best_overall['method'] = 'fourier' if best_overall is best_f else 'patches'
    return best_f, best_p, best_overall


# ============ ЭТАП 1: АВТОПОДБОР ============
print("\n=== АВТОПОДБОР (СЕЧЕНИЕ 0) ===\n")
sec0 = cleaned[(cleaned['section_id'] == 0) & (cleaned['is_outlier_detected'] == False)]
sec0_ideal = data[data['section_id'] == 0][['angle_deg', 'radius_ideal_mm']].copy()

best_f, best_p, best_overall = auto_select_both(sec0, sec0_ideal)

print(f"ЛУЧШИЙ ФУРЬЕ: N={best_f['params']['N']}, "
      f"RMSE={best_f['rmse']:.5f}, corr={best_f['corr']:.5f}")
print(f"ЛУЧШИЕ ЛОСКУТЫ: n={best_p['params']['n']}, deg={best_p['params']['degree']}, "
      f"ov={best_p['params']['overlap']}, RMSE={best_p['rmse']:.5f}, corr={best_p['corr']:.5f}")
print(f"ПОБЕДИТЕЛЬ: {best_overall['method'].upper()}, RMSE={best_overall['rmse']:.5f}")


# ============ ЭТАП 2: ПРИМЕНЕНИЕ КО ВСЕМ СЕЧЕНИЯМ ============
print("\n=== ПРИМЕНЕНИЕ КО ВСЕМ СЕЧЕНИЯМ ===\n")
results = []
angles_grid = np.linspace(0, 360, 720, endpoint=False)

for sid in data['section_id'].unique():
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()

    # Фурье с лучшими параметрами
    coefs_f = fourier_fit_raw(sec_clean['angle_deg'].values,
                              sec_clean['radius_mm'].values,
                              best_f['params']['N'])
    fitted_f = fourier_eval(angles_grid, coefs_f, best_f['params']['N'])
    rmse_f, corr_f, max_f = compute_metrics(angles_grid, fitted_f, sec_ideal)

    # Лоскуты с лучшими параметрами
    p = best_p['params']
    coefs_list = approximate_npatches(sec_clean, p['degree'], p['overlap'], p['n'])
    fitted_p = blend_npatches(angles_grid, coefs_list, p['overlap'], p['n'])
    rmse_p, corr_p, max_p = compute_metrics(angles_grid, fitted_p, sec_ideal)

    results.append({
        'section_id': sid,
        'rmse_f': rmse_f, 'corr_f': corr_f, 'max_f': max_f,
        'rmse_p': rmse_p, 'corr_p': corr_p, 'max_p': max_p,
    })

print(f"{'Сек':<5} {'Фурье RMSE':<12} {'Фурье corr':<12} {'Лоск RMSE':<12} {'Лоск corr':<12}")
for r in results:
    print(f"{r['section_id']:<5} {r['rmse_f']:<12.5f} {r['corr_f']:<12.6f} "
          f"{r['rmse_p']:<12.5f} {r['corr_p']:<12.6f}")

avg_rmse_f = np.mean([r['rmse_f'] for r in results])
avg_rmse_p = np.mean([r['rmse_p'] for r in results])
print(f"\nСредний RMSE Фурье:   {avg_rmse_f:.5f}")
print(f"Средний RMSE Лоскуты: {avg_rmse_p:.5f}")


# ============ СОХРАНЕНИЕ ============
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
report_file = f'report_{timestamp}.txt'

with open(report_file, 'w', encoding='utf-8') as f:
    f.write(f"=== ОТЧЁТ ===\n")
    f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write(f"Лучший Фурье:   N={best_f['params']['N']}, "
            f"RMSE={best_f['rmse']:.6f}, corr={best_f['corr']:.6f}\n")
    f.write(f"Лучшие лоскуты: n={best_p['params']['n']}, deg={best_p['params']['degree']}, "
            f"ov={best_p['params']['overlap']}, RMSE={best_p['rmse']:.6f}, corr={best_p['corr']:.6f}\n")
    f.write(f"Победитель: {best_overall['method']}\n\n")

    f.write(f"{'Сек':<5} {'Фурье RMSE':<12} {'Фурье corr':<12} {'Лоск RMSE':<12} {'Лоск corr':<12}\n")
    f.write("-" * 60 + "\n")
    for r in results:
        f.write(f"{r['section_id']:<5} {r['rmse_f']:<12.5f} {r['corr_f']:<12.6f} "
                f"{r['rmse_p']:<12.5f} {r['corr_p']:<12.6f}\n")

    f.write(f"\nСредний RMSE Фурье:   {avg_rmse_f:.6f}\n")
    f.write(f"Средний RMSE Лоскуты: {avg_rmse_p:.6f}\n")

print(f"\nОтчёт: {report_file}")


# ============ ВИЗУАЛИЗАЦИЯ (оба метода) ============
fig, axes = plt.subplots(2, 2, figsize=(14, 12))
axes = axes.flatten()
SECTIONS_TO_SHOW = [0, 3, 6, 9]

for sid in SECTIONS_TO_SHOW:
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()

    # Фурье
    coefs_f = fourier_fit_raw(sec_clean['angle_deg'].values,
                              sec_clean['radius_mm'].values,
                              best_f['params']['N'])
    fitted_f = fourier_eval(angles_grid, coefs_f, best_f['params']['N'])
    rmse_f, _, _ = compute_metrics(angles_grid, fitted_f, sec_ideal)

    # Лоскуты
    p = best_p['params']
    coefs_list = approximate_npatches(sec_clean, p['degree'], p['overlap'], p['n'])
    fitted_p = blend_npatches(angles_grid, coefs_list, p['overlap'], p['n'])
    rmse_p, _, _ = compute_metrics(angles_grid, fitted_p, sec_ideal)

    ax = axes[SECTIONS_TO_SHOW.index(sid)]
    ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
            'b.', markersize=2, alpha=0.3, label='Данные')
    ax.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
            'green', lw=2, linestyle=':', label='Эталон', alpha=0.7)
    ax.plot(angles_grid, fitted_f, 'red', lw=2,
            label=f'Фурье N={best_f["params"]["N"]} (RMSE={rmse_f:.5f})')
    ax.plot(angles_grid, fitted_p, 'orange', lw=2,
            label=f'Лоскуты N={p["n"]}, deg={p["degree"]} (RMSE={rmse_p:.5f})')

    ax.set_title(f'Сечение {sid}: Фурье={rmse_f:.5f}, Лоскуты={rmse_p:.5f}')
    ax.set_xlabel('Угол, °')
    ax.set_ylabel('Радиус, мм')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('comparison_both.png', dpi=120)
print("График: comparison_both.png")