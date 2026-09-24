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
    """
    Усиленная очистка:
    1. По производной (резкие скачки).
    2. По MAD (отклонения от медианы).
    3. По modified z-score.
    """
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
N_PATCHES = 8
DEGREE_MIN = 4
DEGREE_MAX = 14
SCALE = 180.0
NOISE_STD = 0.1
SID = 0
OVERLAP_TRAIN = 15    # для обучения
OVERLAP_USE = 5       # для blend


# ============ МЕТРИКИ СЛОЖНОСТИ ПО ПАТЧАМ ============
def compute_patch_complexity(angles_full, radii_full, is_outlier,
                              centers, half_sector):
    """
    Устойчивая амплитуда радиуса в секторе (5-й и 95-й процентили).
    """
    patch_metrics = []
    for c in centers:
        mask_sec = np.abs((angles_full - c + 180) % 360 - 180) <= half_sector
        mask_clean = mask_sec & ~is_outlier

        r_sec = radii_full[mask_clean]

        if len(r_sec) < 5:
            patch_metrics.append({'amplitude': 0.0, 'mean_radius': 15.0})
            continue

        amp = float(np.percentile(r_sec, 95) - np.percentile(r_sec, 5))
        mean_r = float(np.mean(r_sec))

        patch_metrics.append({
            'amplitude': amp,
            'mean_radius': mean_r,
        })
    return patch_metrics


def degree_from_amplitude(m, deg_min=DEGREE_MIN, deg_max=DEGREE_MAX, scale=SCALE):
    """
    deg = round(amp_norm × scale), но только ЧЁТНАЯ.
    """
    amp = m['amplitude']
    mean_r = m['mean_radius']

    if mean_r > 0:
        amp_norm = amp / mean_r
    else:
        amp_norm = 0.0

    deg = int(round(amp_norm * scale))
    deg = max(deg_min, min(deg_max, deg))

    # Округляем до чётного
    if deg % 2 != 0:
        deg += 1  # вверх

    deg = max(deg_min, min(deg_max, deg))
    return deg, amp_norm


# ============ ФУНКЦИИ ПАТЧЕЙ ============
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return 3 * t**2 - 2 * t**3


def build_patches(angles_raw, radii_raw, degrees, n_patches,
                  overlap_train=OVERLAP_TRAIN,
                  overlap_use=OVERLAP_USE):
    """
    Патчи с разными overlap для обучения и для blend.
    """
    sector = 360.0 / n_patches
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(n_patches)]

    angles_ext = np.concatenate([angles_raw - 360, angles_raw, angles_raw + 360])
    radii_ext = np.concatenate([radii_raw, radii_raw, radii_raw])

    patches = []
    for j, c in enumerate(centers):
        deg = degrees[j]
        half_train = half_sector + overlap_train
        half_use = half_sector + overlap_use

        mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], deg)

        patches.append({
            'center': c,
            'half_sector': half_sector,
            'half_train': half_train,
            'half_use': half_use,
            'coefs': coefs,
            'degree': deg,
            'n_points': int(mask.sum()),
        })
    return patches


def eval_patches(angles, patches):
    fitted = np.zeros_like(angles, dtype=float)
    for i, a in enumerate(angles):
        vals, ws = [], []
        for p in patches:
            d = abs((a - p['center'] + 180) % 360 - 180)
            
            # Вес: 1 внутри сектора, плавно убывает в зоне blend
            if d <= p['half_sector']:
                w = 1.0
            elif d <= p['half_use']:
                t = 1.0 - (d - p['half_sector']) / (p['half_use'] - p['half_sector'])
                w = smoothstep(t)
            else:
                w = 0.0
            
            local = (a - p['center'] + 180) % 360 - 180
            r = np.polyval(p['coefs'], local)
            vals.append(r)
            ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        if ws.sum() > 0:
            fitted[i] = np.sum(ws * vals) / np.sum(ws)
    return fitted


def compute_rmse(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values,
                       sec_ideal['radius_ideal_mm'].values)
    return np.sqrt(np.mean((fitted - ideal) ** 2))


