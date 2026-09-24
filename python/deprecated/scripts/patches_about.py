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

# ============ ПАРАМЕТРЫ ============
N_PATCHES = 8
DEGREE_BASE = 3          # базовая степень
DEGREE_MAX = 15          # максимальная степень
NOISE_STD = 0.1          # оценка шума (известна из генератора)
ADAPT_ALPHA = 1.0        # порог: alpha * NOISE_STD
OVERLAP_CANDIDATES = [5, 10, 15, 20, 25, 35]
SID = 0

# ============ ПОДГОТОВКА ============
sec_clean = cleaned[(cleaned['section_id'] == SID) & (cleaned['is_outlier_detected'] == False)]
sec_ideal = data[data['section_id'] == SID][['angle_deg', 'radius_ideal_mm']].copy()
angles_raw = sec_clean['angle_deg'].values
radii_raw = sec_clean['radius_mm'].values
angles_grid = np.linspace(0, 360, 1440, endpoint=False)

# ============ ОБЩИЕ ФУНКЦИИ ============
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return 3 * t**2 - 2 * t**3

def build_patches(angles_raw, radii_raw, degree_or_list, overlap, n_patches):
    """
    degree_or_list: int (одна степень) или list (адаптивные степени).
    """
    sector = 360.0 / n_patches
    half_sector = sector / 2
    centers = [i * sector + half_sector for i in range(n_patches)]
    half_train = half_sector + overlap

    angles_ext = np.concatenate([angles_raw - 360, angles_raw, angles_raw + 360])
    radii_ext = np.concatenate([radii_raw, radii_raw, radii_raw])

    patches = []
    for j, c in enumerate(centers):
        deg = degree_or_list[j] if isinstance(degree_or_list, list) else degree_or_list
        mask = (angles_ext >= c - half_train) & (angles_ext <= c + half_train)
        local = angles_ext[mask] - c
        coefs = np.polyfit(local, radii_ext[mask], deg)
        patches.append({
            'center': c, 'half_sector': half_sector, 'half_train': half_train,
            'coefs': coefs, 'degree': deg, 'n_points': mask.sum(),
        })
    return patches

def eval_patches(angles, patches):
    fitted = np.zeros_like(angles, dtype=float)
    for i, a in enumerate(angles):
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
            vals.append(r)
            ws.append(w)
        vals = np.array(vals); ws = np.array(ws)
        if ws.sum() > 0:
            fitted[i] = np.sum(ws * vals) / np.sum(ws)
    return fitted

def compute_rmse(angles, fitted, sec_ideal):
    ideal = np.interp(angles, sec_ideal['angle_deg'].values, sec_ideal['radius_ideal_mm'].values)
    return np.sqrt(np.mean((fitted - ideal) ** 2))

def plot_polynomial(ax, center, half_train, coefs, color, label=None, lw=2.5):
    """
    Правильная отрисовка полинома: разбивка на два отрезка при переходе 0/360.
    """
    a_local = np.linspace(-half_train, half_train, 300)
    a_global_raw = center + a_local
    r_vals = np.polyval(coefs, a_local)

    mask_neg = a_global_raw < 0
    mask_over = a_global_raw > 360
    mask_ok = ~mask_neg & ~mask_over

    if mask_ok.any():
        ax.plot(a_global_raw[mask_ok], r_vals[mask_ok], color=color, lw=lw, label=label)
    if mask_neg.any():
        ax.plot(a_global_raw[mask_neg] + 360, r_vals[mask_neg], color=color, lw=lw)
    if mask_over.any():
        ax.plot(a_global_raw[mask_over] - 360, r_vals[mask_over], color=color, lw=lw)

# ============ ЭТАП 1: АВТОПОДБОР OVERLAP ============
print("\n=== АВТОПОДБОР OVERLAP ===")
overlap_results = []
for ov in OVERLAP_CANDIDATES:
    patches = build_patches(angles_raw, radii_raw, DEGREE_BASE, ov, N_PATCHES)
    fitted = eval_patches(angles_grid, patches)
    rmse = compute_rmse(angles_grid, fitted, sec_ideal)
    overlap_results.append({'overlap': ov, 'rmse': rmse})
    print(f"  overlap={ov:>3}°: RMSE={rmse:.5f}")

best_ov = min(overlap_results, key=lambda x: x['rmse'])
BEST_OVERLAP = best_ov['overlap']
print(f"\nЛучший overlap: {BEST_OVERLAP}°, RMSE={best_ov['rmse']:.5f}")

# ============ ЭТАП 2: АДАПТИВНАЯ СТЕПЕНЬ ============
print("\n=== АДАПТИВНАЯ СТЕПЕНЬ ===")

