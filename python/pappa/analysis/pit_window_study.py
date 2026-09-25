"""
pappa.analysis.pit_window_study — геометрия «окно фичера vs фаза» для решения.

Задача (постановка пользователя): сравнить два способа убрать дефект «окно ямы
заезжает в зону сшивки двух патчей, амплитуду ямы делят два полигона»:
  1) СУЗИТЬ ОКНО фичера (3.2σ = ±9.6° -> 2.5σ = ±7.5° или 2.0σ = ±6.0°);
  2) СДВИНУТЬ ФАЗУ раскладки так, чтобы окна всех ям оказались внутри плато
     одного патча (своя фаза на сечение или фаза «под ямы»).

Геометрия: узел (шов) стоит на phase + i*360/N; плато патча — |Δ| <= half_sector;
зона сшивки — |Δ до узла| <= overlap_use (там веса обоих патчей < 1). Значит
запас ямы до сшивки: margin = dist(центр ямы, ближайший узел) - overlap_use - window.
margin >= 0 — окно ямы целиком в плато (амплитуду никто не делит), иначе окно
перекрывает зону сшивки на |margin| градусов.
"""

import numpy as np

from ..core.geometry import node_angles, patch_centers
from ..core.pit_feature import pit_shape_deg


def pit_seam_margins(n_patches, phase_deg, pits, overlap_use_deg, window_deg):
    """Запас каждой ямы до зоны сшивки, ° (+ окно внутри плато, - перекрытие)."""
    nodes = np.asarray(node_angles(n_patches, phase_deg), dtype=float)
    out = []
    for c in pits:
        if not len(nodes):
            out.append(180.0 - overlap_use_deg - window_deg)
            continue
        d = float(np.min(np.abs((nodes - float(c) + 180.0) % 360.0 - 180.0)))
        out.append(d - overlap_use_deg - window_deg)
    return out


def overlap_stats(n_patches, phase_deg, pits, overlap_use_deg, window_deg):
    """Сводка по перекрытиям окон ям с зоной сшивки."""
    m = np.asarray(pit_seam_margins(n_patches, phase_deg, pits, overlap_use_deg,
                                    window_deg), dtype=float)
    if not len(m):
        return {"worst_margin": 180.0, "n_overlap": 0, "max_overlap": 0.0,
                "sum_overlap": 0.0}
    neg = np.clip(-m, 0.0, None)
    return {"worst_margin": float(np.min(m)),
            "n_overlap": int(np.count_nonzero(m < 0.0)),
            "max_overlap": float(np.max(neg)),
            "sum_overlap": float(np.sum(neg))}


def best_phase_for_pits(cfg, zones, pits, n_patches, overlap_use_deg, window_deg,
                        step_deg=0.25):
    """
    Фаза, при которой окна ям минимально заезжают в зону сшивки.

    Перебираются фазы внутри сектора; берутся только БЕЗОПАСНЫЕ по трещинам
    (минимальный отступ узла >= 0, см. pappa.analysis.layout.zone_margin_deg),
    среди них — максимум минимального запаса ям (сначала worst-case, потом
    суммарное перекрытие). Возвращает (phase, stats, safe_any).
    """
    from .layout import zone_margin_deg

    sector = 360.0 / n_patches
    phases = np.arange(0.0, sector, step_deg)
    best = None
    for ph in phases:
        safe = True
        for nd in node_angles(n_patches, float(ph)):
            if zone_margin_deg(nd, zones, cfg["guard_deg"]) < 0.0:
                safe = False
                break
        st = overlap_stats(n_patches, float(ph), pits, overlap_use_deg, window_deg)
        if not safe:
            st = dict(st, worst_margin=st["worst_margin"] - 1e3)
        key = (st["worst_margin"], -st["sum_overlap"])
        if best is None or key > best[0]:
            best = (key, float(ph), st, safe)
    return best[1], best[2], best[3]


def window_profile(delta_deg, window_sigma, sigma_deg=3.0, core_sigma=2.0):
    """Профиль веса окна (тот самый «вектор» весов) для рисунка."""
    return pit_shape_deg(delta_deg, sigma_deg, core_sigma, window_sigma, True)


def seam_contribution(model, grid, n_patches, phase_deg, overlap_use_deg):
    """
    Главный показатель «дележа амплитуды»: max |вклад ям| внутри зоны сшивки
    (±overlap_use вокруг швов), мм. 0 — окна ям не дотягиваются до сшивки и
    амплитуду ямы никто не делит.
    """
    nodes = np.asarray(node_angles(n_patches, phase_deg), dtype=float)
    if not len(nodes):
        return 0.0
    pit = np.abs(np.asarray(model.eval_part(grid, "pit"), dtype=float))
    d = np.min(np.abs((grid[:, None] - nodes[None, :] + 180.0) % 360.0 - 180.0),
               axis=1)
    mask = d <= overlap_use_deg
    return float(np.max(pit[mask])) if mask.any() else 0.0


def geometry_rows(cfg, zones_by_section, pits_by_section, sids):
    """
    Строки для таблицы/рисунка: по каждой яме — расстояние до ближайшего узла
    при общей фазе, при своей фазе (cfg["own_phase"]) и при фазе «под ямы».
    """
    rows = []
    n, ou = cfg["n_patches"], cfg["model"]["overlap_use"]
    for sid in sids:
        zones = zones_by_section[sid]
        pits = pits_by_section[sid]
        ph_best, st_best, safe = best_phase_for_pits(cfg, zones, pits, n, ou,
                                                     3.2 * cfg["sigma_deg"])
        own = cfg.get("own_phase", {}).get(sid, cfg["phase_deg"])
        for c in pits:
            rows.append({
                "section": sid, "pit": float(c),
                "nodes_shared": node_angles(n, cfg["phase_deg"]),
                "m_shared": pit_seam_margins(n, cfg["phase_deg"], [c], ou,
                                             3.2 * cfg["sigma_deg"])[0],
                "m_own": pit_seam_margins(n, own, [c], ou, 3.2 * cfg["sigma_deg"])[0],
                "m_best": pit_seam_margins(n, ph_best, [c], ou,
                                           3.2 * cfg["sigma_deg"])[0],
                "phase_best": ph_best, "safe_best": safe,
                "dist_shared": float(np.min(np.abs((np.asarray(
                    node_angles(n, cfg["phase_deg"])) - c + 180.0) % 360.0
                    - 180.0))),
                "dist_own": float(np.min(np.abs((np.asarray(
                    node_angles(n, own)) - c + 180.0) % 360.0 - 180.0))),
                "dist_best": float(np.min(np.abs((np.asarray(
                    node_angles(n, ph_best)) - c + 180.0) % 360.0 - 180.0))),
            })
    return rows
