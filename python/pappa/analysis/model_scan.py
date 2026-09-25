# вырезано из compare_patch_counts_src.py (рефакторинг, см. CONTEXT.md §21)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from ..core.outlier_cleaner import build_cleaner
from ..core.patch_approximator import PatchApproximator

PLOT_ONLY_KEYS = ("color", "label", "linestyle")
    # ключи только для рисунков: модель их не понимает


def build_variant_config(base, variant):
    """Сливает базовые параметры метода с переопределениями варианта."""
    params = dict(base)
    params.update({k: v for k, v in variant.items()
                   if k not in PLOT_ONLY_KEYS})
    return params


def make_approximator(params):
    """Создаёт PatchApproximator строго из известных ему аргументов."""
    return PatchApproximator(
        n_patches=int(params["n_patches"]),
        deg_min=int(params["deg_min"]),
        deg_max=int(params["deg_max"]),
        amplitude_scale=float(params["amplitude_scale"]),
        overlap_train=float(params["overlap_train"]),
        overlap_use=float(params["overlap_use"]),
        phase_deg=float(params.get("phase_deg", 0.0)),
    )


def evaluate_variant(section, params, angles_grid,
                     metric_on="data", metric_scope="clean"):
    """
    Обучает PatchApproximator variant-параметрами и считает метрики.

    ОБУЧЕНИЕ: идёт по ВСЕМ точкам файла, прошедшим очистку выбросов
    (section["angles"], section["radii"]). Сетка отрисовки angles_grid
    в обучение не попадает.

    angles_grid используется ТОЛЬКО для отрисовки: по нему считается
    fitted_grid — та кривая, которую рисуем на графике.

    МЕТРИКИ (RMSE/MAE/max) считаются:
      metric_on="data" — по реальным точкам файла (по умолчанию);
      metric_on="grid" — по равномерной сетке отрисовки (прежнее поведение).
    metric_scope выбирает набор точек: "clean" (после очистки) или "all".

    Возвращает (fitted_grid, rmse, info).
    """
    approx = make_approximator(params)
    approx.fit(section["angles"], section["radii"])   # ← все точки из файла

    fitted_grid = approx.eval(angles_grid)            # ← только для отрисовки

    # --- точки, по которым считаем метрику ---
    if metric_scope == "all":
        a_m, r_m = section["angles_all"], section["radii_all"]
    else:
        a_m, r_m = section["angles"], section["radii"]

    if metric_on == "grid":
        fitted_m = fitted_grid
        ideal_m = np.interp(angles_grid,
                            section["ideal_deg"], section["ideal_r"])
    else:
        fitted_m = approx.eval(a_m)
        ideal_m = np.interp(a_m, section["ideal_deg"], section["ideal_r"])

    valid = np.isfinite(fitted_m) & np.isfinite(ideal_m)
    diff = fitted_m[valid] - ideal_m[valid]
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    mae = float(np.mean(np.abs(diff)))
    max_err = float(np.max(np.abs(diff)))

    info = {
        "degrees": approx.get_degrees(),
        "half_sector": approx.half_sector_,
        "half_train": approx.half_sector_ + approx.overlap_train,
        "half_use": approx.half_sector_ + approx.overlap_use,
        "n_patches": approx.n_patches,
        "phase_deg": float(approx.phase_deg),
        "n_train": int(len(section["angles"])),
        "n_metric": int(valid.sum()),
        "metric_on": metric_on,
        "metric_scope": metric_scope,
        "mae": mae,
        "max_err": max_err,
    }
    return fitted_grid, rmse, info
