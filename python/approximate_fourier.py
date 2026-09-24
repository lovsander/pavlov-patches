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

# ============ РЕСЕМПЛИНГ (для Фурье нужна равномерная сетка) ============
def resample_to_grid(sec_clean, n_target=360):
    if len(sec_clean) < 10:
        return None
    sec_clean = sec_clean.sort_values('angle_deg').reset_index(drop=True)
    angles = sec_clean['angle_deg'].values
    radii = sec_clean['radius_mm'].values
    # Замыкаем
    angles = np.append(angles, 360.0)
    radii = np.append(radii, radii[0])
    target_angles = np.linspace(0, 360, n_target, endpoint=False)
    target_radii = np.interp(target_angles, angles, radii)
    return pd.DataFrame({
        'angle_deg': target_angles,
        'radius_mm': target_radii,
    })

# ============ ФУРЬЕ ============
def fourier_fit(angles_deg, radii, n_harmonics=10):
    """
    Аппроксимация рядом Фурье.
    
    r(φ) = a0 + Σ (a_k cos(kφ) + b_k sin(kφ))
    
    Возвращает: coefs (массив [a0, a1, b1, a2, b2, ...])
    """
    phi = np.deg2rad(angles_deg)
    n = len(phi)
    
    # Матрица базисных функций
    A = np.ones((n, 1 + 2 * n_harmonics))
    for k in range(1, n_harmonics + 1):
        A[:, 2*k - 1] = np.cos(k * phi)
        A[:, 2*k] = np.sin(k * phi)
    
    # МНК
    coefs, _, _, _ = np.linalg.lstsq(A, radii, rcond=None)
    return coefs


def fourier_eval(angles_deg, coefs, n_harmonics=10):
    """Восстановление по коэффициентам Фурье."""
    phi = np.deg2rad(angles_deg)
    result = np.full_like(phi, coefs[0], dtype=float)
    for k in range(1, n_harmonics + 1):
        result += coefs[2*k - 1] * np.cos(k * phi)
        result += coefs[2*k] * np.sin(k * phi)
    return result

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
N_HARMONICS = 10

fig, axes = plt.subplots(2, 2, figsize=(14, 12))
axes = axes.flatten()

for sid in data['section_id'].unique():
    sec_clean = cleaned[(cleaned['section_id'] == sid) & (cleaned['is_outlier_detected'] == False)]
    if len(sec_clean) < 20:
        continue

    # Ресемплинг к 360 (для Фурье)
    sec_res = resample_to_grid(sec_clean, n_target=360)
    if sec_res is None:
        continue

    # Фурье
    coefs = fourier_fit(sec_res['angle_deg'].values, sec_res['radius_mm'].values, n_harmonics=N_HARMONICS)
    fitted = fourier_eval(sec_res['angle_deg'].values, coefs, n_harmonics=N_HARMONICS)

    # Метрики
    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']].copy()
    rmse, corr, max_err = compute_metrics(sec_res['angle_deg'].values, fitted, sec_ideal)

    results.append({'section_id': sid, 'rmse': rmse, 'corr': corr, 'max_err': max_err})

    # Визуализация
    if sid in SECTIONS_TO_SHOW:
        ax = axes[SECTIONS_TO_SHOW.index(sid)]

        ax.plot(sec_res['angle_deg'], sec_res['radius_mm'],
                'b.', markersize=2, label='Данные (ресемпл)', alpha=0.5)
        ax.plot(sec_res['angle_deg'], fitted,
                'orange', lw=2.5, label=f'Фурье (N={N_HARMONICS})')
        ax.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
                'green', lw=1.5, linestyle=':', label='Эталон')

        ax.set_title(f'Сечение {sid}: RMSE={rmse:.3f}, corr={corr:.4f}')
        ax.set_xlabel('Угол, °')
        ax.set_ylabel('Радиус, мм')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('approximation_fourier.png', dpi=120)
print("График: approximation_fourier.png")

# ============ ИТОГИ ============
print("\n=== РЕЗУЛЬТАТЫ (ФУРЬЕ) ===")
print(f"{'Сечение':<10} {'RMSE, мм':<12} {'Корреляция':<12} {'Макс. ошибка':<12}")
for r in results:
    print(f"{r['section_id']:<10} {r['rmse']:<12.4f} {r['corr']:<12.6f} {r['max_err']:<12.4f}")

avg_rmse = np.mean([r['rmse'] for r in results])
avg_corr = np.mean([r['corr'] for r in results])
print(f"\nСредний RMSE: {avg_rmse:.4f} мм")
print(f"Средняя корреляция: {avg_corr:.6f}")