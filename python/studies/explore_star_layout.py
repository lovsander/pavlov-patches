"""
explore_star_layout.py

Квази-графическая раскладка патчей «звездой».

Что такое звезда здесь:
  N патчей = N лучей. Центр патча — вершина луча, а граница между соседними
  патчами («узел», шов) — впадина между лучами. Раскладка симметрична, пока
  узлы стоят через 360/N: узлы на углах phase + i*360/N, центры патчей — между
  ними (ровно это и делает PatchApproximator с phase_deg).

Зачем: шов между патчами — самое слабое место модели. Если узел попадает на
трещину, две разные полиномиальные поверхности описывают один дефект и стык
«ломается». Значит, узлы должны стоять на ГЛАДКИХ участках профиля.

Как выбирается раскладка:
  1) запретные (дефектные) зоны берутся выбранным детектором из defect_map:
     band = |уровень 1° − уровень 10°|, порог k = 5.5 MAD
     (см. explore_baseline_defects.py — он находит все трещины без ложных зон);
  2) зоны ВСЕХ сечений объединяются, и отступ узла считается до объединения:
     раскладка безопасна, только если узел не попадает в трещину НИ НА ОДНОЙ
     высоте (в этом смысл «минимального отступа по сечениям»);
     ВАЖНО: это САМЫЙ ЖЁСТКИЙ вариант — «одна фаза на всё тело». Трещина в
     этих данных свипается по высоте, поэтому честная постановка — своя фаза
     на каждое сечение; она посчитана в explore_per_section_phase.py
     (там же цена общего подхода и разбор «яма против центра патча»).
     Этот скрипт оставлен как консервативная справка и как проверка
     «а что, если фазу нельзя менять по высоте»;
  3) перебираются симметричные раскладки N = 3..12 и фаза внутри сектора;
     для каждой считаются минимальный отступ узла (за вычетом запаса guard_deg)
     и число узлов в запретной зоне;
  4) среди безопасных (отступ >= 0) берётся раскладка с наибольшим минимальным
     отступом; при равенстве — лучшая по RMSE модели (обучение на точках после
     автоочистки, RMSE по равномерной сетке относительно эталона);
  5) «гибкие узлы» (flex): симметрия слегка нарушается — каждый узел сдвигается
     в пределах ±flex_deg, чтобы выжать максимум из минимального отступа.
     RMSE для гибкой раскладки НЕ измеряется: PatchApproximator строит
     равномерную сетку (+phase_deg), поэтому flex — это рекомендация для
     неоднородной раскладки, а не новый режим модели (об этом честно сказано
     в отчёте).

Рисунки (все — >= 2000 px по ширине, «2K+»; dpi в CONFIG):
  star_layout_variants.png — звёзды N из star_n_patches (6..9) при лучшей фазе:
                             лучи = патчи, впадины = узлы, закрашены запретные
                             зоны, узлы зелёные (с отступом) / красные (в зоне);
  star_layout_report.png   — выбранная раскладка: звезда, развёртка по углу,
                             отступ и RMSE от фазы, сводка по N и flex;
  star_layout_fits.png     — 4 сечения, на каждой оси наложены N=6..9 сразу и
                             каждый N — при СВОЕЙ оптимальной фазе
                             (безопасность -> точность, как в search_symmetric).
                             Видно, как разные N укладывают ямы: у N без
                             безопасной фазы кривая полупрозрачная, потому что
                             это сравнение, а не рекомендация.
                             Контрастные цвета — палитра Okabe–Ito (FIT_STYLES).
  star_layout_patches.png  — обучение патчей выбранной раскладки: панель = патч
                             (как в архивном final_step2_training.png из
                             deprecated/scripts/patches_about*.py): обучающие
                             точки, полином патча, границы train/blend, фон
                             запретных зон, узлы с отступом; последняя панель —
                             самый тесный узел среди N=6..9.

Почему N<6 и N>9 не рисуются: N<6 — широкие окна и сглаживание полинома
«съедают» ямы (ошибка модели растёт, а не безопасность), N>9 — узлы всё чаще
попадают на трещины. Рабочий диапазон N=6..9 (CONFIG fits_n_patches /
star_n_patches); числа по-прежнему считаются для всех N=3..12, печатаются в
консоль и остаются в сводке на star_layout_report.png.

Запуск: <python> explore_star_layout.py, где <python> — интерпретатор с
numpy/pandas/matplotlib. На этой машине это conda-окружение
C:/Users/maxan/miniconda3/envs/geom-toolkit/python.exe (в системном
C:/Python314 этих пакетов нет).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys

from pathlib import Path

import numpy as np

import pandas as pd

import matplotlib

matplotlib.use("Agg")             # только сохранение в файл, без GUI

import matplotlib.pyplot as plt

from appa.analysis.layout import (fit_layout, flex_cost_deg, flex_nodes,
                                  per_section_margins, search_symmetric,
                                  section_crack_zones, sector_rmse, union_zones)
from appa.analysis.zones import (crack_depths_mm, detect_zones, indicator_curve,
                                 load_crack_table, mask_to_zones, truth_zone_mask)
from appa.core.geometry import node_angles, patch_centers
from appa.core.outlier_cleaner import build_cleaner
from appa.core.patch_approximator import PatchApproximator
from appa.io.dataset import attach_ideal_grid, load_sections
from appa.paths import resolve_path, resolve_plot
from appa.report.layout_report import report_chosen, report_overlay, report_rows
from appa.viz.layout_figs import (overlay_curves, plot_layout_fits,
                                  plot_layout_report, plot_patches,
                                  plot_variants)
from appa.viz.star import STAR_INNER_R, STAR_TOP_R, draw_star

try:                              # чтобы кириллица в консоли не ломалась
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONFIG = {
    "csv": "synthetic_data.csv",
    "sections": [0, 2, 5, 9],               # сечения для рисунков и RMSE
    "all_sections": list(range(10)),        # для робастного отступа (объединение зон)
    "ideal_column": "radius_ideal_mm",

    # --- детектор запретных зон: тот же, что выбран в explore_baseline_defects ---
    "detector": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
                 "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0,
                 "truth_depth_frac": 0.05},
    # запас: узел должен быть не ближе этого расстояния к трещине
    "guard_deg": 3.0,
    # «комфортный» отступ: внутри него безопасность уже плато, дальше торгуемся
    # только точностью (RMSE). Если у раскладки лучший отступ меньше комфортного,
    # берём фазы, близкие к её собственному максимуму.
    "comfort_margin_deg": 5.0,
    # маска объединения зон строится на этой сетке (мелко, чтобы не терять края)
    "zone_grid_step_deg": 0.01,

    # --- параметры модели (как в пайплайне) ---
    # Степень выбирается по остаткам обучения (правило «локтя», deg_elbow_tol);
    # amplitude_scale — историческая шкала, на выбор степени не влияет.
    "model": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
              "overlap_train": 15.0, "overlap_use": 5.0,
              "deg_elbow_tol": 0.05},
    "grid_points": 1440,

    # --- перебор симметричных раскладок ---
    "n_patches_list": [3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "phase_step_deg": 0.05,          # мелкий шаг: отступ считается без обучения
    "rmse_phase_step_deg": 5.0,      # грубый шаг: тут уже обучается модель

    # --- гибкие узлы ---
    "flex_deg": 6.0,
    "flex_step_deg": 0.25,
    "flex_passes": 3,

    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},

    # --- какие N попадают на рисунки (каждый при СВОЕЙ фазе) ---
    # Отсекаем лишнее: N < 6 ставят слишком мало патчей (широкие окна «съедают»
    # ямы из-за сглаживания полинома), N > 9 ставят узлы на трещины.
    "fits_n_patches": [6, 7, 8, 9],     # наложение кривых на 4 сечения
    "star_n_patches": [6, 7, 8, 9],     # звёзды (лучи = патчи, впадины = узлы)

    # --- стиль графиков наложения (линий немного, поэтому линии заметные) ---
    "style": {
        "variant_lw": 1.3,       # толщина кривых аппроксимации
        "ideal_lw": 0.9,         # толщина линии эталона (сплошная)
        "data_ms": 1.0,          # размер маркера «данные»
        "data_alpha": 0.18,      # прозрачность фона данных
        "safe_alpha": 1.00,      # кривая безопасной раскладки (контраст!)
        "unsafe_alpha": 0.55,    # кривая N без безопасной фазы (для сравнения)
        "zone_alpha": 0.14,      # фон запретных зон
        "patch_col_alpha": 0.10, # фон сектора патча на рисунке обучения
        "train_ms": 6.0,         # размер маркера обучающих точек
        "node_lw": 1.0,          # толщина вертикали узла (шва) на рисунке обучения
        "window_pad_deg": 6.0,   # запас окна вокруг half_train на рисунке обучения
        "issue_half_deg": 22.0,  # полуокно вокруг «проблемного» узла, °
    },

    # dpi 160 при figsize 16x10 (и 17.5x7.4 у звёзд, 17x11.5 у отчёта) даёт
    # «2K+»: >= 2000 px по ширине — правило для презентационных рисунков.
    # Шрифты и линии заданы в пунктах, поэтому dpi масштабирует рисунок целиком.
    "dpi": 160,
    "out_variants": "star_layout_variants.png",
    "out_report": "star_layout_report.png",
    "out_fits": "star_layout_fits.png",
    "out_patches": "star_layout_patches.png",
}

def main():
    cfg = CONFIG
    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    table = load_crack_table()
    sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                             cfg["cleaner"])
    attach_ideal_grid(sections, grid)

    print("=" * 100)
    print("Раскладка патчей «звездой»: узлы (швы между патчами) не должны "
          "попадать на трещины")
    print("=" * 100)
    print(f"Таблица трещин: {table['source']}")
    print("Сечения для рисунков и RMSE: " + ", ".join(
        f"{sid} (h={sections[sid]['height_mm']:.0f} мм)" for sid in cfg["sections"]))
    det = cfg["detector"]
    print(f"Запретные зоны = трещины по детектору {det['kind']} "
          f"({det['window_deg']:g}° vs {det['wide_deg']:g}°, сглаживание "
          f"{det['smooth_deg']:g}°, порог {det['k']:g} MAD, зона от "
          f"{det['min_zone_deg']:g}°)")
    print("Отступ узла считается до объединения зон всех сечений: раскладка "
          "безопасна только\nесли узел не попадает в трещину ни на одной высоте.")

    zones_by_section = section_crack_zones(cfg, sections, cfg["all_sections"])
    print("\nНайденные зоны-трещины:")
    for sid, z in zones_by_section.items():
        txt = ", ".join(f"[{a:.1f}, {b:.1f}]°" for a, b in z) or "нет"
        print(f"  сечение {sid:>2} (h={sections[sid]['height_mm']:>5.0f} мм): {txt}")

    union = union_zones(cfg, zones_by_section)
    print("\nОбъединение по всем сечениям (сюда узлам нельзя):")
    print("  " + (", ".join(f"[{a:.1f}, {b:.1f}]°" for a, b in union) or "нет"))
    free = 360.0 - sum(b - a for a, b in union)
    print(f"  свободно под узлы: {free:.1f}° из 360°")
    print("  ЭТО КОНСЕРВАТИВНЫЙ ВАРИАНТ (одна фаза на всё тело). Своя фаза на "
          "каждое сечение\n  считается в explore_per_section_phase.py: там "
          "N = 8 перестаёт быть запретным, потому\n  что швы уходят от трещин "
          "именно на этой высоте, а не «в среднем по телу».")

    print()
    print("=" * 100)
    print("1) Перебор симметричных раскладок: N = 3..12, фаза внутри сектора")
    print("=" * 100)
    rows = search_symmetric(cfg, union, zones_by_section, sections, grid)
    report_rows(rows, cfg["guard_deg"], cfg["phase_step_deg"])

    print()
    print("=" * 100)
    print("2) Выбор раскладки: из БЕЗОПАСНЫХ — самая точная (минимальный RMSE)")
    print("=" * 100)
    print("Порядок именно такой: у безопасности есть «плато» (отступ 4° и 25° "
          "одинаково хороши),\nа у RMSE — нет: лишние патчи всегда точнее. "
          "Поэтому сначала отсекаем небезопасные,\nа точность сравниваем уже "
          "только среди них.")
    safe = [r for r in rows if r["min_margin"] >= 0]
    if safe:
        chosen = min(safe, key=lambda r: (r["rmse"], -r["min_margin"]))
        print(f"Безопасные раскладки: " + ", ".join(
            f"N={r['n_patches']} (отступ {r['min_margin']:+.1f}°, RMSE {r['rmse']:.4f})"
            for r in safe))
    else:
        chosen = max(rows, key=lambda r: r["min_margin"])
        print("Ни одна симметричная раскладка не даёт положительного отступа — "
              "берём лучшую по отступу (нужно либо уменьшить запас, либо "
              "гибкие узлы).")
    chosen["per_section"] = per_section_margins(chosen["n_patches"], chosen["phase"],
                                                zones_by_section, cfg["guard_deg"])

    # --- гибкие узлы для выбранной раскладки ---
    flex_nodes_arr, flex_history = flex_nodes(
        chosen["n_patches"], chosen["phase"], union, cfg["guard_deg"],
        cfg["flex_deg"], cfg["flex_step_deg"], cfg["flex_passes"])
    flex_info = {
        "nodes": flex_nodes_arr,
        "history": flex_history,
        "min_margin": float(flex_history[-1]),
        "cost_deg": flex_cost_deg(node_angles(chosen["n_patches"], chosen["phase"]),
                                  flex_nodes_arr),
        "flex_deg": cfg["flex_deg"],
    }

    # --- что даёт выбранная раскладка модели ---
    sid0 = cfg["sections"][0]
    ap, _ = fit_layout(sections[sid0], grid, cfg["model"], chosen["n_patches"],
                       chosen["phase"])
    sec_rm = sector_rmse(ap, grid, sections[sid0]["ideal_grid"],
                         chosen["n_patches"], chosen["phase"],
                         cfg["model"]["overlap_use"])
    report_chosen(chosen, flex_info, zones_by_section)
    print(f"\n  RMSE по патчам (сечение {sid0}, "
          f"плато сектора — без зон перекрытия):")
    for i in range(chosen["n_patches"]):
        print(f"    луч {i + 1:>2} (центр "
              f"{patch_centers(chosen['n_patches'], chosen['phase'])[i]:>5.1f}°): "
              f"степень {int(ap.degrees_[i]):>2}, RMSE {sec_rm[i]:.4f} мм")

    # --- наложение N из cfg["fits_n_patches"] на 4 сечения ---
    print()
    print("=" * 100)
    print("3) Наложение N = "
          + ", ".join(str(n) for n in cfg["fits_n_patches"])
          + " на 4 сечения — каждый N при СВОЕЙ оптимальной фазе")
    print("=" * 100)
    curves = overlay_curves(cfg, sections, grid, rows)
    report_overlay(curves, cfg)
    plot_layout_fits(cfg, sections, grid, union, curves, resolve_plot(cfg["out_fits"]))
    issue = plot_patches(cfg, sections, grid, union, chosen, ap, curves,
                         resolve_plot(cfg["out_patches"]))
    print(f"\nПроблемное место (последняя панель {cfg['out_patches']}): "
          f"сечение {issue['section']}, N = {issue['n_patches']}, узел "
          f"{issue['node_deg']:.1f}°, отступ {issue['node_margin']:+.2f}°, "
          f"узлов в запретных зонах {issue['nodes_in_zone']}")
    print(f"  макс |Δr| в ±5° вокруг узла: " + ", ".join(
        f"N={n}: {p:.4f} мм" for n, p in sorted(issue["peaks_mm"].items())))

    # --- рисунки ---
    plot_variants(cfg, rows, union, resolve_plot(cfg["out_variants"]))
    plot_layout_report(cfg, sections, table, union, rows, chosen, flex_info,
                resolve_plot(cfg["out_report"]))
    print(f"\nРисунок: {cfg['out_variants']} "
          f"(звёзды N = {', '.join(str(n) for n in cfg['star_n_patches'])})")
    print(f"Рисунок: {cfg['out_report']}")
    print(f"Рисунок: {cfg['out_fits']}")
    print(f"Рисунок: {cfg['out_patches']}")

    print()
    print("=" * 100)
    print("ВЫВОД")
    print("=" * 100)
    print(f"Раскладка по умолчанию: N = {chosen['n_patches']}, "
          f"phase_deg = {chosen['phase']:g}° — узел ближе всего "
          f"{chosen['min_margin']:+.1f}° к трещине (запас {cfg['guard_deg']:g}°).")
    print("Если нужен ещё больший запас — гибкие узлы (см. выше), но тогда "
          "раскладка перестаёт быть\nравномерной, и модель должна уметь "
          "неоднородные секторы.")

if __name__ == "__main__":
    main()
