import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- Параметры ---
N_POINTS = 3200          # точек на оборот (как у прибора)
N_SECTIONS = 10          # сечений по высоте
NOISE_STD = 0.05         # шум, мм
OUTLIER_RATE = 0.05      # 5% выбросов
RADIUS = 15.0            # средний радиус, мм
ELLIPSNESS = 0.5         # эллипсность (разница полуосей), мм
WAVINESS = 0.1           # волнистость (амплитуда), мм
WAVINESS_FREQ = 5        # частота волнистости

def generate_section(section_id, height_mm):
    """Генерирует одно сечение: 3200 точек по кругу."""
    # Углы: 0..360 с шагом 360/3200
    angles_deg = np.linspace(0, 360, N_POINTS, endpoint=False)
    angles_rad = np.deg2rad(angles_deg)

    # Идеальная форма: эллипс + волнистость
    # a, b — полуоси эллипса
    a = RADIUS + ELLIPSNESS / 2
    b = RADIUS - ELLIPSNESS / 2
    # Полярное уравнение эллипса (приближённое, для малой эллипсности)
    r_ideal = a * b / np.sqrt((b * np.cos(angles_rad))**2 + (a * np.sin(angles_rad))**2)
    # Волнистость
    r_ideal += WAVINESS * np.sin(WAVINESS_FREQ * angles_rad)

    # Шум
    r_noisy = r_ideal + np.random.normal(0, NOISE_STD, N_POINTS)

    # Выбросы (трещины/поры)
    n_outliers = int(N_POINTS * OUTLIER_RATE)
    outlier_idx = np.random.choice(N_POINTS, n_outliers, replace=False)
    is_outlier = np.zeros(N_POINTS, dtype=bool)
    is_outlier[outlier_idx] = True
    # Выбросы: резкое отклонение внутрь или наружу
    r_noisy[outlier_idx] += np.random.choice([-1, 1], n_outliers) * np.random.uniform(0.5, 2.0, n_outliers)

    # DataFrame
    df = pd.DataFrame({
        'section_id': section_id,
        'height_mm': height_mm,
        'angle_deg': angles_deg,
        'radius_mm': r_noisy,
        'radius_ideal_mm': r_ideal,
        'is_outlier': is_outlier,
    })
    return df

# --- Генерация всех сечений ---
sections = []
for i in range(N_SECTIONS):
    h = i * 5.0  # высота от 0 до 45 мм
    sections.append(generate_section(i, h))

data = pd.concat(sections, ignore_index=True)
data.to_csv('synthetic_data.csv', index=False)
print(f"Сгенерировано {len(data)} точек. Файл: synthetic_data.csv")

# --- Визуализация одного сечения ---
sec = data[data['section_id'] == 0]
fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={'projection': 'polar'})
# Чистые точки
clean = sec[~sec['is_outlier']]
ax.scatter(np.deg2rad(clean['angle_deg']), clean['radius_mm'], s=1, c='blue', label='Чистые')
# Выбросы
out = sec[sec['is_outlier']]
ax.scatter(np.deg2rad(out['angle_deg']), out['radius_mm'], s=10, c='red', label='Выбросы')
# Идеал
ax.plot(np.deg2rad(sec['angle_deg']), sec['radius_ideal_mm'], c='green', lw=1, label='Идеал')
ax.set_title(f'Сечение 0, высота 0 мм')
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
plt.tight_layout()
plt.savefig('section_0.png', dpi=100)
print("График сохранён: section_0.png")