# Сначала строим с базовой степенью
patches_base = build_patches(angles_raw, radii_raw, DEGREE_BASE, BEST_OVERLAP, N_PATCHES)

# Для каждого патча увеличиваем степень до порога
threshold = ADAPT_ALPHA * NOISE_STD
adaptive_degrees = []
for j, p in enumerate(patches_base):
    c = p['center']
    # Берём точки этого патча (только его сектор, не overlap)
    mask_sec = (np.abs((angles_raw - c + 180) % 360 - 180) <= p['half_sector'])
    local_sec = (angles_raw[mask_sec] - c + 180) % 360 - 180
    r_sec = radii_raw[mask_sec]

    if len(local_sec) < 5:
        adaptive_degrees.append(DEGREE_BASE)
        continue

    best_deg = DEGREE_BASE
    best_rmse = 1e9
    for deg in range(DEGREE_BASE, DEGREE_MAX + 1):
        if deg + 1 >= len(local_sec):
            break
        coefs = np.polyfit(local_sec, r_sec, deg)
        r_fit = np.polyval(coefs, local_sec)
        rmse_local = np.sqrt(np.mean((r_fit - r_sec) ** 2))
        if rmse_local < best_rmse:
            best_rmse = rmse_local
            best_deg = deg
        if rmse_local <= threshold:
            break
    adaptive_degrees.append(best_deg)
    print(f"  Патч {j+1} (центр {c:.0f}°): степень={best_deg}, RMSE={best_rmse:.5f}")

# Финальные патчи с адаптивными степенями
patches_adaptive = build_patches(angles_raw, radii_raw, adaptive_degrees, BEST_OVERLAP, N_PATCHES)
fitted_adaptive = eval_patches(angles_grid, patches_adaptive)
rmse_adaptive = compute_rmse(angles_grid, fitted_adaptive, sec_ideal)

print(f"\nRMSE с адаптивными степенями: {rmse_adaptive:.5f}")
print(f"Суммарное число коэффициентов: {sum(d+1 for d in adaptive_degrees)}")

# ============ РИСУНОК 1: АВТОПОДБОР OVERLAP ============
fig, ax = plt.subplots(figsize=(12, 6))
ovs = [r['overlap'] for r in overlap_results]
rmses = [r['rmse'] for r in overlap_results]
ax.plot(ovs, rmses, 'bo-', lw=2, markersize=10)
ax.axvline(BEST_OVERLAP, color='red', linestyle='--', lw=2,
           label=f'Лучший: {BEST_OVERLAP}° (RMSE={best_ov["rmse"]:.5f})')
for ov, rmse in zip(ovs, rmses):
    ax.annotate(f'{rmse:.5f}', (ov, rmse), textcoords="offset points",
                xytext=(0, 10), ha='center', fontsize=9)
ax.set_xlabel('Overlap, °')
ax.set_ylabel('RMSE, мм')
ax.set_title(f'Автоподбор overlap (N={N_PATCHES}, deg={DEGREE_BASE})')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('final_step0_overlap.png', dpi=120)
print("\nСохранено: final_step0_overlap.png")

# ============ РИСУНОК 2: СЕКТОРА + ШТРИХОВКА OVERLAP ============
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
        'b.', markersize=3, alpha=0.3, label='Данные')

colors = plt.cm.tab10(np.linspace(0, 1, N_PATCHES))
sector = 360.0 / N_PATCHES
half_sector = sector / 2
half_train = half_sector + BEST_OVERLAP
centers = [i * sector + half_sector for i in range(N_PATCHES)]

for j, c in enumerate(centers):
    a_start = c - half_sector
    a_end = c + half_sector
    a_train_start = c - half_train
    a_train_end = c + half_train

    # Основной сектор
    ax.axvspan(a_start, a_end, color=colors[j], alpha=0.12)
    # Overlap слева
    ax.axvspan(a_train_start, a_start, color=colors[j], alpha=0.3,
               hatch='///', edgecolor=colors[j], linewidth=0)
    # Overlap справа
    ax.axvspan(a_end, a_train_end, color=colors[j], alpha=0.3,
               hatch='///', edgecolor=colors[j], linewidth=0)

    ax.axvline(c, color=colors[j], lw=1.5, alpha=0.8)
    ax.text(c, ax.get_ylim()[1] * 0.98, f'П{j+1} (deg={adaptive_degrees[j]})',
            ha='center', va='top', fontsize=8, color=colors[j], fontweight='bold')

