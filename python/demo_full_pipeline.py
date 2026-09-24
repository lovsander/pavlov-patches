"""
demo_full_pipeline.py

Полный pipeline:
1. OutlierCleaner — очистка
2. PatchApproximator — подробная + грубая модели
3. CrackDetector — разница моделей
4. Отрисовка по всем сечениям (16:9)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from outlier_cleaner import OutlierCleaner
from patch_approximator import PatchApproximator
from crack_detector import CrackDetector


# ============ ЗАГРУЗКА ============
data = pd.read_csv('synthetic_data.csv')


# ============ ОЧИСТКА ============
cleaner = OutlierCleaner(threshold_deriv=0.5, mad_k=9.5, z_threshold=3.5)

print("=== ОЧИСТКА ===")
cleaned_list = []
for sid in data['section_id'].unique():
    sec = data[data['section_id'] == sid].copy().sort_values('angle_deg').reset_index(drop=True)
    mask = cleaner.clean(sec['angle_deg'].values, sec['radius_mm'].values)
    sec['is_outlier_detected'] = mask
    cleaned_list.append(sec)

cleaned = pd.concat(cleaned_list, ignore_index=True)

for sid in data['section_id'].unique():
    sub = cleaned[cleaned['section_id'] == sid]
    n_out = sub['is_outlier_detected'].sum()
    print(f"  Сечение {sid}: выбросов {n_out}/{len(sub)}")


# ============ ПАРАМЕТРЫ ============
angles_grid = np.linspace(0, 360, 1440, endpoint=False)

detector = CrackDetector(
    coarse_deg_max=4,
    min_depth_mm=0.15,
    min_width_deg=5.0,
    merge_gap_deg=15.0,
)


# ============ ПРОГОН ПО ВСЕМ СЕЧЕНИЯМ ============
print("\n=== ПРОГОН ПО ВСЕМ СЕЧЕНИЯМ ===")
results = []

for sid in data['section_id'].unique():
    sec_full = cleaned[cleaned['section_id'] == sid]
    sec_clean = sec_full[~sec_full['is_outlier_detected']]
    sec_ideal = data[data['section_id'] == sid][['angle_deg', 'radius_ideal_mm']]

    if len(sec_clean) < 20:
        continue

    a_raw = sec_clean['angle_deg'].values
    r_raw = sec_clean['radius_mm'].values

    approx = PatchApproximator(
        n_patches=8, deg_min=4, deg_max=14,
        amplitude_scale=180.0, overlap_train=15.0, overlap_use=5.0,
    )
    approx.fit(a_raw, r_raw)

    approx_coarse = PatchApproximator(
        n_patches=8, deg_min=4, deg_max=4,
        amplitude_scale=180.0, overlap_train=15.0, overlap_use=5.0,
    )
    approx_coarse.fit(a_raw, r_raw)

    fitted = approx.eval(angles_grid)
    fitted_coarse = approx_coarse.eval(angles_grid)

    ideal_grid = np.interp(angles_grid, sec_ideal['angle_deg'].values,
                            sec_ideal['radius_ideal_mm'].values)
    rmse = np.sqrt(np.mean((fitted - ideal_grid) ** 2))

    defects = detector.detect(a_raw, r_raw, approx)

    results.append({
        'sid': sid,
        'sec_full': sec_full,
        'a_raw': a_raw,
        'r_raw': r_raw,
        'approx': approx,
        'fitted': fitted,
        'fitted_coarse': fitted_coarse,
        'ideal_grid': ideal_grid,
        'sec_ideal': sec_ideal,
        'rmse': rmse,
        'defects': defects,
        'degrees': approx.get_degrees(),
    })

    def_str = ", ".join([f"{d['angle_start']:.0f}°-{d['angle_end']:.0f}°"
                          for d in defects]) if defects else "нет"
    print(f"  Сечение {sid}: RMSE={rmse:.5f}, deg={approx.get_degrees()}, трещины: {def_str}")


# ============ ОТРИСОВКА: ВСЕ СЕЧЕНИЯ 16:9 ============
n_results = len(results)
n_cols = 5
n_rows = int(np.ceil(n_results / n_cols))

fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 11))
axes = axes.flatten()

for ax_idx, res in enumerate(results):
    ax = axes[ax_idx]
    sid = res['sid']
    h = data[data['section_id'] == sid]['height_mm'].iloc[0]

    ax.plot(res['sec_full']['angle_deg'], res['sec_full']['radius_mm'],
            'b.', markersize=1, alpha=0.2)

    sec_out = res['sec_full'][res['sec_full']['is_outlier_detected']]
    if len(sec_out) > 0:
        ax.scatter(sec_out['angle_deg'], sec_out['radius_mm'],
                   s=6, c='gray', marker='x', linewidths=0.5, alpha=0.4)

    ax.plot(res['sec_ideal']['angle_deg'], res['sec_ideal']['radius_ideal_mm'],
            'k-', lw=1, alpha=0.5)
    ax.plot(angles_grid, res['fitted'], 'orange', lw=1.8)
    ax.plot(angles_grid, res['fitted_coarse'], 'cyan', lw=1, linestyle='--')

    for d in res['defects']:
        a_start = d['angle_start']
        a_end = d['angle_end']

        if a_start <= a_end:
            ax.axvspan(a_start, a_end, color='red', alpha=0.2, zorder=4)
        else:
            ax.axvspan(a_start, 360, color='red', alpha=0.2, zorder=4)
            ax.axvspan(0, a_end, color='red', alpha=0.2, zorder=4)

        ax.axvline(a_start, color='red', lw=0.8, linestyle='--', alpha=0.7, zorder=15)
        ax.axvline(a_end, color='red', lw=0.8, linestyle='--', alpha=0.7, zorder=15)

        a_mid = (a_start + a_end) / 2 if a_start <= a_end else ((a_start + a_end + 360) / 2) % 360
        ax.annotate(
            f'{d["depth_mm"]:.2f}мм / {d["width_deg"]:.0f}°',
            xy=(a_mid, ax.get_ylim()[0]),
            xytext=(a_mid, ax.get_ylim()[0] + 0.1 * (ax.get_ylim()[1] - ax.get_ylim()[0])),
            ha='center', va='bottom', fontsize=6, color='red',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                      edgecolor='red', alpha=0.9, linewidth=0.5),
            zorder=20,
        )

    def_str = ", ".join([f"{d['angle_start']:.0f}°-{d['angle_end']:.0f}°" for d in res['defects']]) or "—"
    ax.set_title(f'С. {sid} | h={h:.0f}мм | RMSE={res["rmse"]:.4f} | {def_str}',
                 fontsize=8)
    ax.set_xlabel('Угол, °', fontsize=7)
    ax.set_ylabel('Радиус, мм', fontsize=7)
    ax.tick_params(labelsize=6)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 360)

for j in range(n_results, len(axes)):
    axes[j].axis('off')

plt.tight_layout()
plt.savefig('pipeline_all_sections.png', dpi=120, bbox_inches='tight')
print("\nГрафик: pipeline_all_sections.png")


# ============ ГРАФИК ТРЕЩИН ПО ВЫСОТЕ ============
fig2, (ax_depth, ax_width, ax_angle) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)


def group_defects_by_angle(all_defects, tol=30.0):
    groups = []
    for d in sorted(all_defects, key=lambda x: x['height']):
        placed = False
        for g in groups:
            if abs((d['angle_mid'] - g['angle_mid']) + 180) % 360 - 180 < tol:
                g['items'].append(d)
                placed = True
                break
        if not placed:
            groups.append({'angle_mid': d['angle_mid'], 'items': [d]})
    return groups


all_defects = []
for res in results:
    sid = res['sid']
    h = data[data['section_id'] == sid]['height_mm'].iloc[0]
    for d in res['defects']:
        a_start = d['angle_start']
        a_end = d['angle_end']
        a_mid = (a_start + a_end) / 2 if a_start <= a_end else ((a_start + a_end + 360) / 2) % 360
        all_defects.append({
            'height': h,
            'angle_mid': a_mid,
            'depth_mm': d['depth_mm'],
            'width_deg': d['width_deg'],
            'angle_start': d['angle_start'],
            'angle_end': d['angle_end'],
        })

if all_defects:
    groups = group_defects_by_angle(all_defects, tol=30.0)
    colors_g = ['red', 'blue', 'green', 'purple', 'orange']

    for gi, g in enumerate(groups):
        items = sorted(g['items'], key=lambda x: x['height'])
        hs = [it['height'] for it in items]
        ds = [it['depth_mm'] for it in items]
        ws = [it['width_deg'] for it in items]
        an = [it['angle_mid'] for it in items]
        color = colors_g[gi % len(colors_g)]

        ax_depth.plot(hs, ds, 'o-', color=color, lw=2, markersize=10,
                      label=f'трещина ~{np.mean(an):.0f}°')
        ax_width.plot(hs, ws, 'o-', color=color, lw=2, markersize=10)
        ax_angle.plot(hs, an, 'o-', color=color, lw=2, markersize=10)

    ax_depth.set_ylabel('Глубина, мм')
    ax_depth.set_title('Трещины по высоте образца')
    ax_depth.legend(fontsize=8)
    ax_depth.grid(True, alpha=0.3)

    ax_width.set_ylabel('Ширина, °')
    ax_width.grid(True, alpha=0.3)

    ax_angle.set_xlabel('Высота сечения, мм')
    ax_angle.set_ylabel('Угол центра, °')
    ax_angle.grid(True, alpha=0.3)
else:
    for ax in (ax_depth, ax_width, ax_angle):
        ax.text(0.5, 0.5, 'Трещин не найдено',
                ha='center', va='center', transform=ax.transAxes)

plt.tight_layout()
plt.savefig('pipeline_cracks_by_height.png', dpi=110)
print("График: pipeline_cracks_by_height.png")