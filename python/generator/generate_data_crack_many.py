"""
generate_data_crack_many.py

Генератор синтетических данных для аппроксимации и детекции трещин.
Несколько трещин, каждая варьируется по высоте.

N_POINTS_PER_SECTION точек создаётся для КАЖДОГО сечения, т.е. в файле
получается N_POINTS_PER_SECTION * N_SECTIONS строк.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

from appa.paths import resolve_plot

# ============ ПАРАМЕТРЫ ============
N_POINTS_PER_SECTION = 6000   # точек на одно сечение (на оборот)
N_SECTIONS = 10               # число сечений по высоте
HEIGHT_STEP = 5.0             # шаг между сечениями, мм
NOISE_STD = 0.1
OUTLIER_RATE = 0.02
OUTLIER_MIN = 0.5
OUTLIER_MAX = 2.0

SHAPE = 'cylinder'
RADIUS = 15.0
ELLIPSNESS = 0.8
WAVINESS = 0.1
WAVINESS_FREQ = 5
CONE_ANGLE = 0.4
TILT_X = 0.2
TILT_Y = 0.03

# Полная высота детали, по которой интерполируется профиль трещин, мм.
# None -> (N_SECTIONS - 1) * HEIGHT_STEP, т.е. трещины развиваются по всей
# сгенерированной высоте. Задайте число явно, если сечений меньше, чем в
# полной детали, но геометрия трещин должна остаться прежней.
TOTAL_HEIGHT = None
if TOTAL_HEIGHT is None:
    TOTAL_HEIGHT = (N_SECTIONS - 1) * HEIGHT_STEP

# ============ ТРЕЩИНЫ (список) ============
# Каждая трещина:
#   angle_bottom, angle_top — угол центра в нижнем/верхнем сечении
#   width_bottom, width_top — ширина в градусах
#   depth_bottom, depth_top — глубина в мм
CRACKS = [
    {
        'angle_bottom': 90.0,   'angle_top': 110.0,
        'width_bottom': 40.0,   'width_top': 15.0,
        'depth_bottom': 1.8,    'depth_top': 0.4,
    },
    {
        'angle_bottom': 200.0,  'angle_top': 220.0,
        'width_bottom': 25.0,   'width_top': 30.0,
        'depth_bottom': 0.7,    'depth_top': 0.9,
    },
    {
        'angle_bottom': 315.0,  'angle_top': 300.0,
        'width_bottom': 12.0,   'width_top': 20.0,
        'depth_bottom': 0.5,    'depth_top': 1.2,
    },
]

CRACK_PROFILE = 'gauss'  # 'gauss' или 'triangle'

def crack_profile(angles_deg, height_mm, total_height, crack):
    """
    Профиль одной трещины с интерполяцией параметров по высоте.
    """
    t = height_mm / total_height if total_height > 0 else 0.0
    t = np.clip(t, 0.0, 1.0)

    angle_c = crack['angle_bottom'] + (crack['angle_top'] - crack['angle_bottom']) * t
    width = crack['width_bottom'] + (crack['width_top'] - crack['width_bottom']) * t
    depth = crack['depth_bottom'] + (crack['depth_top'] - crack['depth_bottom']) * t

    d = np.abs((angles_deg - angle_c + 180) % 360 - 180)
    half = width / 2

    if CRACK_PROFILE == 'gauss':
        sigma = half / 2.5
        delta = -depth * np.exp(-(d ** 2) / (2 * sigma ** 2))
    elif CRACK_PROFILE == 'triangle':
        delta = np.where(d < half, -depth * (1 - d / half), 0.0)
    else:
        delta = np.zeros_like(angles_deg)
    return delta

def all_cracks_profile(angles_deg, height_mm, total_height):
    """Суммарный профиль всех трещин."""
    delta = np.zeros_like(angles_deg)
    for crack in CRACKS:
        delta += crack_profile(angles_deg, height_mm, total_height, crack)
    return delta

def ideal_radius(angle_rad, height_mm, angles_deg, total_height):
    if SHAPE == 'cylinder':
        r = RADIUS
    elif SHAPE == 'cone':
        r = RADIUS + CONE_ANGLE * height_mm
    elif SHAPE == 'sphere':
        z = height_mm
        r_sq = RADIUS**2 - (z - RADIUS)**2
        r = np.sqrt(max(r_sq, 0.1))
    else:
        r = RADIUS

    a = r + ELLIPSNESS / 2
    b = r - ELLIPSNESS / 2
    r_ell = a * b / np.sqrt((b * np.cos(angle_rad))**2 + (a * np.sin(angle_rad))**2)
    r_ell += WAVINESS * np.sin(WAVINESS_FREQ * angle_rad)

    r_ell = r_ell + all_cracks_profile(angles_deg, height_mm, total_height)
    return r_ell

def generate_section(section_id, height_mm):
    angles_deg = np.linspace(0, 360, N_POINTS_PER_SECTION, endpoint=False)
    angles_rad = np.deg2rad(angles_deg)
    total_height = TOTAL_HEIGHT

    r_ideal = np.array([
        ideal_radius(a, height_mm, ad, total_height)
        for a, ad in zip(angles_rad, angles_deg)
    ])

    cx = TILT_X * height_mm
    cy = TILT_Y * height_mm

    r_noisy = r_ideal + np.random.normal(0, NOISE_STD, N_POINTS_PER_SECTION)

    n_outliers = int(N_POINTS_PER_SECTION * OUTLIER_RATE)
    outlier_idx = np.random.choice(N_POINTS_PER_SECTION, n_outliers, replace=False)
    is_outlier = np.zeros(N_POINTS_PER_SECTION, dtype=bool)
    is_outlier[outlier_idx] = True
    r_noisy[outlier_idx] += (
        np.random.choice([-1, 1], n_outliers)
        * np.random.uniform(OUTLIER_MIN, OUTLIER_MAX, n_outliers)
    )

    x = cx + r_noisy * np.cos(angles_rad)
    y = cy + r_noisy * np.sin(angles_rad)
    x_ideal = cx + r_ideal * np.cos(angles_rad)
    y_ideal = cy + r_ideal * np.sin(angles_rad)

    return pd.DataFrame({
        'section_id': section_id,
        'height_mm': height_mm,
        'angle_deg': angles_deg,
        'radius_mm': r_noisy,
        'radius_ideal_mm': r_ideal,
        'x_mm': x, 'y_mm': y,
        'x_ideal_mm': x_ideal, 'y_ideal_mm': y_ideal,
        'cx_mm': cx, 'cy_mm': cy,
        'is_outlier': is_outlier,
    })

# ============ ГЕНЕРАЦИЯ ============
np.random.seed(42)

sections = []
for i in range(N_SECTIONS):
    h = i * HEIGHT_STEP
    sections.append(generate_section(i, h))

data = pd.concat(sections, ignore_index=True)
data.to_csv('synthetic_data.csv', index=False)

print(f"Сечений: {N_SECTIONS} по {N_POINTS_PER_SECTION} точек "
      f"(итого {len(data)} точек в файле)")
print(f"Профиль трещин интерполируется по высоте {TOTAL_HEIGHT:g} мм "
      f"с шагом сечений {HEIGHT_STEP:g} мм")
print(f"Трещин: {len(CRACKS)}")
for j, c in enumerate(CRACKS):
    print(f"  Трещина {j+1}:")
    print(f"    Угол:    {c['angle_bottom']}° → {c['angle_top']}°")
    print(f"    Ширина:  {c['width_bottom']}° → {c['width_top']}°")
    print(f"    Глубина: {c['depth_bottom']} мм → {c['depth_top']} мм")

# ============ ВИЗУАЛИЗАЦИЯ СЕЧЕНИЙ ============
# Первое, среднее и последнее сечение — работает при любом N_SECTIONS
# (при N_SECTIONS = 10 получается то же [0, 4, 9], что и раньше).
SECTIONS_TO_SHOW = sorted({0, (N_SECTIONS - 1) // 2, N_SECTIONS - 1})
fig, axes = plt.subplots(1, len(SECTIONS_TO_SHOW), figsize=(18, 6))
axes = np.atleast_1d(axes).ravel()

for ax, sid in zip(axes, SECTIONS_TO_SHOW):
    sec = data[data['section_id'] == sid]
    h = sec['height_mm'].iloc[0]

    ax.plot(sec['angle_deg'], sec['radius_ideal_mm'],
            'k-', lw=2, alpha=0.6, label='Идеал (с трещинами)')
    ax.scatter(sec[~sec['is_outlier']]['angle_deg'],
               sec[~sec['is_outlier']]['radius_mm'],
               s=4, c='blue', alpha=0.4, label='Чистые')
    ax.scatter(sec[sec['is_outlier']]['angle_deg'],
               sec[sec['is_outlier']]['radius_mm'],
               s=20, c='red', alpha=0.6, label='Выбросы')

    ax.set_title(f'Сечение {sid} (h={h:.0f} мм)')
    ax.set_xlabel('Угол, °')
    ax.set_ylabel('Радиус, мм')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 360)

plt.tight_layout()
out_png = resolve_plot('generator_check.png')
plt.savefig(out_png, dpi=110)
print(f"\nГрафик: {out_png}")