ax.set_title(f'Сектора + overlap {BEST_OVERLAP}° (штриховка — зоны перекрытия)')
ax.set_xlabel('Угол, °')
ax.set_ylabel('Радиус, мм')
ax.set_xlim(0, 360)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('final_step1_sectors.png', dpi=120)
print("Сохранено: final_step1_sectors.png")

# ============ РИСУНОК 3: ОБУЧЕНИЕ ПАТЧЕЙ (исправленная отрисовка) ============
fig, axes = plt.subplots(4, 2, figsize=(16, 14))
axes = axes.flatten()

for j, p in enumerate(patches_adaptive):
    ax = axes[j]
    c = p['center']

    mask = (np.abs((angles_raw - c + 180) % 360 - 180) <= p['half_train'])
    a_train = angles_raw[mask]
    r_train = radii_raw[mask]

    ax.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
            'b.', markersize=2, alpha=0.15)
    ax.scatter(a_train, r_train, s=8, c=colors[j], alpha=0.6,
               label=f'Точки ({mask.sum()})')

    # Исправленная отрисовка полинома
    plot_polynomial(ax, c, p['half_train'], p['coefs'], colors[j],
                    label=f'deg={p["degree"]}', lw=2.5)

    ax.axvspan(c - half_sector, c + half_sector, color=colors[j], alpha=0.1)
    ax.axvline(c - p['half_train'], color='gray', lw=0.8, linestyle=':')
    ax.axvline(c + p['half_train'], color='gray', lw=0.8, linestyle=':')

    ax.set_title(f'Патч {j+1}: центр {c:.1f}°, deg={p["degree"]}, точек={p["n_points"]}',
                 fontsize=10)
    ax.set_xlim(0, 360)
    ax.set_ylim(sec_clean['radius_mm'].min() - 0.3,
                sec_clean['radius_mm'].max() + 0.3)
    ax.legend(fontsize=7, loc='lower right')
    ax.grid(True, alpha=0.3)

plt.suptitle(f'Обучение {N_PATCHES} патчей (адаптивные степени, overlap={BEST_OVERLAP}°)',
             fontsize=13)
plt.tight_layout()
plt.savefig('final_step2_training.png', dpi=120)
print("Сохранено: final_step2_training.png")

# ============ РИСУНОК 4: ВЕСА + СТЕПЕНИ ============
fig, ax = plt.subplots(figsize=(14, 6))
for j, p in enumerate(patches_adaptive):
    d = np.abs((angles_grid - p['center'] + 180) % 360 - 180)
    t = np.clip(1.0 - d / p['half_train'], 0.0, 1.0)
    w = smoothstep(t)
    ax.plot(angles_grid, w, color=colors[j], lw=2,
            label=f'П{j+1} (deg={p["degree"]})')
ax.set_title(f'Веса патчей (overlap={BEST_OVERLAP}°)')
ax.set_xlabel('Угол, °')
ax.set_ylabel('Вес')
ax.set_xlim(0, 360)
ax.set_ylim(-0.05, 1.05)
ax.legend(fontsize=8, ncol=4)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('final_step3_weights.png', dpi=120)
print("Сохранено: final_step3_weights.png")

# ============ РИСУНОК 5: ИТОГ + ОСТАТКИ ============
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

# Верх: итог
ax1.plot(sec_clean['angle_deg'], sec_clean['radius_mm'],
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
ax1.set_title(f'Итоговая аппроксимация (N={N_PATCHES}, адаптивные степени)')
ax1.set_xlabel('Угол, °')
ax1.set_ylabel('Радиус, мм')
ax1.legend()
ax1.grid(True, alpha=0.3)
ax1.set_xlim(0, 360)

# Низ: остатки
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

# ============ ИТОГОВАЯ ТАБЛИЦА ============
print("\n" + "="*60)
print("ИТОГОВАЯ СВОДКА")
print("="*60)
print(f"N_PATCHES        = {N_PATCHES}")
print(f"BEST_OVERLAP     = {BEST_OVERLAP}°")
print(f"DEGREE_BASE      = {DEGREE_BASE}")
print(f"DEGREE_MAX       = {DEGREE_MAX}")
print(f"NOISE_STD        = {NOISE_STD}")
print(f"ADAPT_ALPHA      = {ADAPT_ALPHA}")
print(f"\nАдаптивные степени:")
for j, d in enumerate(adaptive_degrees):
    print(f"  Патч {j+1}: deg={d} (коэффициентов: {d+1})")
print(f"\nСуммарно коэффициентов: {sum(d+1 for d in adaptive_degrees)}")
print(f"RMSE (адаптивный):      {rmse_adaptive:.5f}")
print(f"RMSE (базовый deg={DEGREE_BASE}):  {best_ov['rmse']:.5f}")