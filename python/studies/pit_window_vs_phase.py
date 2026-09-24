"""
pit_window_vs_phase.py — «окно фичера 2.5σ против фазы раскладки»: витрина для
решения (по просьбе пользователя).

Сравниваются варианты (прежний вид = первый):
  1) общая фаза 24.75°, окно 3.2σ — как сейчас;
  2) общая фаза, окно 2.5σ — только сузить окно;
  3) своя фаза на сечение (таблица из CONTEXT §18), окно 3.2σ;
  4) своя фаза, окно 2.5σ;
  5) фаза «под ямы»: фаза, при которой окна ям минимально заезжают в зону
     сшивки патчей, окно 3.2σ.

Рисунки:
  pit_window_geometry.png — геометрия без подгонок (профили веса окна, запас до
                            швов по каждой яме, суммарные перекрытия, развёртка
                            кольца для худшего сечения);
  pit_window_fits.png     — подгонки на точках (самая глубокая яма и яма с
                            худшей геометрией в каждом сечении).

Запуск: <python> studies/pit_window_vs_phase.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

from appa.analysis.layout import section_crack_zones
from appa.analysis.pit_study import fit_variant
from appa.analysis.pit_study import measure as measure_patches
from appa.analysis.pit_window_study import (best_phase_for_pits, geometry_rows,
                                            overlap_stats, seam_contribution)
from appa.core.geometry import node_angles
from appa.core.pit_feature import PIT_DEFAULTS, validate_pit_cfg
from appa.io.dataset import attach_ideal_grid, load_sections, ring_interp
from appa.paths import resolve_path
from appa.report.pit_window_report import report_fits, report_geometry
from appa.viz.pit_window_figs import plot_window_fits, plot_window_geometry

CONFIG = {
    "csv": "synthetic_data.csv",
    "ideal_column": "radius_ideal_mm",
    "sections": [0, 2, 5, 9],               # где считаем подгонки и рисунок 2
    "all_sections": list(range(10)),        # где считаем геометрию (все ямы)

    # --- прежний вид ---
    "n_patches": 7,
    "phase_deg": 24.75,
    # --- фичер ямы: единый источник параметров (appa.core.pit_feature) ---
    # «прежний вид» = PIT_DEFAULTS (окно 3.2σ); решение 2026-09-24 (CONTEXT §25)
    **PIT_DEFAULTS,

    # --- своя фаза НА СЕЧЕНИЕ (N=7, из CONTEXT §18) ---
    "own_phase": {0: 21.70, 1: 15.30, 2: 13.50, 3: 12.00, 4: 13.95, 5: 15.10,
                  6: 33.15, 7: 20.85, 8: 21.75, 9: 24.75},

    # --- сдвиг фазы для проверки окон (шаг 0.25°) ---
    "detector": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
                 "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0},
    "guard_deg": 3.0,
    "model": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
              "overlap_train": 15.0, "overlap_use": 5.0, "deg_elbow_tol": 0.05},
    "grid_points": 1440,
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},

    "crop_margin_deg": 12.0,
    "dpi": 160,
    "out_geometry": "pit_window_geometry.png",
    "out_fits": "pit_window_fits.png",
}

VARIANTS = {
    "shared32": {"ls": "-", "color": "#0072B2", "lw": 1.9,
                 "label": "прежний вид: общая фаза 24.75°, окно 3.2σ"},
    "shared25": {"ls": (0, (5, 2)), "color": "#56B4E9", "lw": 1.4,
                 "label": "общая фаза, окно 2.5σ (уже)"},
    "own32": {"ls": (0, (1.5, 1.5)), "color": "#E69F00", "lw": 1.3,
              "label": "своя фаза на сечение, окно 3.2σ"},
    "own25": {"ls": (0, (4, 1.5, 1, 1.5)), "color": "#7B3294", "lw": 1.3,
              "label": "своя фаза, окно 2.5σ"},
    "best32": {"ls": (0, (8, 2)), "color": "#009E73", "lw": 1.6,
               "label": "фаза «под ямы», окно 3.2σ"},
}

def crop_one(section, sid, angle, half, models, width=0.0):
    """Крупный план одной ямы: точки, эталон и кривые всех вариантов."""
    loc = np.linspace(-half, half, 601)
    glob = (angle + loc) % 360.0
    dl = np.abs((section["angles_clean"] - angle + 180.0) % 360.0 - 180.0)
    near = dl <= half
    w = 0.5 * half  # для оценки глубины берём широкие плечи
    shoulder = (dl >= w) & (dl <= 2.0 * w)
    core = dl <= 0.25 * w
    depth = (float(np.median(section["radii_clean"][shoulder])
                   - np.min(section["radii_clean"][core]))
             if shoulder.any() and core.any() else 0.0)
    return {"angle": float(angle), "depth": depth, "width": float(width),
            "loc": loc,
            "ideal": ring_interp(section["angles"], section["ideal"], glob),
            "curves": {k: m.eval(glob) for k, m in models.items()},
            "pts_a": section["angles_clean"][near] - float(angle),
            "pts_r": section["radii_clean"][near]}

def main():
    cfg = CONFIG
    validate_pit_cfg(cfg)
    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                             cfg["cleaner"])
    attach_ideal_grid(sections, grid)
    zones_all = section_crack_zones(cfg, sections, cfg["all_sections"])
    pits_all = {sid: [0.5 * (a + b) for a, b in zz]
                for sid, zz in zones_all.items()}
    ou = cfg["model"]["overlap_use"]

    # --- 1) ГЕОМЕТРИЯ по всем сечениям ---
    rows = geometry_rows(cfg, zones_all, pits_all, cfg["all_sections"])
    per_section = {}
    for sid in cfg["all_sections"]:
        zones, pits = zones_all[sid], pits_all[sid]
        ph_best, st_best, safe = best_phase_for_pits(
            cfg, zones, pits, cfg["n_patches"], ou,
            cfg["pit_window_sigma"] * cfg["sigma_deg"])
        per_section[sid] = {
            "shared": {w: overlap_stats(cfg["n_patches"], cfg["phase_deg"], pits,
                                        ou, w * cfg["sigma_deg"])
                       for w in (3.2, 2.5, 2.0)},
            "own": {3.2: overlap_stats(cfg["n_patches"],
                                       cfg["own_phase"][sid], pits, ou,
                                       3.2 * cfg["sigma_deg"])},
            "best": {3.2: st_best},
            "best_phase": ph_best, "best_safe": safe,
        }
    report_geometry(cfg, rows, per_section)

    sid_worst = max(cfg["sections"],
                    key=lambda s: per_section[s]["shared"][3.2]["sum_overlap"])
    plot_window_geometry(cfg, rows, per_section, sections, zones_all, pits_all,
                         sid_worst, resolve_path(cfg["out_geometry"]))

    # --- 2) ПОДГОНКИ для 4 сечений и 5 вариантов ---
    rows_fits, crops_by_section, models_by_section = {}, {}, {}
    for sid in cfg["sections"]:
        sec = sections[sid]
        pits = pits_all[sid]
        ph_best = per_section[sid]["best_phase"]
        variants = {"shared32": (cfg["phase_deg"], 3.2),
                    "shared25": (cfg["phase_deg"], 2.5),
                    "own32": (cfg["own_phase"][sid], 3.2),
                    "own25": (cfg["own_phase"][sid], 2.5),
                    "best32": (ph_best, 3.2)}
        models, metrics, seam = {}, {}, {}
        for key, (ph, wsig) in variants.items():
            cfg_i = dict(cfg, phase_deg=float(ph), pit_window_sigma=float(wsig))
            ap = fit_variant(cfg_i, sec, pits, "pit_win")
            models[key] = ap
            metrics[key] = measure_patches(ap, grid, sec, pits)
            seam[key] = seam_contribution(ap, grid, cfg["n_patches"], float(ph),
                                          ou)
        models_by_section[sid] = models
        rows_fits[sid] = {"metrics": metrics, "seam": seam}

        # самая глубокая яма и яма с худшей геометрией (окно ближе всего к шву)
        nodes = np.asarray(node_angles(cfg["n_patches"], cfg["phase_deg"]))

        def local_depth(p):
            d = np.abs((sec["angles_clean"] - p + 180.0) % 360.0 - 180.0)
            sh, cr = (d >= 6.0) & (d <= 15.0), d <= 4.0
            if not (sh.any() and cr.any()):
                return 0.0
            return float(np.median(sec["radii_clean"][sh])
                         - np.min(sec["radii_clean"][cr]))

        def dist_to_seam(p):
            return float(np.min(np.abs((nodes - p + 180.0) % 360.0 - 180.0)))

        half = cfg["pit_window_sigma"] * cfg["sigma_deg"] + cfg["crop_margin_deg"]

        def zone_width(angle):
            for a, b in zones_all[sid]:
                if a <= angle <= b:
                    return b - a
            return 0.0

        p_deep = max(pits, key=local_depth)
        p_worst = min(pits, key=dist_to_seam)
        deep = crop_one(sec, sid, p_deep, half, models, zone_width(p_deep))
        worst = crop_one(sec, sid, p_worst, half, models, zone_width(p_worst))
        crops_by_section[sid] = [deep, worst]

    report_fits(cfg, rows_fits, VARIANTS,
                {k: v["label"] for k, v in VARIANTS.items()})
    plot_window_fits(cfg, sections, zones_all, crops_by_section, rows_fits,
                     VARIANTS, resolve_path(cfg["out_fits"]))
    print(f"\nРисунки: {cfg['out_geometry']}, {cfg['out_fits']}")

if __name__ == "__main__":
    main()
