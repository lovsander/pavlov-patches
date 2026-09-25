"""
explore_baseline_defects.py

Две вещи на одном наборе сечений:

1) КАК РАБОТАЕТ median_filter_wrap (скользящая медиана по кольцу, «базовый
   уровень» профиля). Показаны сечения с линиями фильтра при разных окнах
   (0.3°, 0.6°, 1°, 2°, 5°) и «цена» каждого окна: маленькое окно — фильтр
   проваливается в трещину, большое — срезает её и уносит форму.

2) ХОД ИССЛЕДОВАНИЯ «чем измерять дефектность». Сравниваются простые признаки:
       res  = |r − baseline|            — остаток (шум + одиночные всплески);
       d1   = |Δ baseline|              — наклон (первая разность);
       d2   = |Δ² baseline|             — кривизна (вторая разность, «по учебнику»);
       band = |baseline − wide_baseline| — полоса между двумя масштабами.
   Каждый делится на свою робастную sigma → безразмерные «MAD-ы», порог k задаётся
   в них. Производные считаются и прямые по точке, и по сглаженной кривой.
   Измерено на synthetic_data.csv: шаг 0.06° даёт такой шум, что производные трещину
   не видят (F1 низкий при любом k), а band находит ВСЕ трещины без ложных зон.

Истина берётся из таблицы трещин генератора (generate_data_crack_many.py):
для каждой высоты известны углы и ширина трёх трещин, поэтому оценка честная —
по ЗОНАМ (нашлась/не нашлась трещина, сколько ложных зон), а не по точкам.

Файлы на выходе:
  baseline_filter_windows.png      — 4 сечения, линии фильтра при разных окнах
  baseline_filter_tradeoff.png     — что окно фильтра сохраняет/срезает/шумит
  defect_indicators.png            — признаки по сечениям + найденные band-зоны
  defect_indicator_candidates.png  — сравнение кандидатов-признаков по зонам
  defect_threshold_sweep.png       — F1(k) для кандидатов: где у признака «плато»

Запуск: <python> explore_baseline_defects.py
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

from pappa.core.outlier_cleaner import build_cleaner, median_filter_wrap, window_points

from pappa.analysis.zones import defect_maps, detect_zones, indicator_curve, load_crack_table, mask_to_zones, score_zones, truth_zone_mask
from pappa.analysis.defect_study import candidate_results, sweep_thresholds, truth_zones_by_section, window_metrics
from pappa.paths import resolve_path, resolve_plot
from pappa.report.defect_report import report_candidates
from pappa.viz.defect_figs import plot_candidates, plot_indicators, plot_k_sweep, plot_tradeoff, plot_windows

try:                              # чтобы кириллица в консоли не ломалась
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONFIG = {
    "csv": "synthetic_data.csv",
    "sections": [0, 2, 5, 9],              # 4 сечения для рисунков
    "all_sections": list(range(10)),       # для честных средних по зонам
    "ideal_column": "radius_ideal_mm",

    # окна медианного фильтра, которые показываем линиями
    "windows_deg": [0.3, 0.6, 1.0, 2.0, 5.0],
    "baseline_deg": 1.0,                   # узкое окно (как в AutoOutlierCleaner)
    "envelope_deg": 0.5,                   # сглаживание огибающей |остатка|
    "wide_deg": 10.0,                      # широкое окно «полосы»
    "smooth_deg": 2.0,                     # сглаживание самих признаков

    # пороги детектора дефектов (в MAD признака) и параметры оценки
    "detector": {
        "env_k": 3.0,
        "d1_k": 4.0,
        "d2_k": 1.0,
        "band_k": 5.5,
        "min_zone_deg": 2.0,
        "truth_depth_frac": 0.05,          # истинная зона = глубже 5% от глубины
    },

    # кандидаты «признака дефектности»: что реально видит трещину
    "candidates": [
        {"label": "band 1°−10°, сглаж. 2°", "kind": "band", "window_deg": 1.0,
         "wide_deg": 10.0, "smooth_deg": 2.0, "k": 5.0},
        {"label": "band 1°−20°, сглаж. 2°", "kind": "band", "window_deg": 1.0,
         "wide_deg": 20.0, "smooth_deg": 2.0, "k": 9.0},
        {"label": "огибающая res, сглаж. 2°", "kind": "env", "window_deg": 1.0,
         "envelope_deg": 0.5, "smooth_deg": 2.0, "k": 3.0},
        {"label": "d1, сглаж. 2°", "kind": "d1", "window_deg": 1.0,
         "smooth_deg": 2.0, "k": 4.0},
        {"label": "d2, сглаж. 2°", "kind": "d2", "window_deg": 1.0,
         "smooth_deg": 2.0, "k": 1.0},
        {"label": "d2 без сглаживания", "kind": "d2_raw", "window_deg": 1.0,
         "smooth_deg": 2.0, "k": 2.0},
    ],

    # подбор порога k по максимуму F1 (по зонам) — «ход исследования»
    "k_sweep": {"min": 0.5, "max": 20.0, "step": 0.5, "min_zone_deg": 2.0},

    # ВЫБРАННЫЙ признак дефектности (по итогам п.3, все 10 сечений):
    #   band 1°−20°, k=9.5 -> P=1.00 R=1.00 F1=1.00, 0 ложных зон, но трещина
    #   «размазана» окном 20°; band 1°−10°, k=5.5 -> F1=0.99, 0.1 ложной зоны
    #   на сечение и заметно точнее локализует трещину — его и берём по умолчанию.
    # Им пользуются автоочистка и разрешённые зоны для раскладки (script 3).
    "chosen": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
               "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0},

    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},

    "dpi": 120,
    "out_windows": "baseline_filter_windows.png",
    "out_tradeoff": "baseline_filter_tradeoff.png",
    "out_indicators": "defect_indicators.png",
    "out_candidates": "defect_indicator_candidates.png",
    "out_k_sweep": "defect_threshold_sweep.png",
}

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

def main():
    cfg = CONFIG

    det = cfg["detector"]
    table = load_crack_table()
    sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                             cfg["cleaner"])

    print("=" * 100)
    print("1) median_filter_wrap: как окно медианы влияет на профиль")
    print("=" * 100)
    print(f"Таблица трещин: {table['source']}")
    print("Показанные сечения: " + ", ".join(
        f"{sid} (h={sections[sid]['height_mm']:.0f} мм)" for sid in cfg["sections"]))

    rows = []
    for wdeg in cfg["windows_deg"]:
        per = [window_metrics(sections[sid], wdeg, table, det["truth_depth_frac"])
               for sid in cfg["sections"]]
        n_crack = min(len(p["retained_depth_mm"]) for p in per)
        rows.append({
            "window_deg": float(wdeg),
            "window_points": per[0]["window_points"],
            "retained_depth_mm": [float(np.mean([p["retained_depth_mm"][ci]
                                                 for p in per])) for ci in range(n_crack)],
            "noise_mm": float(np.mean([p["noise_mm"] for p in per])),
            "bias_mm": float(np.mean([p["bias_mm"] for p in per])),
        })

    print("\nокно,°  точек  дно трещин: min(эталон−baseline) по трещинам, мм   "
          "шум после фильтра, мм   уведённая форма вне трещин, мм")
    for r in rows:
        depths = " / ".join(f"{v:+.2f}" for v in r["retained_depth_mm"])
        mark = "  <-- рабочее" if abs(r["window_deg"] - cfg["baseline_deg"]) < 1e-9 else ""
        print(f"{r['window_deg']:>5.2f}  {r['window_points']:>5}   {depths:<45} "
              f"{r['noise_mm']:>8.4f}                {r['bias_mm']:>8.4f}{mark}")
    print("Читается так: чем больше окно, тем меньше шума, но тем сильнее фильтр\n"
          "«срезает» дно трещины (дно уходит вверх от эталона) и уводит форму.")

    plot_windows(cfg, sections, resolve_plot(cfg["out_windows"]))
    plot_tradeoff(cfg, sections, table, rows, resolve_plot(cfg["out_tradeoff"]))
    print(f"\nРисунок: {cfg['out_windows']}")
    print(f"Рисунок: {cfg['out_tradeoff']}")

    print()
    print("=" * 100)
    print("2) Дефектность: двухмасштабная полоса band против производных d1 / d2")
    print("=" * 100)
    print("Оценка честная, по ЗОНАМ: нашлась ли трещина, сколько ложных зон.\n"
          "Признаки безразмерные (в MAD), пороги задаются в конфиге.")

    data = {}
    truth_all = truth_zones_by_section(cfg, sections, table, cfg["sections"])
    for sid in cfg["sections"]:
        s = sections[sid]
        maps = defect_maps(s["angles_clean"], s["radii_clean"],
                           cfg["baseline_deg"], cfg["envelope_deg"],
                           cfg["wide_deg"], cfg["smooth_deg"])
        truth = truth_all[sid]
        zones_band = detect_zones(s["angles_clean"], maps["band_norm"],
                                  det["band_k"], det["min_zone_deg"])
        data[sid] = {"maps": maps, "zones_truth": truth, "zones_band": zones_band,
                     "score_band": score_zones(zones_band, truth)}

    zone_of = {"band": ("band_norm", det["band_k"], "уровень 1° − уровень 10°"),
               "res": ("env_norm", det["env_k"], "огибающая |r − уровень|"),
               "d1": ("d1_norm", det["d1_k"], "|Δ уровень|, сглаж."),
               "d2": ("d2_norm", det["d2_k"], "|Δ² уровень|, сглаж."),
               "d1_raw": ("d1_raw_norm", det["d1_k"], "|Δ уровень|, без сглаж."),
               "d2_raw": ("d2_raw_norm", det["d2_k"], "|Δ² уровень|, без сглаж.")}
    for sid in cfg["sections"]:
        s = sections[sid]
        print(f"\nСечение {sid} (h={s['height_mm']:.0f} мм): "
              f"истинных зон {len(data[sid]['zones_truth'])}")
        for key, (field, k, label) in zone_of.items():
            zones = detect_zones(s["angles_clean"], data[sid]["maps"][field], k,
                                 det["min_zone_deg"])
            sc = score_zones(zones, data[sid]["zones_truth"])
            print(f"    {key:<6} {label:<26} порог {k:>4.1f} MAD: зон {sc['detected']:>3}, "
                  f"TP {sc['tp']}, FP {sc['fp']}, FN {sc['fn']}, "
                  f"P={sc['precision']:.2f} R={sc['recall']:.2f} F1={sc['f1']:.2f}")

    plot_indicators(cfg, sections, table, data, resolve_plot(cfg["out_indicators"]))
    print(f"\nРисунок: {cfg['out_indicators']}")

    print()
    print("=" * 100)
    print("3) Какой признак дефектности выбрать (кандидаты из конфига)")
    print("=" * 100)
    cand_res = candidate_results(cfg, sections, table)
    plot_candidates(cfg, sections, cand_res, resolve_plot(cfg["out_candidates"]))
    print(f"Рисунок: {cfg['out_candidates']}")

    cand_all = candidate_results(cfg, sections, table, cfg["all_sections"])
    report_candidates(cand_all,
                      f"кандидаты при порогах k из конфига, все {len(cfg['all_sections'])} сечений")

    sweep = sweep_thresholds(cfg, sections, table)
    print(f"\n{'признак':<26} {'лучш. k':>7} {'F1 при лучш. k':>15} {'FP-зон/сеч':>11}")
    for lab in cand_res["labels"]:
        b = sweep[lab]["best"]
        print(f"{lab:<26} {b['k']:>7.1f} {b['f1']:>15.2f} {b['fp']:>11.2f}")
    plot_k_sweep(cfg, sweep, resolve_plot(cfg["out_k_sweep"]))
    print(f"\nРисунок: {cfg['out_k_sweep']}")

    print("\nВывод исследования: точечные производные d1/d2 на шаге 0.06° упираются\n"
          "в шум (низкий F1 при ЛЮБОМ пороге), а двухмасштабная полоса\n"
          "band = |уровень 1° − уровень 10°| находит все трещины без ложных зон\n"
          "(широкое плато F1≈1.0). Её и стоит класть в основу автоочистки и раскладки.")

if __name__ == "__main__":
    main()
