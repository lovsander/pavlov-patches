"""
compare_fourier_pit.py — «хватит ли Фурье 4-6 гармоник + фичер ям вместо
метода поли-патчей».

Сравниваются на одних и тех же 4 сечениях (одна звезда N=7, phase 24.75°):

  Фурье-4 / Фурье-6      — только ряд, без ям (база);
  Фурье-6 + ямы (общая)  — Фурье и ямы подбираются вместе: Фурье «видит» ямы;
  Фурье-6 (без ям) + ямы — Фурье учится только на точках ВНЕ окон ям, затем
                           при замороженном Фурье подбираются амплитуды ям
                           (Фурье ям не видит, яму рисует только фичер);
  патчи-поли / патчи+ямы — наш метод (для сравнения).

Рисунок: fourier_vs_patches.png (строки — сечения: всё кольцо | крупно яма).
Запуск: <python> studies/compare_fourier_pit.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

from pappa.analysis.fourier_study import (base_drift, crop_data, dist_to_pits,
                                         fit_fourier_pit, measure, sweep_orders)
from pappa.analysis.layout import section_crack_zones
from pappa.analysis.pit_study import fit_variant
from pappa.analysis.pit_study import measure as measure_patches
from pappa.core.pit_feature import PIT_DEFAULTS, validate_pit_cfg
from pappa.io.dataset import attach_ideal_grid, load_sections
from pappa.paths import resolve_path, resolve_plot
from pappa.report.fourier_report import (report_config, report_sweep,
                                        report_table, report_verdict)
from pappa.viz.fourier_figs import plot_fourier_pit, plot_fourier_sweep

CONFIG = {
    "csv": "synthetic_data.csv",
    "ideal_column": "radius_ideal_mm",
    "sections": [0, 2, 5, 9],
    "fourier_orders": [4, 6],

    # --- наша звезда (та же, что в остальных исследованиях) ---
    "n_patches": 7,
    "phase_deg": 24.75,

    # --- детектор трещин -> центры ям ---
    "detector": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
                 "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0},

    # --- фичер ямы: та же форма и окно, что у патчей ---
    # --- фичер ямы: единый источник параметров (pappa.core.pit_feature) ---
    **PIT_DEFAULTS,

    # --- модель патчей ---
    "model": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
              "overlap_train": 15.0, "overlap_use": 5.0, "deg_elbow_tol": 0.05},
    "grid_points": 1440,
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},

    "crop_margin_deg": 12.0,
    "orders_sweep": [4, 6, 8, 10, 12, 16, 20, 24],
    "dpi": 160,
    "out_figure": "fourier_vs_patches.png",
    "out_sweep": "fourier_order_sweep.png",
}

def build_models(cfg, section, pits):
    """Все варианты модели для одного сечения (ключ -> объект с .eval)."""
    a, r = section["angles_clean"], section["radii_clean"]
    models = {}
    for order in cfg["fourier_orders"]:
        models[f"fourier{order}"] = fit_fourier_pit(cfg, a, r, pits, order,
                                                    "fourier")
    models["joint"] = fit_fourier_pit(cfg, a, r, pits, 6, "joint")
    models["masked"] = fit_fourier_pit(cfg, a, r, pits, 6, "masked")
    models["poly"] = fit_variant(cfg, section, pits, "poly")
    models["patches"] = fit_variant(cfg, section, pits, "pit_win")
    return models

def main():
    cfg = CONFIG
    validate_pit_cfg(cfg)
    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                             cfg["cleaner"])
    attach_ideal_grid(sections, grid)
    zones_by_section = section_crack_zones(cfg, sections, cfg["sections"])
    pits_by_section = {sid: [0.5 * (a + b) for a, b in zz]
                       for sid, zz in zones_by_section.items()}

    report_config(cfg, sections, zones_by_section)

    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]
    models_by_section, rows, drift = {}, {}, {}
    for sid in cfg["sections"]:
        s = sections[sid]
        pits = pits_by_section[sid]
        models = build_models(cfg, s, pits)
        models_by_section[sid] = models

        metrics = {}
        for key, model in models.items():
            metrics[key] = (measure_patches(model, grid, s, pits)
                            if key in ("poly", "patches")
                            else measure(model, grid, s["ideal_grid"], cfg, pits))

        # насколько база «поехала» из-за ям: Фурье(общая) vs «слепой» Фурье,
        # и патчи+ямы vs патчи без ям (вне окон ям)
        outside = dist_to_pits(grid, pits) > win
        dy = np.abs(models["patches"].eval(grid) - models["poly"].eval(grid))
        drift[sid] = {
            "joint": base_drift(models["masked"], models["joint"], grid, cfg, pits),
            "patches": (float(np.max(dy[outside])) if outside.any() else 0.0, 0.0),
        }
        rows[sid] = {"grid": grid,
                     "curves": {k: m.eval(grid) for k, m in models.items()},
                     "metrics": metrics}

    report_table(cfg, rows, drift)

    crops = crop_data(cfg, sections, zones_by_section, models_by_section,
                      cfg["sections"], win + cfg["crop_margin_deg"])
    plot_fourier_pit(cfg, sections, zones_by_section, crops, rows,
                     resolve_plot(cfg["out_figure"]))

    ref = {v: (float(np.mean([rows[s]["metrics"][v]["rmse"]
                              for s in cfg["sections"]])),
               float(np.mean([rows[s]["metrics"][v]["peak_at_pit"]
                              for s in cfg["sections"]])),
               float(np.mean([rows[s]["metrics"][v]["n_coefs"]
                              for s in cfg["sections"]])))
           for v in ("poly", "patches")}
    sweep = sweep_orders(cfg, sections, pits_by_section, cfg["orders_sweep"],
                         grid)
    report_sweep(cfg, sweep, ref)
    plot_fourier_sweep(cfg, sweep, ref, resolve_plot(cfg["out_sweep"]))

    report_verdict(cfg, rows)
    print(f"\nРисунки: {cfg['out_figure']}, {cfg['out_sweep']}")

if __name__ == "__main__":
    main()
