"""
explore_per_section_phase.py

ПОЧЕМУ ЭТОТ СКРИПТ (решение по итогам обсуждения).

explore_star_layout.py ищет ОДНУ фазу на все 10 сечений: он объединяет
запретные зоны всех высот и требует, чтобы узел (шов между патчами) не попадал
на трещину НИ НА ОДНОЙ высоте. Это ограничение надуманное:

  * трещина в этих данных СПИРАЛЬНАЯ — с высотой её угол сдвигается примерно
    на 20° (сечение 0: 90.3°, сечение 9: 109.9°). Физически это ОДНА трещина,
    которая «свипается» по высоте;
  * патчи в пайплайне УЖЕ строятся для каждого сечения отдельно
    (geometry_pipeline.cpp: на сечение создаётся свой PatchApproximator) —
    общий у раскладок только угол поворота сетки (phase_deg);
  * требуя одну фазу на всё тело, мы заставляем швы избегать СУММУ углов, где
    трещина проходит хоть на какой-то высоте. Свободных дуг остаётся ~285°, и
    при N>=8 равномерная раскладка физически не может разойтись (75° запрета
    против 8 швов — им нужно >= 8 «щелей», а их меньше).

ПРАВИЛЬНАЯ ПОСТАНОВКА: фаза выбирается ДЛЯ КАЖДОГО СЕЧЕНИЯ отдельно, по зонам
ЭТОГО сечения («звезда вписывается в свою фазу»). Тогда:
  * у каждого сечения свои швы, и они уходят от трещин на этой высоте;
  * N>=8 перестаёт быть запретным: безопасная фаза находится для каждого
    сечения по отдельности (проверяется здесь же на числах);
  * фаза не «прыгает» произвольно: она следует за свипом трещины, то есть
    является измеримой функцией высоты (это и рисует overview).

ЧТО СЧИТАЕТСЯ (числа, а не слова):
  1) для каждого сечения — своя фаза: сначала безопасность (максимум минимума
     отступа шва до зон ЭТОГО сечения), затем RMSE среди безопасных фаз
     (та же двухстадийная логика, что в explore_star_layout, но БЕЗ объединения);
  2) сравнение с общей фазой (объединение зон) на тех же N: сколько RMSE стоит
     «единая фаза на всё тело» и в каких сечениях она небезопасна;
  3) ответ на вопрос «яма окажется в центральной половине патча во всех
     сечениях?»: для каждой трещины считается ближайший центр патча и
     проверяется, попадает ли яма в центральную половину сектора
     (|смещение| <= сектор/4). При раскладке по своей фазе и при общей фазе.

Рисунки (dpi x figsize >= 2000 px по ширине):
  per_section_phase_fits.png     — 4 сечения: своя фаза (цвет) против общей
                                   (серый пунктир), фон — зоны-трещины, внизу
                                   отметки швов (зелёный/красный = отступ);
  per_section_phase_overview.png — фаза против высоты (свип трещины), RMSE
                                   «своя против общей», смещение ямы от центра
                                   патча, и звёзды всех сечений на одной
                                   полярной оси.

Запуск: <python> explore_per_section_phase.py, где <python> — интерпретатор с
numpy/pandas/matplotlib (на этой машине
C:/Users/maxan/miniconda3/envs/geom-toolkit/python.exe).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys

import numpy as np

import matplotlib

matplotlib.use("Agg")             # только сохранение в файл, без GUI

import matplotlib.pyplot as plt

from appa.analysis.layout import fit_layout, layout_margins, section_crack_zones, union_zones, zone_margin_deg
from appa.core.geometry import node_angles, patch_centers
from appa.io.dataset import attach_ideal_grid, load_sections
from appa.paths import resolve_path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from appa.analysis.per_section_phase import search_phase, section_margins, section_rmse, shared_rmse_fn
from appa.report.phase_report import report_compare, report_pits, report_zones
from appa.viz.phase_figs import plot_phase_fits
from appa.viz.phase_figs import plot_overview

try:                              # чтобы кириллица в консоли не ломалась
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONFIG = {
    "csv": "synthetic_data.csv",
    "ideal_column": "radius_ideal_mm",
    "sections": [0, 2, 5, 9],               # сечения для рисунков и чисел
    "all_sections": list(range(10)),        # зоны нужны по всем высотам

    "detector": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
                 "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0},
    "guard_deg": 3.0,                       # запас шва до трещины
    "comfort_margin_deg": 5.0,              # «комфортный» отступ (плато)
    "zone_grid_step_deg": 0.01,

    "model": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
              "overlap_train": 15.0, "overlap_use": 5.0, "deg_elbow_tol": 0.05},
    "grid_points": 1440,
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},

    # N, для которых всё считается (рабочая звезда + «запретный» N=8/9)
    "n_patches_compare": [7, 8, 9],
    "phase_step_deg": 0.05,                 # мелкий шаг: отступ считается без обучения
    "rmse_phase_step_deg": 5.0,             # грубый шаг: тут обучается модель

    # «яма в центральной половине патча»: |смещение| <= sector * pit_center_frac
    "pit_center_frac": 0.25,

    "dpi": 160,
    "out_fits": "per_section_phase_fits.png",
    "out_overview": "per_section_phase_overview.png",
}

def main():
    cfg = CONFIG
    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                             cfg["cleaner"])
    attach_ideal_grid(sections, grid)

    zones_by_section = section_crack_zones(cfg, sections, cfg["all_sections"])
    union = union_zones(cfg, zones_by_section)
    report_zones(cfg, sections, zones_by_section)
    free = 360.0 - sum(b - a for a, b in union)
    print("\nОбъединение зон по всем высотам (для сравнения): "
          + ", ".join(f"[{a:.1f}, {b:.1f}]°" for a, b in union)
          + f" -> свободно {free:.1f}° из 360°")

    # --- 1) общая фаза (объединение зон), как в explore_star_layout ---
    shared_rows = {}
    for n in cfg["n_patches_compare"]:
        shared_rows[n] = search_phase(cfg, n, union,
                                      shared_rmse_fn(cfg, sections, grid, n))
    shared_margins = {
        n: section_margins(n, shared_rows[n]["phase"], zones_by_section,
                           cfg["guard_deg"], cfg["sections"])
        for n in cfg["n_patches_compare"]}

    # --- 2) своя фаза на КАЖДОЕ сечение (все 10 высот) ---
    own_all = {n: {} for n in cfg["n_patches_compare"]}
    for n in cfg["n_patches_compare"]:
        for sid in cfg["all_sections"]:
            sec = sections[sid]
            row = search_phase(cfg, n, zones_by_section[sid],
                               (lambda ph, s=sec, nn=n:
                                section_rmse(cfg, s, grid, nn, ph)))
            row["rmse_shared"] = section_rmse(cfg, sec, grid, n,
                                              shared_rows[n]["phase"])
            own_all[n][sid] = row

    report_compare(cfg, sections, zones_by_section, own_all, shared_rows,
                   shared_margins, grid)
    report_pits(cfg, sections, grid, zones_by_section, own_all, shared_rows,
                cfg["n_patches_compare"][1])

    # --- 3) рисунки ---
    n_main = cfg["n_patches_compare"][0]
    plot_phase_fits(cfg, sections, grid, zones_by_section, n_main, own_all[n_main],
              shared_rows[n_main], resolve_path(cfg["out_fits"]))
    plot_overview(cfg, sections, zones_by_section, own_all, shared_rows,
                  cfg["n_patches_compare"][1], resolve_path(cfg["out_overview"]))

    # --- 4) итог: готовый рецепт фаз по высоте ---
    n_use = n_main
    print()
    print("=" * 100)
    print("ИТОГ")
    print("=" * 100)
    own_mean = float(np.mean([own_all[n_use][s]["rmse"] for s in cfg["sections"]]))
    sh_mean = float(np.mean([own_all[n_use][s]["rmse_shared"]
                             for s in cfg["sections"]]))
    print(f"N = {n_use}: RMSE по {len(cfg['sections'])} сечениям "
          f"{own_mean:.4f} мм (своя фаза) против {sh_mean:.4f} мм (общая фаза) "
          f"= {100.0 * (1.0 - own_mean / sh_mean):+.1f}%")
    print("Фазы по сечениям (готовая таблица для пайплайна — phase_deg на "
          "высоту):")
    for sid in cfg["all_sections"]:
        r = own_all[n_use][sid]
        print(f"  сечение {sid:>2} (h={sections[sid]['height_mm']:>5.0f} мм): "
              f"phase_deg = {r['phase']:>6.2f}, отступ шва "
              f"{r['margin']:>+6.2f}°, RMSE {r['rmse']:.4f} "
              f"({'ок' if r['margin'] >= 0 else 'ШОВ НА ТРЕЩИНЕ'})")
    print(f"Рисунки: {cfg['out_fits']}, {cfg['out_overview']}")
    print("Следующий шаг по коду: geometry_pipeline уже создаёт PatchApproximator "
          "на каждое\nсечение — достаточно передавать phase_deg из этой таблицы "
          "(или искать его на месте\nпо зонам своего сечения).")

if __name__ == "__main__":
    main()
