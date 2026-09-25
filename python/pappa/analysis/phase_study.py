# вырезано из compare_phase_shift_src.py (рефакторинг, см. CONTEXT.md §21)

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .model_scan import make_approximator
from ..io.dataset import load_and_clean
from ..paths import resolve_path

def cyclic_dist(a, b):
    """Кратчайшее расстояние по дуге, °."""
    return np.abs((np.asarray(a, float) - np.asarray(b, float) + 180.0) % 360.0
                  - 180.0)


def rmse(a, b):
    """RMSE между двумя массивами."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def find_pits(deg, r, window_deg, prominence_mm):
    """
    Углы «ям» эталона — циклические локальные минимумы радиуса.

    Яма = минимум в окне ±window_deg, глубина которого относительно
    максимумов того же окна не меньше prominence_mm.
    Возвращает отсортированный список пар (угол, глубина).
    """
    deg = np.asarray(deg, float)
    r = np.asarray(r, float)
    order = np.argsort(deg % 360.0)
    deg, r = deg[order], r[order]

    n = len(r)
    step = 360.0 / n
    k = max(1, int(round(window_deg / step)))

    cand = np.flatnonzero((r <= np.roll(r, k)) & (r <= np.roll(r, -k)))

    pits = []
    for i in cand:
        idx = (i + np.arange(-k, k + 1)) % n
        j = int(idx[int(np.argmin(r[idx]))])           # самое дно в окне
        left = r[(j + np.arange(-k, 1)) % n].max()
        right = r[(j + np.arange(0, k + 1)) % n].max()
        prom = float(min(left, right) - r[j])
        if prom < prominence_mm:
            continue
        if any(cyclic_dist(deg[j], a) < window_deg for a, _ in pits):
            continue                                    # эту яму уже нашли
        pits.append((float(deg[j]), prom))

    pits.sort()
    return pits


def aligned_phase(pit_angle, n_patches):
    """Фаза, при которой центр одного из патчей попадает точно на pit_angle."""
    sector = 360.0 / n_patches
    return float((pit_angle - sector / 2.0) % sector)


def outlier_mask(section):
    """
    True для точек файла, отброшенных очисткой выбросов.

    Число выбросов в окрестности ямы показывает, насколько "clean"-метрика
    недооценивает ошибку в самой сложной зоне профиля.
    """
    a_all = section["angles_all"]
    is_out = np.ones(len(a_all), dtype=bool)
    idx = np.clip(np.searchsorted(a_all, section["angles"]),
                  0, len(a_all) - 1)
    keep = np.isclose(a_all[idx], section["angles"])
    is_out[idx[keep]] = False
    return is_out


def sweep_phase(section, base, n_patches, step_deg, angles_grid, ideal_grid,
                metric_scope="clean", extra_phases=()):
    """
    Прогон по фазам внутри одного сектора (период свипа = sector).

    base — параметры метода без n_patches/phase_deg.
    extra_phases — фазы, которые нужно посчитать точно (например «центр
    патча на дне ямы») даже если они не попали на равномерную сетку.

    Обучение — по чистым точкам файла. RMSE считается по точкам файла
    (metric_scope) и по сетке отрисовки.

    Возвращает dict с массивами: phases, rmse_data, rmse_grid,
    degrees, centers, fitted_grid.
    """
    sector = 360.0 / n_patches
    n_steps = max(4, int(round(sector / step_deg)))
    phases = np.unique(np.concatenate([
        np.linspace(0.0, sector, n_steps, endpoint=False),
        np.asarray(list(extra_phases), dtype=float) % sector,
    ]))

    if metric_scope == "all":
        a_m, r_m = section["angles_all"], section["radii_all"]
    else:
        a_m, r_m = section["angles"], section["radii"]
    ideal_m = np.interp(a_m, section["ideal_deg"], section["ideal_r"])

    out = {"phases": phases, "rmse_data": [], "rmse_grid": [],
           "degrees": [], "centers": [], "fitted_grid": []}

    for ph in phases:
        params = dict(base)
        params["n_patches"] = int(n_patches)
        params["phase_deg"] = float(ph)

        approx = make_approximator(params)
        approx.fit(section["angles"], section["radii"])   # все чистые точки

        fitted_grid = approx.eval(angles_grid)
        fitted_m = approx.eval(a_m)

        out["rmse_data"].append(rmse(fitted_m, ideal_m))
        out["rmse_grid"].append(rmse(fitted_grid, ideal_grid))
        out["degrees"].append(approx.get_degrees())
        out["centers"].append(np.asarray(approx.centers_, float))
        out["fitted_grid"].append(fitted_grid)

    for key in ("rmse_data", "rmse_grid"):
        out[key] = np.asarray(out[key], float)

    return out
