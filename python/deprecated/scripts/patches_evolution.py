"""
patches_evolution.py

Сравнение эволюции методов лоскутной (патч) аппроксимации замкнутых форм.
На одном графике — 6 методов от простого к финальному.

Все методы строятся ПО ОДНИМ И ТЕМ ЖЕ данным.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')

# ============ ОЧИСТКА ============
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


# ============ ПАРАМЕТРЫ ============
SID = 0
N_PATCHES = 8
NOISE_STD = 0.1

# ============ ПОДГОТОВКА ============
sec_full = cleaned[cleaned['section_id'] == SID].copy()
angles_full = sec_full['angle_deg'].values
radii_full = sec_full['radius_mm'].values
is_outlier = sec_full['is_outlier_detected'].values

sec_clean = sec_full[~sec_full['is_outlier_detected']]
angles_raw = sec_clean['angle_deg'].values
radii_raw = sec_clean['radius_mm'].values

sec_ideal = data[data['section_id'] == SID][['angle_deg', 'radius_ideal_mm']].copy()
angles_grid = np.linspace(0, 360, 1440, endpoint=False)


# ============ ОБЩИЕ ФУНКЦИИ ============
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return 3 * t**2 - 2 * t**3


def compute_rmse(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values,
                       sec_ideal['radius_ideal_mm'].values)
    return np.sqrt(np.mean((fitted - ideal) ** 2))


def compute_mae(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values,
                       sec_ideal['radius_ideal_mm'].values)
    return np.mean(np.abs(fitted - ideal))



# ============ МЕТОД 3: 8 ЛОСКУТОВ, ФИКС. СТЕПЕНЬ ============
def method_8patches_fixed(angles_raw, radii_raw, degree=12, overlap=25):
    sector = 360.0 / N_PATCHES
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(N_PATCHES)]
    half_train = half_sector + overlap

    angles_ext = np.concatenate([angles_raw - 360, angles_raw, angles_raw + 360])
    radii_ext = np.concatenate([radii_raw, radii_raw, radii_raw])

    patches = []
    for c in centers:
        mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], degree)
        patches.append({'center': c, 'half_sector': half_sector,
                        'half_train': half_train, 'coefs': coefs})

    fitted = np.zeros_like(angles_grid)
    for i, a in enumerate(angles_grid):
        vals, ws = [], []
        for p in patches:
            d = abs((a - p['center'] + 180) % 360 - 180)
            if d >= p['half_train']:
                w = 0.0
            else:
                t = 1.0 - d / p['half_train']
                w = smoothstep(t)
            local = (a - p['center'] + 180) % 360 - 180
            r = np.polyval(p['coefs'], local)
            vals.append(r); ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        fitted[i] = np.sum(ws * vals) / np.sum(ws) if ws.sum() > 0 else np.nan
    return fitted


# ============ МЕТОД 4: 8 ЛОСКУТОВ, ADAPTIVE ПО RMSE ============
def method_8patches_adaptive_rmse(angles_full, radii_full, is_outlier,
                                    sec_ideal, deg_min=3, deg_max=15,
                                    overlap=25):
    sector = 360.0 / N_PATCHES
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(N_PATCHES)]
    half_train = half_sector + overlap

    angles_ext = np.concatenate([angles_raw - 360, angles_raw, angles_raw + 360])
    radii_ext = np.concatenate([radii_raw, radii_raw, radii_raw])

    ideal_grid = np.interp(angles_grid, sec_ideal['angle_deg'].values,
                            sec_ideal['radius_ideal_mm'].values)

    patches = []
    for c in centers:
        # Сектор без overlap для оценки RMSE
        mask_sec = np.abs((angles_full - c + 180) % 360 - 180) <= half_sector
        mask_clean = mask_sec & ~is_outlier
        a_sec = (angles_full[mask_clean] - c + 180) % 360 - 180
        r_sec = radii_full[mask_clean]

        best_deg = deg_min
        best_rmse = 1e9
        for deg in range(deg_min, deg_max + 1):
            if deg + 1 >= len(a_sec):
                break
            coefs = np.polyfit(a_sec, r_sec, deg)
            r_fit = np.polyval(coefs, a_sec)
            rmse = np.sqrt(np.mean((r_fit - r_sec) ** 2))
            if rmse < best_rmse:
                best_rmse = rmse
                best_deg = deg

        mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], best_deg)
        patches.append({'center': c, 'half_sector': half_sector,
                        'half_train': half_train, 'coefs': coefs,
                        'degree': best_deg})

    fitted = np.zeros_like(angles_grid)
    for i, a in enumerate(angles_grid):
        vals, ws = [], []
        for p in patches:
            d = abs((a - p['center'] + 180) % 360 - 180)
            if d >= p['half_train']:
                w = 0.0
            else:
                t = 1.0 - d / p['half_train']
                w = smoothstep(t)
            local = (a - p['center'] + 180) % 360 - 180
            r = np.polyval(p['coefs'], local)
            vals.append(r); ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        fitted[i] = np.sum(ws * vals) / np.sum(ws) if ws.sum() > 0 else np.nan
    return fitted


# ============ МЕТОД 5: ADAPTIVE ПО СЛОЖНОСТИ (старый, без чётных) ============
def method_8patches_adaptive_complexity(angles_full, radii_full, is_outlier,
                                          overlap=25):
    sector = 360.0 / N_PATCHES
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(N_PATCHES)]
    half_train = half_sector + overlap

    angles_ext = np.concatenate([angles_raw - 360, angles_raw, angles_raw + 360])
    radii_ext = np.concatenate([radii_raw, radii_raw, radii_raw])

    patches = []
    for c in centers:
        mask_sec = np.abs((angles_full - c + 180) % 360 - 180) <= half_sector
        mask_clean = mask_sec & ~is_outlier
        r_sec = radii_full[mask_clean]

        if len(r_sec) < 5:
            deg = 3
        else:
            amp = float(np.max(r_sec) - np.min(r_sec))
            if amp < 0.3:
                deg = 3
            elif amp < 0.5:
                deg = 5
            elif amp < 0.7:
                deg = 7
            elif amp < 0.9:
                deg = 9
            else:
                deg = 12

        mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], deg)
        patches.append({'center': c, 'half_sector': half_sector,
                        'half_train': half_train, 'coefs': coefs,
                        'degree': deg})

    fitted = np.zeros_like(angles_grid)
    for i, a in enumerate(angles_grid):
        vals, ws = [], []
        for p in patches:
            d = abs((a - p['center'] + 180) % 360 - 180)
            if d >= p['half_train']:
                w = 0.0
            else:
                t = 1.0 - d / p['half_train']
                w = smoothstep(t)
            local = (a - p['center'] + 180) % 360 - 180
            r = np.polyval(p['coefs'], local)
            vals.append(r); ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        fitted[i] = np.sum(ws * vals) / np.sum(ws) if ws.sum() > 0 else np.nan
    return fitted


# ============ МЕТОД 6: ФИНАЛЬНЫЙ v3 ============
def method_8patches_v3(angles_full, radii_full, is_outlier,
                        overlap_train=15, overlap_use=5,
                        deg_min=4, deg_max=14, scale=180.0):
    """
    Adaptive по амплитуде, чётные степени,
    обучение ±15°, blend ±5°.
    """
    sector = 360.0 / N_PATCHES
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(N_PATCHES)]

    angles_ext = np.concatenate([angles_raw - 360, angles_raw, angles_raw + 360])
    radii_ext = np.concatenate([radii_raw, radii_raw, radii_raw])

    patches = []
    for c in centers:
        mask_sec = np.abs((angles_full - c + 180) % 360 - 180) <= half_sector
        mask_clean = mask_sec & ~is_outlier
        r_sec = radii_full[mask_clean]

        if len(r_sec) < 5:
            deg = deg_min
        else:
            amp = float(np.percentile(r_sec, 95) - np.percentile(r_sec, 5))
            mean_r = float(np.mean(r_sec))
            amp_norm = amp / mean_r if mean_r > 0 else 0
            deg = int(round(amp_norm * scale))
            deg = max(deg_min, min(deg_max, deg))
            if deg % 2 != 0:
                deg += 1
            deg = max(deg_min, min(deg_max, deg))

        half_train = half_sector + overlap_train
        half_use = half_sector + overlap_use

        mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], deg)

        patches.append({
            'center': c, 'half_sector': half_sector,
            'half_train': half_train, 'half_use': half_use,
            'coefs': coefs, 'degree': deg,
        })

    fitted = np.zeros_like(angles_grid)
    for i, a in enumerate(angles_grid):
        vals, ws = [], []
        for p in patches:
            d = abs((a - p['center'] + 180) % 360 - 180)
            if d <= p['half_sector']:
                w = 1.0
            elif d <= p['half_use']:
                t = 1.0 - (d - p['half_sector']) / (p['half_use'] - p['half_sector'])
                w = smoothstep(t)
            else:
                w = 0.0
            local = (a - p['center'] + 180) % 360 - 180
            r = np.polyval(p['coefs'], local)
            vals.append(r); ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        fitted[i] = np.sum(ws * vals) / np.sum(ws) if ws.sum() > 0 else np.nan
    return fitted, patches


# ============ ЗАПУСК ВСЕХ МЕТОДОВ ============
print("=== СРАВНЕНИЕ МЕТОДОВ ПАТЧЕЙ ===\n")

results = {}


# 3
fitted = method_8patches_fixed(angles_raw, radii_raw, degree=12, overlap=25)
results['3. 8 лоскутов deg=6'] = fitted
print(f"3. 8 лоскутов deg=6:             RMSE={compute_rmse(angles_grid, fitted, sec_ideal):.5f}")

# 4
fitted = method_8patches_adaptive_rmse(angles_full, radii_full, is_outlier,
                                         sec_ideal, deg_min=3, deg_max=15)
results['4. 8 adaptive (RMSE)'] = fitted
print(f"4. 8 adaptive (RMSE):            RMSE={compute_rmse(angles_grid, fitted, sec_ideal):.5f}")

# 5
fitted = method_8patches_adaptive_complexity(angles_full, radii_full, is_outlier)
results['5. 8 adaptive (сложность)'] = fitted
print(f"5. 8 adaptive (сложность):       RMSE={compute_rmse(angles_grid, fitted, sec_ideal):.5f}")

# 6
fitted, patches_v3 = method_8patches_v3(angles_full, radii_full, is_outlier)
results['6. FINAL v3 (amplitude, четные)'] = fitted
print(f"6. FINAL v3:                     RMSE={compute_rmse(angles_grid, fitted, sec_ideal):.5f}")

print(f"\nСтепени FINAL v3: {[p['degree'] for p in patches_v3]}")


# ============ ГРАФИК ============
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 12),
                                gridspec_kw={'height_ratios': [3, 1]})

# Данные
ax1.plot(sec_full['angle_deg'], sec_full['radius_mm'],
         'b.', markersize=2, alpha=0.2, label='Данные')
ax1.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2, alpha=0.5, label='Эталон')

# Методы
colors = ['gray', 'purple', 'cyan', 'green', 'orange', 'red']
linestyles = [':', '--', '-.', '--', '-.', '-']

for (name, fitted), color, ls in zip(results.items(), colors, linestyles):
    rmse = compute_rmse(angles_grid, fitted, sec_ideal)
    lw =  1.8
    ax1.plot(angles_grid, fitted, color=color, lw=lw, linestyle=ls,
             label=f'{name} — RMSE={rmse:.5f}',
             zorder=10 if 'FINAL' in name else 5)

ax1.set_title(f'Эволюция методов лоскутной аппроксимации (сечение {SID})', fontsize=14)
ax1.set_xlabel('Угол, °')
ax1.set_ylabel('Радиус, мм')
ax1.legend(fontsize=9, loc='upper right')
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 360)

# Остатки
ideal_grid = np.interp(angles_grid, sec_ideal['angle_deg'].values,
                       sec_ideal['radius_ideal_mm'].values)

for (name, fitted), color, ls in zip(results.items(), colors, linestyles):
    residual = fitted - ideal_grid
    lw = 2.5 if 'FINAL' in name else 1.0
    ax2.plot(angles_grid, residual, color=color, lw=lw, linestyle=ls,
             label=name, alpha=0.9 if 'FINAL' in name else 0.6)

ax2.axhline(0, color='k', lw=0.5)
ax2.axhline(NOISE_STD, color='r', lw=0.8, linestyle='--', alpha=0.3)
ax2.axhline(-NOISE_STD, color='r', lw=0.8, linestyle='--', alpha=0.3)

ax2.set_title('Остатки (аппроксимация − эталон)', fontsize=12)
ax2.set_xlabel('Угол, °')
ax2.set_ylabel('Остаток, мм')
ax2.legend(fontsize=8, ncol=2)
ax2.grid(True, alpha=0.3)
ax2.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('patches_evolution.png', dpi=120)
print("\nСохранено: patches_evolution.png")