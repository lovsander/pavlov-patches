import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============ ПАРАМЕТРЫ ============
N_POINTS = 3600            # точек на оборот
N_SECTIONS = 10           # сечений по высоте (генерируем все)
HEIGHT_STEP = 5.0         # мм между сечениями
NOISE_STD = 0.25          # шум, мм
OUTLIER_RATE = 0.02       # 2% выбросов
OUTLIER_MIN = 0.05        # мин. отклонение выброса
OUTLIER_MAX = 2.0         # макс. отклонение выброса

# Форма
SHAPE = 'cylinder'        # 'cylinder', 'cone', 'sphere', 'torus'
RADIUS = 15.0             # средний радиус
ELLIPSNESS = 0.8          # разница полуосей (мм)
WAVINESS = 0.23            # волнистость (мм)
WAVINESS_FREQ = 5         # частота волнистости
CONE_ANGLE = 0.4          # для конуса
TILT_X = 0.2              # наклон оси: смещение X на мм высоты
TILT_Y = 0.03             # наклон оси: смещение Y на мм высоты

# Какие сечения показывать (0, 3, 6, 9)
SECTIONS_TO_SHOW = [0, 3, 6, 9]


def ideal_radius(angle_rad, height_mm):
    """Идеальный радиус для данной формы и высоты."""
    if SHAPE == 'cylinder':
        r = RADIUS
    elif SHAPE == 'cone':
        r = RADIUS + CONE_ANGLE * height_mm
    elif SHAPE == 'sphere':
        z = height_mm
        r_sq = RADIUS**2 - (z - RADIUS)**2
        r = np.sqrt(max(r_sq, 0.1))
    elif SHAPE == 'torus':
        r = RADIUS + 2.0 * np.cos(angle_rad)
    else:
        r = RADIUS

    # Эллипсность
    a = r + ELLIPSNESS / 2
    b = r - ELLIPSNESS / 2
    r_ell = a * b / np.sqrt((b * np.cos(angle_rad))**2 + (a * np.sin(angle_rad))**2)

    # Волнистость
    r_ell += WAVINESS * np.sin(WAVINESS_FREQ * angle_rad)

    return r_ell


def generate_section(section_id, height_mm):
    """Генерирует одно сечение."""
    angles_deg = np.linspace(0, 360, N_POINTS, endpoint=False)
    angles_rad = np.deg2rad(angles_deg)

    r_ideal = np.array([ideal_radius(a, height_mm) for a in angles_rad])

    # Наклон оси
    cx = TILT_X * height_mm
    cy = TILT_Y * height_mm

    # Шум
    r_noisy = r_ideal + np.random.normal(0, NOISE_STD, N_POINTS)

    # Выбросы
    n_outliers = int(N_POINTS * OUTLIER_RATE)
    outlier_idx = np.random.choice(N_POINTS, n_outliers, replace=False)
    is_outlier = np.zeros(N_POINTS, dtype=bool)
    is_outlier[outlier_idx] = True
    r_noisy[outlier_idx] += (
        np.random.choice([-1, 1], n_outliers)
        * np.random.uniform(OUTLIER_MIN, OUTLIER_MAX, n_outliers)
    )

    # Декартовы координаты
    x = cx + r_noisy * np.cos(angles_rad)
    y = cy + r_noisy * np.sin(angles_rad)

    # Идеал в декартовых (без шума)
    x_ideal = cx + r_ideal * np.cos(angles_rad)
    y_ideal = cy + r_ideal * np.sin(angles_rad)

    return pd.DataFrame({
        'section_id': section_id,
        'height_mm': height_mm,
        'angle_deg': angles_deg,
        'radius_mm': r_noisy,
        'radius_ideal_mm': r_ideal,
        'x_mm': x,
        'y_mm': y,
        'x_ideal_mm': x_ideal,
        'y_ideal_mm': y_ideal,
        'cx_mm': cx,
        'cy_mm': cy,
        'is_outlier': is_outlier,
    })


# ============ ГЕНЕРАЦИЯ ============
np.random.seed(42)  # для воспроизводимости

sections = []
for i in range(N_SECTIONS):
    h = i * HEIGHT_STEP
    sections.append(generate_section(i, h))

data = pd.concat(sections, ignore_index=True)
data.to_csv('synthetic_data.csv', index=False)
print(f"Сгенерировано {len(data)} точек. Файл: synthetic_data.csv")


# ============ ВИЗУАЛИЗАЦИЯ 2x2 ============
fig, axes = plt.subplots(2, 2, figsize=(14, 14))
axes = axes.flatten()

for ax, sid in zip(axes, SECTIONS_TO_SHOW):
    sec = data[data['section_id'] == sid]
    clean = sec[~sec['is_outlier']]
    out = sec[sec['is_outlier']]

    # Идеал (зелёная линия)
    ax.plot(sec['x_ideal_mm'], sec['y_ideal_mm'],
            c='green', lw=1.5, label='Идеал (без шума)')

    # Чистые точки (синие)
    ax.scatter(clean['x_mm'], clean['y_mm'],
               s=3, c='blue', label='Чистые')

    # Выбросы (красные)
    ax.scatter(out['x_mm'], out['y_mm'],
               s=25, c='red', label='Выбросы', zorder=5)

    # Центр вращения (0, 0) — чёрный крест
    ax.axhline(0, color='gray', lw=0.5, alpha=0.5)
    ax.axvline(0, color='gray', lw=0.5, alpha=0.5)
    ax.plot(0, 0, 'k+', markersize=18, markeredgewidth=2,
            label='Центр вращения (0,0)')

    # Центр сечения — зелёный кружок
    cx = sec['cx_mm'].iloc[0]
    cy = sec['cy_mm'].iloc[0]
    ax.plot(cx, cy, 'go', markersize=12,
            markeredgecolor='black', markeredgewidth=1.5,
            label=f'Центр сечения ({cx:.1f}, {cy:.1f})')

    # Линия смещения
    ax.plot([0, cx], [0, cy], 'g--', lw=2, alpha=0.8)

    ax.set_aspect('equal')
    ax.set_title(
        f'Сечение {sid} (высота {sid * HEIGHT_STEP:.0f} мм)\n'
        f'Смещение: X={cx:.2f} мм, Y={cy:.2f} мм',
        fontsize=11
    )
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-25, 25)
    ax.set_ylim(-25, 25)
    ax.set_xlabel('X, мм')
    ax.set_ylabel('Y, мм')

plt.tight_layout()
plt.savefig('sections.png', dpi=120)
print("График: sections.png")