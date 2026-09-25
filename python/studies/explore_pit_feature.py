"""
explore_pit_feature.py

ЧТО ЭТО ТАКОЕ (простыми словами).

Трещина (яма) — узкая (ширина ~4-6°, глубина 0.4-1.2 мм) на гладком профиле
радиусом ~15 мм. Полиному, чтобы «нырнуть» в неё, приходится выгибаться в очень
узкой области: у полинома нет локальности — он качается по всему окну (эффект
Рунге). Отсюда либо завышенные степени (12-14), либо недоописанная яма.

ИДЕЯ «ФИЧЕРА ЯМЫ»: дать модели готовый элемент формы — гауссову «ямку» — и
позволить МНК подобрать только её амплитуду:

    r(x) = полином(deg, x) + a * exp( -((x - c)^2) / (2 sigma^2) )

где c — центр ямы (из детектора трещин, defect_map). Центр фиксирован, поэтому
модель ЛИНЕЙНА по всем коэффициентам (полином + a) и решается тем же МНК.

ЧТО ДОДЕЛЫВАЕТСЯ В ЭТОЙ ВЕРСИИ — СШИВКА ЯМЫ С ПОЛИНОМОМ.
Чистый гаусс не равен нулю на хвостах и не имеет там нулевой производной,
поэтому на выходе из ямы в полином виден излом; вдобавок амплитуду ямы делят
между собой два соседних патча (каждый видит яму в своём обучающем окне), и на
стыке это даёт резкий переход. Поэтому гаусс теперь ОКОННЫЙ (tapered):

    phi(d) = exp(-d^2 / (2 sigma^2)) * S(|d|),   d = x - c,

      S = 1                       при |d| <= core_sigma * sigma
                                  (дно ямы точное, вес 1 — глубину не теряем)
      S = smoothstep t^2(3-2t)    при |d| от core_sigma*sigma
                                  до window_sigma*sigma
                                  (вес плавно уходит в 0 к краю окна)
      S = 0                       при |d| >= window_sigma * sigma

S имеет нулевую производную на обоих краях, поэтому phi -> 0 вместе со своей
производной: яма выходит в полином БЕЗ излома (C1), а в зоне перекрытия патчей
её вклад уже ~0.

ЧТО СРАВНИВАЕТСЯ (одна звезда на все 4 сечения, N и фаза — из CONFIG; степени у
всех вариантов ОДИНАКОВЫЕ — правило «локтя» как у базовой модели, чтобы разница
была только в способе описания ямы):

  A) poly     — текущая модель: только полином;
  B) pit_raw  — полином + чистый гаусс (как было; излом на выходе в полином);
  C) pit_win  — полином + оконный гаусс (предлагаемое исправление сшивки).

Рисунок (dpi x figsize >= 2000 px по ширине):
  pit_blend_crops.png — ТОЛЬКО крупные планы участков ям: строки = 4 сечения,
              столбцы = ямы этого сечения. Рисуется НЕ радиус, а ОСТАТОК
              (модель − эталон): только в этом масштабе видно и «дотянулись ли
              до дна», и плавность выхода в полином. Серая полоса — окно
              фичера, штриховые вертикали — его края (за ними модель обязана
              быть чистым полиномом). Сама гауссова яма (до 1.2 мм) не
              рисуется — она вне масштаба остатка.

Запуск: <python> explore_pit_feature.py, где <python> — интерпретатор с
numpy/pandas/matplotlib (на этой машине
C:/Users/maxan/miniconda3/envs/geom-toolkit/python.exe).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys

from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")             # только сохранение в файл, без GUI

import matplotlib.pyplot as plt

from appa.core.pit_feature import PIT_DEFAULTS, validate_pit_cfg

from appa.analysis.layout import section_crack_zones
from appa.io.dataset import attach_ideal_grid, load_sections, ring_interp
from appa.paths import resolve_path, resolve_plot
from appa.analysis.pit_study import fit_variant, measure, pit_crop_info
from appa.report.pit_report import report_config, report_crops, report_metrics
from appa.viz.pit_figs import VARIANTS, plot_pit_crops

try:                              # чтобы кириллица в консоли не ломалась
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONFIG = {
    "csv": "synthetic_data.csv",
    "ideal_column": "radius_ideal_mm",
    "sections": [0, 2, 5, 9],               # 4 сечения, как в остальных скриптах

    # --- ОДНА звезда на все сечения (для простоты объяснения метода) ---
    "n_patches": 7,
    "phase_deg": 24.75,                      # раскладка из CONTEXT.md §14

    # --- детектор трещин -> центры гауссовых ям (тот же, что в explore_star_layout) ---
    "detector": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
                 "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0},

    # --- параметры гауссовой ямы (оконной) ---
    # --- параметры фичера ямы: единый источник (appa.core.pit_feature) ---
    # решение 2026-09-24: оконный гаусс 3.2σ при общей фазе (CONTEXT §25)
    **PIT_DEFAULTS,

    # --- параметры модели (как в пайплайне) ---
    "model": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
              "overlap_train": 15.0, "overlap_use": 5.0, "deg_elbow_tol": 0.05},
    "grid_points": 1440,
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},

    # --- крупные планы участков ям ---
    "crop_margin_deg": 12.0,  # сколько ещё показать ЧИСТОГО полинома за окном
    "max_crops": 3,           # сколько ям на сечение попадает в рисунок

    "dpi": 160,
    "out_crops": "pit_blend_crops.png",
}

def main():
    cfg = CONFIG
    validate_pit_cfg(cfg)                 # окно не уже ядра, σ > 0
    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                             cfg["cleaner"])
    attach_ideal_grid(sections, grid)

    zones_by_section = section_crack_zones(cfg, sections, cfg["sections"])
    pits_by_section = {sid: [0.5 * (a + b) for a, b in zz]
                       for sid, zz in zones_by_section.items()}

    report_config(cfg, sections, zones_by_section)

    # --- обмер A/B/C на каждом сечении (степени у всех одинаковые) ---
    rows, models = {}, {}
    for sid in cfg["sections"]:
        rows[sid], models[sid] = {}, {}
        for v, _ in VARIANTS:
            ap = fit_variant(cfg, sections[sid], pits_by_section[sid], v)
            models[sid][v] = ap
            rows[sid][v] = measure(ap, grid, sections[sid],
                                   pits_by_section[sid])

    # --- крупные планы ям + числовая проверка сшивки ---
    crops = pit_crop_info(cfg, sections, zones_by_section, models)
    nodes_by_section = {sid: [(c + models[sid]["pit_win"].half_sector_) % 360.0
                              for c in models[sid]["pit_win"].centers_]
                        for sid in cfg["sections"]}
    report_metrics(cfg, rows)
    report_crops(cfg, crops)

    # --- рисунок: только кропы участков ям ---
    plot_pit_crops(cfg, sections, zones_by_section, crops, nodes_by_section,
                   resolve_plot(cfg["out_crops"]))

    # --- итог ---
    mean = {v: float(np.mean([rows[s][v]["rmse"] for s in cfg["sections"]]))
            for v, _ in VARIANTS}
    gain_c = 100.0 * (1.0 - mean["pit_win"] / mean["poly"])
    print()
    print("=" * 100)
    print("ВЫВОД")
    print("=" * 100)
    print(f"Средняя RMSE по {len(cfg['sections'])} сечениям (степени у всех "
          f"одинаковые): A {mean['poly']:.4f} мм, B {mean['pit_raw']:.4f} мм, "
          f"C {mean['pit_win']:.4f} мм ({gain_c:+.1f}% к A)")
    items = [it for sid in cfg["sections"] for it in crops[sid]]
    seam_b = [it['seam_pit']['pit_raw'] for it in items]
    seam_c = [it['seam_pit']['pit_win'] for it in items]
    print("Сшивка с полиномом (по %d ямам):" % len(items))
    print("  хвост фичера (до какого |Δ| вклад ямы > 1e-6 мм), макс.: "
          f"B {max(it['span']['pit_raw'] for it in items):.0f}° -> "
          f"C {max(it['span']['pit_win'] for it in items):.0f}°")
    print("  вклад ямы на шве патчей (max в ±6° от шва), медиана/максимум: "
          f"B {np.median(seam_b):.4f}/{max(seam_b):.4f} -> "
          f"C {np.median(seam_c):.4f}/{max(seam_c):.4f} мм")
    print(f"Рисунок: {cfg['out_crops']}")
    print("Фичер — прототип: ядро (patch_approximator.py, C++) и форматы "
          "(.npz/.pappa.json) не менялись.")

if __name__ == "__main__":
    main()