def plot_polynomial(ax, center, half_train, coefs, color, label=None, lw=2.5):
    a_local = np.linspace(-half_train, half_train, 300)
    a_global_raw = center + a_local
    r_vals = np.polyval(coefs, a_local)

    mask_neg = a_global_raw < 0
    mask_over = a_global_raw > 360
    mask_ok = ~mask_neg & ~mask_over

    if mask_ok.any():
        ax.plot(a_global_raw[mask_ok], r_vals[mask_ok],
                color=color, lw=lw, label=label)
    if mask_neg.any():
        ax.plot(a_global_raw[mask_neg] + 360, r_vals[mask_neg],
                color=color, lw=lw)
    if mask_over.any():
        ax.plot(a_global_raw[mask_over] - 360, r_vals[mask_over],
                color=color, lw=lw)


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

print(f"Проверка размеров:")
print(f"  angles_full: {len(angles_full)}")
print(f"  is_outlier:  {len(is_outlier)}")
print(f"  angles_raw:  {len(angles_raw)}")
print(f"  Чистых:      {(~is_outlier).sum()}")
print(f"  Радиус: min={radii_raw.min():.3f}, max={radii_raw.max():.3f}, mean={radii_raw.mean():.3f}")

# ============ ЭТАП 1: СТЕПЕНИ ПО АМПЛИТУДЕ ============
print("\n=== СТЕПЕНИ ПО АМПЛИТУДЕ ===")

sector = 360.0 / N_PATCHES
half_sector = sector / 2
centers = [i * sector + half_sector for i in range(N_PATCHES)]

patch_metrics = compute_patch_complexity(angles_full, radii_full, is_outlier,
                                          centers, half_sector)

adaptive_degrees = []
for j, m in enumerate(patch_metrics):
    deg, amp_norm = degree_from_amplitude(m)
    adaptive_degrees.append(deg)
    print(f"  Патч {j+1}: amp={m['amplitude']:.3f}, "
          f"mean_r={m['mean_radius']:.2f}, "
          f"amp_norm={amp_norm:.5f}, "
          f"deg={deg}")

# ============ ЭТАП 2: ОБУЧЕНИЕ ПАТЧЕЙ ============
patches_adaptive = build_patches(angles_raw, radii_raw, adaptive_degrees,
                                  N_PATCHES,
                                  overlap_train=OVERLAP_TRAIN,
                                  overlap_use=OVERLAP_USE)

fitted_adaptive = eval_patches(angles_grid, patches_adaptive)
rmse_adaptive = compute_rmse(angles_grid, fitted_adaptive, sec_ideal)

print(f"\nRMSE (адаптивные степени): {rmse_adaptive:.5f}")
print(f"Суммарно коэффициентов: {sum(d+1 for d in adaptive_degrees)}")
print(f"\nOverlap:")
for j, p in enumerate(patches_adaptive):
    print(f"  Патч {j+1}: deg={p['degree']}, "
          f"half_train={p['half_train']:.1f}°, "
          f"half_use={p['half_use']:.1f}°")

# ============ РИСУНОК 1: СЕКТОРА + ШТРИХОВКА ============
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(sec_full['angle_deg'], sec_full['radius_mm'],
        'b.', markersize=3, alpha=0.3, label='Данные')

colors = plt.cm.tab10(np.linspace(0, 1, N_PATCHES))

for j, c in enumerate(centers):
    a_start = c - half_sector
    a_end = c + half_sector
    a_train_start = c - patches_adaptive[j]['half_train']
    a_train_end = c + patches_adaptive[j]['half_train']
    a_use_start = c - patches_adaptive[j]['half_use']
    a_use_end = c + patches_adaptive[j]['half_use']

    ax.axvspan(a_start, a_end, color=colors[j], alpha=0.12)
    ax.axvspan(a_train_start, a_use_start, facecolor=colors[j],
               alpha=0.25, hatch='///', edgecolor=colors[j], linewidth=0)
    ax.axvspan(a_use_end, a_train_end, facecolor=colors[j],
               alpha=0.25, hatch='///', edgecolor=colors[j], linewidth=0)

    ax.axvline(c, color=colors[j], lw=1.5, alpha=0.8)
    ax.text(c, ax.get_ylim()[1] * 0.98,
            f'П{j+1}\ndeg={adaptive_degrees[j]}',
            ha='center', va='top', fontsize=8,
            color=colors[j], fontweight='bold')

