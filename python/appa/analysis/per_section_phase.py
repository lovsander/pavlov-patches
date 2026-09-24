# вырезано из _src_per_section_phase.py (рефакторинг, см. CONTEXT.md §21)

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .layout import fit_layout, layout_margins, section_crack_zones, union_zones, zone_margin_deg
from ..core.geometry import node_angles, patch_centers
from ..io.dataset import attach_ideal_grid, load_sections
from ..paths import resolve_path

def ang_dist(a, b):
    """Угловое расстояние по кольцу, °."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def section_rmse(cfg, sec, grid, n_patches, phase_deg):
    """RMSE одного сечения по сетке против эталона."""
    _, y = fit_layout(sec, grid, cfg["model"], n_patches, phase_deg)
    return float(np.sqrt(np.mean((y - sec["ideal_grid"]) ** 2)))


def search_phase(cfg, n_patches, zones, rmse_fn):
    """
    Фаза раскладки по заданным запретным зонам:

      1) мелкий шаг (phase_step_deg, без обучения) — максимум минимального
         отступа шва. Это и есть «безопасность»: шов не на трещине;
      2) среди безопасных фаз — минимум RMSE (дорого, поэтому шаг грубее,
         rmse_phase_step_deg); фазы берутся не хуже «комфортного» отступа
         (или не хуже собственного максимума, если комфорт недостижим).

    rmse_fn — функция «фаза -> RMSE»: для одного сечения или среднее по
    нескольким (тогда это общая фаза на все сечения).
    """
    sector = 360.0 / n_patches
    phases = np.arange(0.0, sector - 1e-9, cfg["phase_step_deg"])
    margins = np.empty(len(phases))
    for k, ph in enumerate(phases):
        _, mm = layout_margins(n_patches, float(ph), zones, cfg["guard_deg"])
        margins[k] = float(np.min(mm))

    best_i = int(np.argmax(margins))
    max_margin = float(margins[best_i])
    row = {"n_patches": int(n_patches), "zones": len(zones),
           "margin_phase": float(phases[best_i]), "max_margin": max_margin,
           "curve_phase": phases, "curve_margin": margins,
           "n_safe_phases": int(np.sum(margins >= 0.0))}

    safe = phases[margins >= 0.0]
    floor = min(cfg["comfort_margin_deg"], max_margin)
    roomy = safe[margins[margins >= 0.0] >= floor - 1e-9]
    if len(roomy):
        safe = roomy

    if len(safe):
        step_k = max(1, int(round(cfg["rmse_phase_step_deg"]
                                  / cfg["phase_step_deg"])))
        best = None          # с порогом комфорта: рекомендация (безопасность-плато)
        best_any = None      # без порога: лучшая точность среди безопасных
        for ph in safe[::step_k]:
            rmse = float(rmse_fn(float(ph)))
            _, mm = layout_margins(n_patches, float(ph), zones, cfg["guard_deg"])
            m = float(np.min(mm))
            if best_any is None or rmse < best_any["rmse"] - 1e-12:
                best_any = {"phase": float(ph), "rmse": rmse, "margin": m}
            if m >= floor - 1e-9 and (best is None or rmse < best["rmse"] - 1e-12):
                best = {"phase": float(ph), "rmse": rmse, "margin": m}
        row.update(best if best else best_any)
        row["safe"] = True
        row["rmse_safe_free"] = best_any["rmse"]
        row["phase_safe_free"] = best_any["phase"]
        row["margin_safe_free"] = best_any["margin"]
    else:
        # Безопасной фазы нет: берём лучшую по отступу, чтобы было с чем
        # сравнить в таблицах (и чтобы узел в зоне был видно на рисунке).
        row.update({"phase": row["margin_phase"], "margin": max_margin,
                    "rmse": float(rmse_fn(row["margin_phase"])),
                    "safe": False,
                    "rmse_safe_free": float(rmse_fn(row["margin_phase"])),
                    "phase_safe_free": row["margin_phase"],
                    "margin_safe_free": max_margin})
    return row


def phase_for_pit_centers(cfg, n_patches, zones):
    """
    Фаза, при которой центры ям максимально «сидят в центрах патчей»:
    минимизируется сумма |смещение ямы от ближайшего центра патча|.

    Нужна, чтобы ответить численно: даёт ли прицельное центрирование ям
    что-то сверх выбора фазы по безопасности швов.
    """
    if not zones:
        return 0.0, 0.0
    sector = 360.0 / n_patches
    phases = np.arange(0.0, sector, cfg["phase_step_deg"])
    cost = np.array([sum(pit_center_offsets(zones, n_patches, float(ph)))
                     for ph in phases])
    k = int(np.argmin(cost))
    return float(phases[k]), float(cost[k] / len(zones))


def shared_rmse_fn(cfg, sections, grid, n_patches):
    """RMSE, усреднённая по сечениям cfg['sections'] (для общей фазы)."""
    secs = [sections[sid] for sid in cfg["sections"]]

    def fn(phase_deg):
        return float(np.mean([section_rmse(cfg, s, grid, n_patches, phase_deg)
                              for s in secs]))
    return fn


def section_margins(n_patches, phase_deg, zones_by_section, guard_deg, sids):
    """Минимальный отступ шва по каждому сечению при заданной фазе, °."""
    out = {}
    for sid in sids:
        _, mm = layout_margins(n_patches, phase_deg, zones_by_section[sid],
                               guard_deg)
        out[sid] = float(np.min(mm))
    return out


def pit_center_offsets(zones, n_patches, phase_deg):
    """Смещения центров зон-трещин до ближайшего центра патча, °."""
    centers = patch_centers(n_patches, phase_deg)
    return [min(ang_dist(0.5 * (a + b), c) for c in centers) for a, b in zones]


def pit_center_stats(cfg, zones_by_section, n_patches, phase_deg, sids):
    """
    Сводка «яма против центра патча»: сколько ям попадает в центральную
    половину своего сектора (|смещение| <= sector * pit_center_frac).
    """
    sector = 360.0 / n_patches
    limit = sector * cfg["pit_center_frac"]
    out = {"limit_deg": limit, "per_section": {}}
    for sid in sids:
        offs = pit_center_offsets(zones_by_section[sid], n_patches, phase_deg)
        out["per_section"][sid] = {
            "offsets": offs,
            "n_pits": len(offs),
            "n_center": int(sum(1 for o in offs if o <= limit)),
        }
    return out
