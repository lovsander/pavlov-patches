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
from .zones import crack_depths_mm, detect_zones, indicator_curve, load_crack_table, mask_to_zones, truth_zone_mask
from ..core.geometry import node_angles

def section_crack_zones(cfg, sections, sids):
    """
    Выбранный детектор (band) -> запретные зоны на каждом сечении.
    Считается по точкам ПОСЛЕ автоочистки: детектору там честнее, а всплески
    (которые всё равно выброшены из обучения) не тянут за собой порог.
    """
    det = cfg["detector"]
    zones = {}
    for sid in sids:
        s = sections[sid]
        norm = indicator_curve(s["angles_clean"], s["radii_clean"], det["kind"],
                               det["window_deg"], 0.5, det["smooth_deg"],
                               det["wide_deg"])
        zones[sid] = detect_zones(s["angles_clean"], norm, det["k"],
                                  det["min_zone_deg"])
    return zones


def zone_mask_on_grid(grid, zones):
    """Маска сетки внутри любой из угловых зон (зоны могут «заворачиваться»)."""
    m = np.zeros(len(grid), dtype=bool)
    for z in zones:
        d = np.abs((grid - 0.5 * (z[0] + z[1]) + 180.0) % 360.0 - 180.0)
        m |= d <= 0.5 * (z[1] - z[0])
    return m


def union_zones(cfg, zones_by_section, min_len_deg=1.0):
    """
    Объединение запретных зон всех сечений: раскладка должна быть безопасной
    на ЛЮБОЙ высоте, поэтому узел, попавший в трещину хотя бы одного сечения,
    считается попавшим. min(расстояние до зон сечений) = расстояние до
    объединения — поэтому дальше работаем только с объединением.
    """
    grid = np.arange(0.0, 360.0, cfg["zone_grid_step_deg"])
    mask = np.zeros(len(grid), dtype=bool)
    for zones in zones_by_section.values():
        mask |= zone_mask_on_grid(grid, zones)
    return mask_to_zones(grid, mask, min_len_deg)


def zone_margin_deg(node_deg, zones, guard_deg):
    """
    Отступ узла от ближайшей запретной зоны с учётом запаса, °.

    > 0 — узел стоит в гладкой зоне и до трещины не ближе guard_deg;
    <= 0 — узел ближе запаса к трещине (или прямо внутри неё). Чем больше,
    тем надёжнее шов: кривизна полинома на краю сектора «доезжает» до стыка.
    """
    if not zones:
        return float("inf")                 # трещин нет — любой узел безопасен
    best = float("inf")
    for z in zones:
        width = z[1] - z[0]
        center = 0.5 * (z[0] + z[1])
        d = abs((node_deg - center + 180.0) % 360.0 - 180.0)
        best = min(best, max(0.0, d - 0.5 * width))
    return best - guard_deg


def layout_margins(n_patches, phase_deg, zones, guard_deg):
    """Отступы всех узлов раскладки до объединённых зон, °."""
    nodes = node_angles(n_patches, phase_deg)
    margins = np.array([zone_margin_deg(nd, zones, guard_deg) for nd in nodes])
    return nodes, margins


def per_section_margins(n_patches, phase_deg, zones_by_section, guard_deg):
    """Мин. отступ по каждому сечению отдельно (сколько сечений выдержал узел)."""
    out = {}
    for sid, zones in sorted(zones_by_section.items()):
        _, m = layout_margins(n_patches, phase_deg, zones, guard_deg)
        out[sid] = float(np.min(m))
    return out


def fit_layout(section, grid, model_cfg, n_patches, phase_deg):
    """PatchApproximator по точкам после автоочистки + значения на сетке."""
    ap = PatchApproximator(n_patches=n_patches,
                           deg_min=model_cfg["deg_min"],
                           deg_max=model_cfg["deg_max"],
                           amplitude_scale=model_cfg["amplitude_scale"],
                           overlap_train=model_cfg["overlap_train"],
                           overlap_use=model_cfg["overlap_use"],
                           phase_deg=phase_deg,
                           deg_elbow_tol=model_cfg.get("deg_elbow_tol", 0.05))
    ap.fit(section["angles_clean"], section["radii_clean"])
    return ap, ap.eval(grid)


def layout_rmse(cfg, sections, grid, n_patches, phase_deg):
    """RMSE модели по сетке относительно эталона: среднее и по сечениям."""
    per = {}
    for sid in cfg["sections"]:
        s = sections[sid]
        _, y = fit_layout(s, grid, cfg["model"], n_patches, phase_deg)
        per[sid] = float(np.sqrt(np.mean((y - s["ideal_grid"]) ** 2)))
    return float(np.mean(list(per.values()))), per


def sector_rmse(ap, grid, ideal_grid, n_patches, phase_deg, overlap_use_deg):
    """
    RMSE по «плато» каждого сектора (без зон перекрытия) — для раскраски лучей
    звезды: видно, какой именно патч хуже описывает свою часть кольца.
    """
    sector = 360.0 / n_patches
    out = []
    for i in range(n_patches):
        c = (phase_deg + sector * (i + 0.5)) % 360.0
        d = np.abs((grid - c + 180.0) % 360.0 - 180.0)
        m = d <= max(0.5 * sector - overlap_use_deg, 0.2 * sector)
        if int(m.sum()) < 2:
            out.append(float("nan"))
            continue
        out.append(float(np.sqrt(np.mean((ap.eval(grid[m]) - ideal_grid[m]) ** 2))))
    return np.array(out)