ax.set_title(f'Сектора: обучение ±{OVERLAP_TRAIN}°, blend ±{OVERLAP_USE}°')
ax.set_xlabel('Угол, °')
ax.set_ylabel('Радиус, мм')
ax.set_xlim(0, 360)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('final_step1_sectors.png', dpi=120)
print("\nСохранено: final_step1_sectors.png")

# ============ РИСУНОК 2: ОБУЧЕНИЕ ПАТЧЕЙ ============
fig, axes = plt.subplots(4, 2, figsize=(16, 14))
axes = axes.flatten()

for j, p in enumerate(patches_adaptive):
    ax = axes[j]
    c = p['center']

    mask = (np.abs((angles_raw - c + 180) % 360 - 180) <= p['half_train'])
    a_train = angles_raw[mask]
    r_train = radii_raw[mask]

    ax.plot(sec_full['angle_deg'], sec_full['radius_mm'],
            'b.', markersize=2, alpha=0.15)
    ax.scatter(a_train, r_train, s=8, c=[colors[j]], alpha=0.6,
               label=f'Точки ({mask.sum()})')

    plot_polynomial(ax, c, p['half_train'], p['coefs'], colors[j],
                    label=f'deg={p["degree"]}', lw=2.5)

    # Зона сектора
    ax.axvspan(c - half_sector, c + half_sector, color=colors[j], alpha=0.1)
    # Границы обучения
    ax.axvline(c - p['half_train'], color='gray', lw=0.8, linestyle=':')
    ax.axvline(c + p['half_train'], color='gray', lw=0.8, linestyle=':')
    # Границы использования (blend)
    ax.axvline(c - p['half_use'], color='green', lw=1.2, linestyle='--', alpha=0.7)
    ax.axvline(c + p['half_use'], color='green', lw=1.2, linestyle='--', alpha=0.7)

    ax.set_title(f'Патч {j+1}: центр {c:.1f}°, deg={p["degree"]}, точек={p["n_points"]}',
                 fontsize=10)
    ax.set_xlim(0, 360)
    ax.set_ylim(sec_full['radius_mm'].min() - 0.3,
                sec_full['radius_mm'].max() + 0.3)
    ax.legend(fontsize=7, loc='lower right')
    ax.grid(True, alpha=0.3)

plt.suptitle(f'Обучение {N_PATCHES} патчей '
             f'(train ±{OVERLAP_TRAIN}°, use ±{OVERLAP_USE}°)',
             fontsize=13)
plt.tight_layout()
plt.savefig('final_step2_training.png', dpi=120)
print("Сохранено: final_step2_training.png")

# ============ РИСУНОК 3: ВЕСА + СТЕПЕНИ ============
fig, ax = plt.subplots(figsize=(14, 6))
for j, p in enumerate(patches_adaptive):
    d = np.abs((angles_grid - p['center'] + 180) % 360 - 180)
    t = np.clip(1.0 - d / p['half_use'], 0.0, 1.0)
    w = smoothstep(t)
    ax.plot(angles_grid, w, color=colors[j], lw=2,
            label=f'П{j+1} (deg={p["degree"]})')
ax.set_title(f'Веса патчей (blend ±{OVERLAP_USE}°)')
ax.set_xlabel('Угол, °')
ax.set_ylabel('Вес')
ax.set_xlim(0, 360)
ax.set_ylim(-0.05, 1.05)
ax.legend(fontsize=8, ncol=4)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('final_step3_weights.png', dpi=120)
print("Сохранено: final_step3_weights.png")

