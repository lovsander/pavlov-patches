import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ПАРАМЕТРЫ ============
N_POINTS = 3600
N_SECTIONS = 10
HEIGHT_STEP = 5.0
NOISE_STD = 0.02
OUTLIER_RATE = 0.01
OUTLIER_MIN = 0.5
OUTLIER_MAX = 1.2

SHAPE = 'cylinder'
RADIUS = 15.0
ELLIPSNESS = 0.8
WAVINESS = 0.1
WAVINESS_FREQ = 5
CONE_ANGLE = 0.4
TILT_X = 0.2
TILT_Y = 0.03

# ============ ТРЕЩИНА (варьируется по высоте) ============
CRACK_ENABLED = True

# Параметры трещины в НИЖНЕМ сечении
CRACK_ANGLE_BOTTOM = 90.0    # угол центра в нижнем сечении
CRACK_WIDTH_BOTTOM = 40.0    # ширина в градусах
CRACK_DEPTH_BOTTOM = 1.8     # глубина в мм

# Параметры трещины в ВЕРХНЕМ сечении
CRACK_ANGLE_TOP = 110.0      # угол смещается (трещина идёт винтом)
CRACK_WIDTH_TOP = 15.0       # ширина уменьшается (трещина сужается)
CRACK_DEPTH_TOP = 0.4        # глубина уменьшается (трещина заживает)

CRACK_PROFILE = 'gauss'


def crack_profile(angles_deg, height_mm, total_height):
    """
    Трещина с параметрами, зависящими от высоты.
    Линейная интерполяция между нижним и верхним сечением.
    """
    t = height_mm / total_height if total_height > 0 else 0.0
    t = np.clip(t, 0.0, 1.0)

    crack_angle = CRACK_ANGLE_BOTTOM + (CRACK_ANGLE_TOP - CRACK_ANGLE_BOTTOM) * t
    crack_width = CRACK_WIDTH_BOTTOM + (CRACK_WIDTH_TOP - CRACK_WIDTH_BOTTOM) * t
    crack_depth = CRACK_DEPTH_BOTTOM + (CRACK_DEPTH_TOP - CRACK_DEPTH_BOTTOM) * t

    d = np.abs((angles_deg - crack_angle + 180) % 360 - 180)
    half = crack_width / 2

    if CRACK_PROFILE == 'gauss':
        sigma = half / 2.5
        delta = -crack_depth * np.exp(-(d ** 2) / (2 * sigma ** 2))
    elif CRACK_PROFILE == 'triangle':
        delta = np.where(d < half, -crack_depth * (1 - d / half), 0.0)
    else:
        delta = np.zeros_like(angles_deg)
    return delta


def ideal_radius(angle_rad, height_mm, angles_deg=None, total_height=45.0):
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

    if CRACK_ENABLED and angles_deg is not None:
        r_ell = r_ell + crack_profile(angles_deg, height_mm, total_height)
    return r_ell


def generate_section(section_id, height_mm):
    angles_deg = np.linspace(0, 360, N_POINTS, endpoint=False)
    angles_rad = np.deg2rad(angles_deg)
    total_height = (N_SECTIONS - 1) * HEIGHT_STEP

    r_ideal = np.array([ideal_radius(a, height_mm, ad, total_height)
                        for a, ad in zip(angles_rad, angles_deg)])

    cx = TILT_X * height_mm
    cy = TILT_Y * height_mm

    r_noisy = r_ideal + np.random.normal(0, NOISE_STD, N_POINTS)

    n_outliers = int(N_POINTS * OUTLIER_RATE)
    outlier_idx = np.random.choice(N_POINTS, n_outliers, replace=False)
    is_outlier = np.zeros(N_POINTS, dtype=bool)
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
print(f"Сгенерировано {len(data)} точек. Трещина: {CRACK_ENABLED}")

# ============ ВИЗУАЛИЗАЦИЯ СЕЧЕНИЯ 0 ============
fig, ax = plt.subplots(figsize=(8, 8))
sec = data[data['section_id'] == 0]

ax.plot(sec['x_ideal_mm'], sec['y_ideal_mm'], 'g-', lw=2, label='Эталон (с трещиной)')
ax.scatter(sec[~sec['is_outlier']]['x_mm'], sec[~sec['is_outlier']]['y_mm'],
           s=3, c='blue', alpha=0.5, label='Чистые')
ax.scatter(sec[sec['is_outlier']]['x_mm'], sec[sec['is_outlier']]['y_mm'],
           s=20, c='red', label='Выбросы')
ax.set_aspect('equal')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('crack_section.png', dpi=120)
print("График: crack_section.png")