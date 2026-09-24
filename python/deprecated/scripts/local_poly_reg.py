import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

def local_polynomial_regression_circular(x, y, x_eval, degree=3, bandwidth=5.0):
    """
    Высокоточная локальная полиномиальная регрессия с учетом круговой геометрии.
    """
    y_eval = np.zeros_like(x_eval)
    
    for i, x0 in enumerate(x_eval):
        # Расчет кратчайшего расстояния по дуге окружности
        dx = np.abs(x - x0)
        dx = np.minimum(dx, 360.0 - dx)
        
        # Попадание в патч (окно)
        idx = dx <= bandwidth
        if np.sum(idx) < (degree + 1):
            y_eval[i] = y[np.argmin(dx)] if len(dx) > 0 else 0
            continue
            
        x_local = x[idx]
        y_local = y[idx]
        dx_local = x_local - x0
        
        # Корректировка знака разности на стыке 0/360 градусов
        dx_local = np.where(dx_local > 180.0, dx_local - 360.0, dx_local)
        dx_local = np.where(dx_local < -180.0, dx_local + 360.0, dx_local)
        
        # Веса Tricube
        u = dx[idx] / bandwidth
        weights = (1.0 - u**3)**3
        W = np.diag(weights)
        
        # Матрица Вандермонда (степень degree=2 для точного отслеживания кривизны)
        X = np.vander(dx_local, degree + 1, increasing=True)
        
        try:
            XT_W = X.T @ W
            beta = np.linalg.solve(XT_W @ X, XT_W @ y_local)
            y_eval[i] = beta[0]  # Значение полинома в точке x0
        except np.linalg.LinAlgError:
            y_eval[i] = np.sum(weights * y_local) / np.sum(weights)
            
    return y_eval

# --- БЛОК ЗАГРУЗКИ И АВТОМАТИЧЕСКОЙ НАСТРОЙКИ СЕТКИ ---
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_filename = 'synthetic_data.csv'
csv_path = os.path.join(script_dir, csv_filename)

if not os.path.exists(csv_path):
    raise FileNotFoundError(f"Файл '{csv_filename}' не найден по пути: {csv_path}")

df = pd.read_csv(csv_path, sep=None, engine='python', encoding='utf-8-sig')
df.columns = df.columns.str.strip().str.replace('﻿', '').str.replace('\ufeff', '')

if df['is_outlier'].dtype == 'object':
    df['is_outlier'] = df['is_outlier'].astype(str).str.strip().str.lower() == 'true'

df = df.sort_values('angle_deg')

# Находим РЕАЛЬНОЕ количество сечений в файле
unique_sections = sorted(df['section_id'].unique())
num_sections = len(unique_sections)

# Создаем сетку СТРОГО под количество сечений (без лишних пустых графиков)
fig, axes = plt.subplots(num_sections, 1, figsize=(12, 3.5 * num_sections), sharex=True)
if num_sections == 1:
    axes = [axes]

# ИСПРАВЛЕННЫЙ ВЫЗОВ ЦВЕТОВОЙ ПАЛИТРЫ (Совместим с Matplotlib 3.9+)
cmap = plt.get_cmap('tab10')
colors = [cmap(i) for i in np.linspace(0, 1, num_sections)]
x_eval = np.linspace(0, 360, 500) # Сетка для плавной отрисовки

for ax, sec_id, color in zip(axes, unique_sections, colors):
    df_sec = df[df['section_id'] == sec_id]
    
    df_clean = df_sec[df_sec['is_outlier'] == False]
    df_outliers = df_sec[df_sec['is_outlier'] == True]
    
    x_train = df_clean['angle_deg'].values
    y_train = df_clean['radius_mm'].values
    
    if len(x_train) == 0:
        continue
        
    # Запуск в режиме HIGH PRECISION (степень 2, окно 7 градусов)
    y_smooth = local_polynomial_regression_circular(
        x_train, y_train, x_eval, degree=2, bandwidth=7.0
    )
    
    # Визуализация
    ax.scatter(df_clean['angle_deg'], df_clean['radius_mm'], 
               color=color, alpha=0.6, s=15, label='Фактические замеры')
    
    if not df_outliers.empty:
        ax.scatter(df_outliers['angle_deg'], df_outliers['radius_mm'], 
                   color='red', marker='x', s=70, lw=1.5, label='Выбросы (пропущены)')
                   
    if 'radius_ideal_mm' in df_sec.columns:
        ax.plot(df_sec['angle_deg'], df_sec['radius_ideal_mm'], 
                color='gray', linestyle='--', linewidth=1.2, label='Номинал (Чертеж)')
                
    ax.plot(x_eval, y_smooth, color='black', linewidth=2.0, label='Высокоточный контур (LPR)')
    
    ax.set_ylabel('Радиус, мм', fontsize=10)
    height = df_sec['height_mm'].iloc[0] if 'height_mm' in df_sec.columns else 'N/A'
    ax.set_title(f'Сечение ID: {sec_id} (Высота: {height} мм)', fontsize=11, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.5)
    ax.legend(loc='upper right', fontsize=9)

axes[-1].set_xlabel('Угол, градусы', fontsize=11)
plt.xlim(0, 360)
plt.tight_layout()

output_path = os.path.join(script_dir, 'all_sections_lpr_analysis.png')
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"\n[Успешно] График сохранен без ошибок и пустых полей:\n👉 {output_path}")
