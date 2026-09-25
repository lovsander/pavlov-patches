# вырезано из _src_star_layout.py / compare_patch_counts_src.py
# вырезано из _src_star_layout.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.outlier_cleaner import build_cleaner
from ..core.patch_approximator import PatchApproximator
from ..analysis.zones import crack_depths_mm, detect_zones, indicator_curve, load_crack_table, mask_to_zones, truth_zone_mask



def load_sections(csv_path, ideal_column, cleaner_cfg):
    """
    CSV -> {section_id: {...}}. Из radii убираются выбросы (auto-очиститель),
    ideal остаётся как есть (эталон вместе с трещинами).
    """
    data = pd.read_csv(csv_path)
    sections = {}
    for sid in sorted(data["section_id"].unique()):
        sec = data[data["section_id"] == sid].sort_values("angle_deg")
        a = sec["angle_deg"].to_numpy(dtype=float)
        r = sec["radius_mm"].to_numpy(dtype=float)
        mask = build_cleaner(cleaner_cfg).clean(a, r)
        sections[int(sid)] = {
            "angles": a,
            "radii": r,
            "mask": mask,
            "angles_clean": a[~mask],
            "radii_clean": r[~mask],
            "ideal": sec[ideal_column].to_numpy(dtype=float),
            "height_mm": float(sec["height_mm"].iloc[0]),
        }
    return sections


def ring_interp(a, y, grid):
    """Интерполяция замкнутого (по углу) профиля на сетку grid."""
    a = np.asarray(a, dtype=float)
    y = np.asarray(y, dtype=float)
    aa = np.concatenate([a, a[:1] + 360.0])
    yy = np.concatenate([y, y[:1]])
    return np.interp(np.mod(grid, 360.0), aa, yy)


def attach_ideal_grid(sections, grid):
    """Эталон, интерполированный на общую сетку (для RMSE)."""
    for s in sections.values():
        s["ideal_grid"] = ring_interp(s["angles"], s["ideal"], grid)


# --- из compare_patch_counts.py ---
def load_and_clean(csv_path, cleaner_cfg, ideal_column):
    """
    Читает CSV, группирует по section_id, чистит выбросы.

    Чистильщик берётся из конфига через build_cleaner() и создаётся ЗАНОВО на
    каждое сечение: авторежим вычисляет пороги по данным этого сечения.

    Возвращает dict: section_id -> {
        'angles', 'radii',           # чистые (без выбросов) точки
        'angles_all', 'radii_all',   # все точки (для фона)
        'ideal_deg', 'ideal_r',      # эталон (углы, радиус)
        'n_total', 'n_out',          # всего точек / выброшено
        'cleaner_params',            # пороги (авто — вычисленные, ручные — заданные)
        'height_mm',
    }
    """
    data = pd.read_csv(csv_path)

    sections = {}
    for sid in sorted(data["section_id"].unique()):
        sec = data[data["section_id"] == sid] \
            .copy().sort_values("angle_deg").reset_index(drop=True)

        a_all = sec["angle_deg"].values
        r_all = sec["radius_mm"].values

        cleaner = build_cleaner(cleaner_cfg)
        mask = cleaner.clean(a_all, r_all)

        sections[sid] = {
            "angles": a_all[~mask],
            "radii": r_all[~mask],
            "angles_all": a_all,
            "radii_all": r_all,
            "ideal_deg": sec["angle_deg"].values,
            "ideal_r": sec[ideal_column].values,
            "n_total": len(a_all),
            "n_out": int(mask.sum()),
            "cleaner_params": dict(getattr(cleaner, "params_", {}) or {}),
            "height_mm": float(sec["height_mm"].iloc[0]),
        }
    return sections