# ============ РИСУНОК 4: ИТОГ + ОСТАТКИ ============
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

ax1.plot(sec_full['angle_deg'], sec_full['radius_mm'],
         'b.', markersize=3, alpha=0.3, label='Данные')
ax1.plot(sec_ideal['angle_deg'], sec_ideal['radius_ideal_mm'],
         'k-', lw=2, alpha=0.6, label='Эталон')

for j, p in enumerate(patches_adaptive):
    a_local = np.linspace(-p['half_train'], p['half_train'], 300)
    a_global_raw = p['center'] + a_local
    r_poly = np.polyval(p['coefs'], a_local)
    mask_neg = a_global_raw < 0
    mask_over = a_global_raw > 360
    mask_ok = ~mask_neg & ~mask_over
    if mask_ok.any():
        ax1.plot(a_global_raw[mask_ok], r_poly[mask_ok], color=colors[j], lw=1, alpha=0.4)
    if mask_neg.any():
        ax1.plot(a_global_raw[mask_neg] + 360, r_poly[mask_neg], color=colors[j], lw=1, alpha=0.4)
    if mask_over.any():
        ax1.plot(a_global_raw[mask_over] - 360, r_poly[mask_over], color=colors[j], lw=1, alpha=0.4)

ax1.plot(angles_grid, fitted_adaptive, 'orange', lw=3,
         label=f'Итог (RMSE={rmse_adaptive:.5f})', zorder=10)
ax1.set_title(f'Итоговая аппроксимация (N={N_PATCHES}, train ±{OVERLAP_TRAIN}°, use ±{OVERLAP_USE}°)')
ax1.set_xlabel('Угол, °')
ax1.set_ylabel('Радиус, мм')
ax1.legend()
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 360)

ideal_grid = np.interp(angles_grid, sec_ideal['angle_deg'].values,
                       sec_ideal['radius_ideal_mm'].values)
residuals = fitted_adaptive - ideal_grid

ax2.plot(angles_grid, residuals, 'purple', lw=1.5, label='Остаток')
ax2.axhline(0, color='k', lw=0.5)
ax2.axhline(NOISE_STD, color='r', lw=0.8, linestyle='--', alpha=0.5,
            label=f'±{NOISE_STD} (шум)')
ax2.axhline(-NOISE_STD, color='r', lw=0.8, linestyle='--', alpha=0.5)
ax2.set_title(f'Остатки: RMSE={rmse_adaptive:.5f}, max={np.max(np.abs(residuals)):.5f}')
ax2.set_xlabel('Угол, °')
ax2.set_ylabel('Остаток, мм')
ax2.legend()
ax2.grid(True, alpha=0.3)
ax2.set_xlim(0, 360)

plt.tight_layout()
plt.savefig('final_step4_residuals.png', dpi=120)
print("Сохранено: final_step4_residuals.png")

# ============ ИТОГОВАЯ СВОДКА ============
print("\n" + "="*60)
print("ИТОГОВАЯ СВОДКА")
print("="*60)
print(f"N_PATCHES        = {N_PATCHES}")
print(f"DEGREE_MIN       = {DEGREE_MIN}")
print(f"DEGREE_MAX       = {DEGREE_MAX}")
print(f"SCALE            = {SCALE}")
print(f"NOISE_STD        = {NOISE_STD}")
print(f"OVERLAP_TRAIN    = {OVERLAP_TRAIN}°")
print(f"OVERLAP_USE      = {OVERLAP_USE}°")
print(f"\nСтепени по секторам:")
for j, d in enumerate(adaptive_degrees):
    m = patch_metrics[j]
    print(f"  Патч {j+1}: deg={d}, amp={m['amplitude']:.3f}, "
          f"amp_norm={m['amplitude']/m['mean_radius']:.5f}")
print(f"\nСуммарно коэффициентов: {sum(d+1 for d in adaptive_degrees)}")
print(f"RMSE (итог): {rmse_adaptive:.5f}")