def search_symmetric(cfg, union, zones_by_section, sections, grid):
    """
    Две стадии (в таком порядке — как в жизни):

      1) МЕЛКИЙ шаг по фазе, критерий — БЕЗОПАСНОСТЬ: максимум минимального
         отступа узла от запретных зон. Оценка отступа бесплатная (без обучения
         модели), поэтому шаг мелкий (phase_step_deg).
      2) ГРУБЫЙ шаг по фазе среди БЕЗОПАСНЫХ, критерий — RMSE: из безопасных
         фаз берём ту, что точнее описывает профиль (обучение модели дорого,
         поэтому шаг крупнее — rmse_phase_step_deg). Но не «за любую цену»:
         рассматриваются только фазы с отступом не хуже comfort_margin_deg
         (или не хуже собственного максимума N, если комфорт недостижим) —
         иначе точность выторговывала бы безопасность, а она тут — плато.

    Если безопасных фаз у N нет — RMSE считается на лучшей по отступу фазе,
    чтобы её было с чем сравнить в таблице.
    """
    rows = []
    for n in cfg["n_patches_list"]:
        sector = 360.0 / n
        phases = np.arange(0.0, sector - 1e-9, cfg["phase_step_deg"])
        worst = np.empty(len(phases))
        mean = np.empty(len(phases))
        n_in = np.empty(len(phases), dtype=int)
        for k, ph in enumerate(phases):
            _, mm = layout_margins(n, float(ph), union, cfg["guard_deg"])
            worst[k] = np.min(mm)
            mean[k] = np.mean(mm)
            n_in[k] = int(np.sum(mm < 0))

        order = int(np.argmax(worst))
        row = {"n_patches": n, "phase": float(phases[order]),
               "min_margin": float(worst[order]), "mean_margin": float(mean[order]),
               "nodes_in_zone": int(n_in[order]),
               "max_margin": float(np.max(worst)),
               "curve_phase": phases, "curve_margin": worst,
               "phase_count": len(phases),
               "safe_phases": int(np.sum(worst >= 0.0))}

        safe = phases[worst >= 0.0]
        # «комфортный» порог: ниже него безопасность уже не плато, а компромисс
        floor = min(cfg["comfort_margin_deg"], row["max_margin"])
        row["comfort_floor"] = float(floor)
        roomy = safe[worst[worst >= 0.0] >= floor - 1e-9]
        if len(roomy):
            safe = roomy
        if len(safe):
            step_k = max(1, int(round(cfg["rmse_phase_step_deg"]
                                      / cfg["phase_step_deg"])))
            best = None
            for ph in safe[::step_k]:
                rmse, per = layout_rmse(cfg, sections, grid, n, float(ph))
                if best is None or rmse < best["rmse"] - 1e-12:
                    _, mm = layout_margins(n, float(ph), union, cfg["guard_deg"])
                    best = {"phase": float(ph), "rmse": rmse,
                            "rmse_per_section": per,
                            "min_margin": float(np.min(mm)),
                            "mean_margin": float(np.mean(mm)),
                            "nodes_in_zone": int(np.sum(mm < 0))}
            row.update(best)
        else:
            row["rmse"], row["rmse_per_section"] = layout_rmse(
                cfg, sections, grid, n, row["phase"])
        rows.append(row)
    return rows


def flex_nodes(n_patches, phase_deg, union, guard_deg, flex_deg, step_deg, passes):
    """
    Гибкие узлы: жадный сдвиг каждого узла в пределах ±flex_deg ради максимума
    МИНИМАЛЬНОГО отступа (бутылочное горлышко важнее средней красоты).
    Возвращает (узлы, история минимального отступа по проходам).
    """
    nodes = [float(x) for x in node_angles(n_patches, phase_deg)]

    def worst(ns):
        return min(zone_margin_deg(nd, union, guard_deg) for nd in ns)

    history = [worst(nodes)]
    for _ in range(passes):
        for i in range(n_patches):
            base = nodes[i]
            best_val, best_shift = worst(nodes), 0.0
            for shift in np.arange(-flex_deg, flex_deg + 1e-9, step_deg):
                trial = list(nodes)
                trial[i] = (base + float(shift)) % 360.0
                v = worst(trial)
                if v > best_val + 1e-9:
                    best_val, best_shift = v, float(shift)
            nodes[i] = (base + best_shift) % 360.0
        history.append(worst(nodes))
    return np.array(sorted(nodes)), np.array(history)


def flex_cost_deg(nodes_uniform, nodes_flex):
    """Максимальный уход узла от равномерной сетки, ° (цена гибкости)."""
    return float(max(min(abs((nf - nu + 180.0) % 360.0 - 180.0) for nu in nodes_uniform)
                     for nf in nodes_flex))
