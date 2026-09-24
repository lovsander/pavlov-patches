
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

# Автоматически определяем рабочую директорию скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))

# Пути к файлам (исходному с шумом и результирующему от C++)
raw_csv_path = os.path.join(script_dir, 'synthetic_data.csv')
smooth_csv_path = os.path.join(script_dir, 'smoothed_geometry_output.csv')

print(f"[Инфо] Чтение исходных данных: {raw_csv_path}")
print(f"[Инфо] Чтение результатов C++ пайплайна: {smooth_csv_path}")

if not os.path.exists(raw_csv_path) or not os.path.exists(smooth_csv_path):
    raise FileNotFoundError(
        "❌ Ошибка: Один из файлов (.csv) не найден в папке скрипта! "
        "Убедитесь, что 'synthetic_data.csv' и 'smoothed_geometry_output.csv' лежат рядом со скриптом."
    )

# Загружаем таблицы
df_raw = pd.read_csv(raw_csv_path)
df_smooth = pd.read_csv(smooth_csv_path)

# Очищаем заголовки от возможных BOM-символов
df_raw.columns = df_raw.columns.str.strip().str.replace('﻿', '').str.replace('\ufeff', '')
df_smooth.columns = df_smooth.columns.str.strip().str.replace('﻿', '').str.replace('\ufeff', '')

# Приведение is_outlier к bool, если это строки
if df_raw['is_outlier'].dtype == 'object':
    df_raw['is_outlier'] = df_raw['is_outlier'].astype(str).str.strip().str.lower() == 'true'

# Определяем уникальные сечения
unique_sections = sorted(df_smooth['section_id'].unique())
num_sections = len(unique_sections)

# Строим сетку графиков: 2 колонки на сечение (Слева - Профиль, Справа - Разность моделей для поиска трещин/дефектов)
fig, axes = plt.subplots(num_sections, 2, figsize=(16, 3.5 * num_sections), squeeze=False)

# Цветовая палитра для графиков
cmap = plt.get_cmap('tab10')
colors = [cmap(i) for i in np.linspace(0, 1, num_sections)]

for idx, (sec_id, color) in enumerate(zip(unique_sections, colors)):
    ax_prof = axes[idx, 0] # Левый график: Профиль радиуса
    ax_diff = axes[idx, 1] # Правый график: Дефектоскопия (Fine - Coarse)
    
    # Фильтруем данные сечения
    raw_sec = df_raw[df_raw['section_id'] == sec_id]
    smooth_sec = df_smooth[df_smooth['section_id'] == sec_id].sort_values('angle_deg')
    
    raw_clean = raw_sec[raw_sec['is_outlier'] == False]
    raw_outliers = raw_sec[raw_sec['is_outlier'] == True]
    
    height = smooth_sec['height_mm'].iloc[0] if 'height_mm' in smooth_sec.columns else 0.0
    
    # --- ЛЕВЫЙ ГРАФИК: ВОССТАНОВЛЕНИЕ КОНТУРА ---
    # Сырые неотфильтрованные замеры
    ax_prof.scatter(raw_clean['angle_deg'], raw_clean['radius_mm'], 
                    color=color, alpha=0.3, s=8, label='Сырые замеры (после фильтра)')
    
    # Выбросы, которые отбросил OutlierCleaner
    if not raw_outliers.empty:
        ax_prof.scatter(raw_outliers['angle_deg'], raw_outliers['radius_mm'], 
                        color='red', marker='x', s=40, lw=1, alpha=0.6, label='Исключенные выбросы')
    
    # Идеальный номинал по чертежу
    if 'radius_ideal_mm' in raw_sec.columns:
        ax_prof.plot(raw_sec['angle_deg'], raw_sec['radius_ideal_mm'], 
                     color='gray', linestyle='--', linewidth=1.2, label='Идеал (Номинал)')
                     
    # Результаты расчета C++ PatchApproximator
    ax_prof.plot(smooth_sec['angle_deg'], smooth_sec['radius_fine_mm'], 
                 color='black', linewidth=2.0, label='Fine Модель (Павлов)')
    ax_prof.plot(smooth_sec['angle_deg'], smooth_sec['radius_coarse_mm'], 
                 color='cyan', linewidth=1.2, linestyle=':', label='Coarse Модель (Тренд)')
    
    ax_prof.set_ylabel('Радиус, мм', fontsize=10)
    ax_prof.set_title(f'Сечение ID {sec_id} (Высота {height:.1f} мм) | Восстановление', fontsize=11, fontweight='bold')
    ax_prof.grid(True, linestyle=':', alpha=0.5)
    ax_prof.set_xlim(0, 360)
    ax_prof.legend(loc='upper right', fontsize=8, framealpha=0.8)
    
    # --- ПРАВЫЙ ГРАФИК: ДЕФЕКТОСКОПИЯ (ОСТАТКИ) ---
    # Разность между Fine и Coarse моделями (сигнализирует о локальных провалах/трещинах)
    delta_model = smooth_sec['radius_fine_mm'] - smooth_sec['radius_coarse_mm']
    
    ax_diff.plot(smooth_sec['angle_deg'], delta_model, color='purple', linewidth=1.5, label='Δ (Fine - Coarse)')
    ax_diff.axhline(0, color='black', lw=0.8, linestyle='-')
    
    # Технологические допуски формы (например, ±0.05 мм)
    ax_diff.axhline(0.05, color='red', lw=0.8, linestyle='--', alpha=0.5, label='Допуск ±0.05 мм')
    ax_diff.axhline(-0.05, color='red', lw=0.8, linestyle='--', alpha=0.5)
    
    ax_diff.set_ylabel('Δ Радиуса, мм', fontsize=10)
    ax_diff.set_title(f'Сечение ID {sec_id} | Локальные отклонения контура', fontsize=11, fontweight='bold')
    ax_diff.grid(True, linestyle=':', alpha=0.5)
    ax_diff.set_xlim(0, 360)
    ax_diff.legend(loc='upper right', fontsize=8, framealpha=0.8)

axes[-1, 0].set_xlabel('Угол, градусы', fontsize=10)
axes[-1, 1].set_xlabel('Угол, градусы', fontsize=10)

plt.tight_layout()
output_plot_path = os.path.join(script_dir, 'cpp_pipeline_results_analysis.png')
plt.savefig(output_plot_path, dpi=300, bbox_inches='tight')

print(f"\n[Успешно] График анализа геометрии построен и сохранен:\n👉")
