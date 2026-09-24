"""
compare_cleaner_auto.py

Сравнение РУЧНОГО и АВТОМАТИЧЕСКОГО подбора параметров очистки выбросов.

Зачем: пороги OutlierCleaner (threshold_deriv=0.5 мм/точку, mad_k=9.5,
z_threshold=3.5) подбирались руками под конкретный файл. В авторежиме
(AutoOutlierCleaner) пороги считаются по самим данным известными простыми
методами, а форма профиля снимается локальным робастным уровнем — поэтому
дно глубоких ям перестаёт считаться выбросом.

Что считается тут, по каждому сечению:
1) Качество обнаружения выбросов относительно ИСТИНЫ из генератора
   (колонка is_outlier): TP/FP/FN, precision, recall, F1.
2) Сколько настоящих (не выбросов) точек потеряно рядом с самой глубокой
   ямой — тот самый дефект ручного режима.
3) Как очистка влияет на саму модель: RMSE подгонки (N патчей) по
   равномерной сетке относительно эталона radius_ideal_mm и относительно
   сырых точек (обе метрики честные, по всему кольцу).
4) Автоподбор порога по внешнему критерию (tune): свип порога и выбор
   лучшего по сеточной RMSE — вместо угадывания константы. Замер показывает,
   что поверхность критерия плоская (и 5-фолдовая CV с робастной потерей тоже):
   стандартные константы уже оптимальны, а тюнинг может уехать в переочистку.

Отдельно видно два эффекта:
- шлюз по производной (|dr| > k*sigma(dr), аналог ручного threshold_deriv)
  добавляет ~1 ложную точку на каждый всплеск (всплеск — перепад и «до», и
  «после» себя), поэтому в авторежиме он выключен;
- масштаб в окне у фильтра Хампеля неустойчив на коротких окнах: нужен либо
  общий масштаб по остатку, либо широкое окно.

Графики (cleaner_auto_report.png): флаги на сечении, зум на яму, F1 по
методам, RMSE по методам, свип порога, чувствительность к окну Хампеля.

Запуск: python compare_cleaner_auto.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

import pandas as pd

import matplotlib

matplotlib.use("Agg")  # только сохранение в файл, без GUI

import matplotlib.pyplot as plt

from pathlib import Path

from appa.core.outlier_cleaner import AutoOutlierCleaner, build_cleaner

from appa.core.patch_approximator import PatchApproximator
from appa.analysis.cleaner_study import evaluate_method, fmt, hampel_window_sweep, make_ctx, mean_or_none
from appa.paths import resolve_path
from appa.report.cleaner_report import print_section_report, print_summary
from appa.viz.cleaner_figs import plot_cleaner_report

CONFIG = {
    "csv": "synthetic_data.csv",
    "sections": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    "ideal_column": "radius_ideal_mm",
    "truth_column": "is_outlier",       # истина из генератора (если есть)

    # --- модель для оценки влияния очистки ---
    "model": {
        "n_patches": 8,
        "deg_min": 4,
        "deg_max": 14,
        "amplitude_scale": 180.0,
        "overlap_train": 15.0,
        "overlap_use": 5.0,
        "phase_deg": 0.0,
    },
    "grid_points": 1440,

    # --- ручной режим (как в пайплайне) ---
    "manual": {"threshold_deriv": 0.5, "mad_k": 9.5, "z_threshold": 3.5},

    # --- сравниваемые методы ---
    # mode="manual" — как есть; mode="auto" — пороги по данным.
    # deriv_gate — автошлюз по производной (аналог threshold_deriv): на синтетике
    # он ухудшает precision, поэтому в авторежиме выключен, а здесь оставлен
    # отдельным вариантом "auto+gate", чтобы этот эффект был виден в отчёте.
    "methods": [
        ("manual", {"mode": "manual", "threshold_deriv": 0.5, "mad_k": 9.5,
                    "z_threshold": 3.5}),
        ("mad", {"mode": "auto", "auto": {"method": "mad"}}),
        ("iqr", {"mode": "auto", "auto": {"method": "iqr"}}),
        ("gmm", {"mode": "auto", "auto": {"method": "gmm"}}),
        ("hampel", {"mode": "auto", "auto": {"method": "hampel"}}),
        ("hampel-wide", {"mode": "auto", "auto": {"method": "hampel",
                                                  "hampel_window": 51,
                                                  "hampel_scale": "global"}}),
        ("auto+gate", {"mode": "auto", "auto": {"method": "iqr",
                                                "deriv_gate": True}}),
        ("iqr-tuned", None),   # порог подбирается tune() по сеточной RMSE
    ],

    # --- автоподбор порога (tune) ---
    "tuned": {
        "method": "iqr",
        "kwargs": {},
        "candidates": [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0],
    },

    # --- окно ямы для диагностики «потерянных настоящих точек» ---
    "pit_window_deg": 12.0,

    # --- чувствительность к окну фильтра Хампеля ---
    "hampel_window_sweep": [3, 5, 7, 11, 21, 51],

    # --- отрисовка ---
    "zoom": {"section": 0, "half_width_deg": 25.0},
    "out_png": "cleaner_auto_report.png",
    "dpi": 120,
}

def ring_interp(angles, values, xq):
    """Интерполяция периодического профиля (кольцо 0..360) в точки xq."""
    angles = np.asarray(angles, dtype=float)
    values = np.asarray(values, dtype=float)
    order = np.argsort(angles)
    a = angles[order]
    v = values[order]
    a_ext = np.concatenate([a - 360.0, a, a + 360.0])
    v_ext = np.concatenate([v, v, v])
    return np.interp(np.asarray(xq, dtype=float), a_ext, v_ext)

def load_sections(csv_path, ideal_column, truth_column):
    """Читает CSV и раскладывает по сечениям (сортировка по углу)."""
    data = pd.read_csv(csv_path)
    has_truth = truth_column in data.columns
    sections = {}
    for sid in sorted(data["section_id"].unique()):
        sec = data[data["section_id"] == sid].sort_values("angle_deg")
        sections[sid] = {
            "angles": sec["angle_deg"].values,
            "radii": sec["radius_mm"].values,
            "ideal": sec[ideal_column].values,
            "truth": sec[truth_column].values.astype(bool) if has_truth else None,
            "height_mm": float(sec["height_mm"].iloc[0]),
        }
    return sections, has_truth

def main():
    cfg = CONFIG
    csv_path = resolve_path(cfg["csv"])
    sections, has_truth = load_sections(csv_path, cfg["ideal_column"],
                                        cfg["truth_column"])
    grid = np.linspace(0.0, 360.0, int(cfg["grid_points"]), endpoint=False)

    print("=" * 78)
    print("ОЧИСТКА ВЫБРОСОВ: РУЧНЫЕ ПОРОГИ vs АВТОПОДБОР")
    print("=" * 78)
    print(f"Файл:   {csv_path}")
    print(f"Сечений: {len(cfg['sections'])}, точек в сечении: "
          f"{len(sections[cfg['sections'][0]]['angles'])}")
    print(f"Ручные пороги (пайплайн): {cfg['manual']}")
    if not has_truth:
        print("ВНИМАНИЕ: колонки истины нет — precision/recall/F1 недоступны")

    all_results = {}
    zoom_results = {}
    zoom_ctx = None
    for sid in cfg["sections"]:
        sec = sections[sid]
        ctx = make_ctx(sec, grid, cfg)
        results = {"raw": evaluate_method("raw", sec, ctx, cfg["tuned"], cfg["model"])}
        for name, mcfg in cfg["methods"]:
            results[name] = evaluate_method(mcfg, sec, ctx, cfg["tuned"], cfg["model"])
        all_results[sid] = results
        print_section_report(sid, sec, results)
        if sid == cfg["zoom"]["section"]:
            zoom_results = results
            zoom_ctx = ctx

    print_summary(all_results)

    # --- протокол автоподбора порога ---
    tuned_rows = zoom_results.get("iqr-tuned", {}).get("tuned_rows")
    if tuned_rows:
        print(f"\n=== АВТОПОДБОР ПОРОКА (iqr_k, сечение {cfg['zoom']['section']}, "
              "критерий — сеточная RMSE) ===")
        print(f"  {'k':>6}{'оставлено':>12}{'сеточная RMSE, мм':>20}")
        for row in tuned_rows:
            score = "-" if row["score"] is None else f"{row['score']:.5f}"
            mark = "  <-- выбрано" if row.get("best") else ""
            print(f"  {row['threshold']:>6.2f}{row['n_kept']:>12}{score:>20}{mark}")

    # --- чувствительность к окну ---
    window_rows = hampel_window_sweep(cfg, sections, grid)
    print("\n=== ЧУВСТВИТЕЛЬНОСТЬ К ОКНУ ФИЛЬТРА ХАМПЕЛЯ (авторежим) ===")
    print(f"  {'окно, точек':>12}{'F1 (в окне)':>13}{'F1 (общий)':>12}"
          f"{'RMSE к эталону':>18}")
    for row in window_rows:
        print(f"  {row['window']:>12}{row['f1_local']:>13.3f}"
              f"{row['f1_global']:>12.3f}{row['rmse_global']:>18.5f}")

    print("\n=== ВЫВОД ===")
    for name, _ in cfg["methods"]:
        f1 = mean_or_none([all_results[sid][name]["f1"] for sid in all_results])
        rm = mean_or_none([all_results[sid][name]["rmse_ideal"] for sid in all_results])
        print(f"  {name:<20} F1={fmt(f1)}  RMSE к эталону={fmt(rm, '.5f')}")
    raw_rm = mean_or_none([all_results[sid]["raw"]["rmse_ideal"] for sid in all_results])
    print(f"  {'raw (без очистки)':<20} F1=-        RMSE к эталону={fmt(raw_rm, '.5f')}")

    # --- рекомендация для пайплайна ---
    auto_names = [name for name, mcfg in cfg["methods"]
                  if isinstance(mcfg, dict) and mcfg.get("mode") == "auto"]
    scores = [(name, mean_or_none([all_results[sid][name]["f1"] for sid in all_results]))
              for name in auto_names]
    scores = [(n, s) for n, s in scores if s is not None]
    if scores:
        best_name, best_f1 = max(scores, key=lambda item: item[1])
        best_cfg = dict(next(mcfg for name, mcfg in cfg["methods"]
                             if name == best_name)["auto"])
        print(f"\n=== РЕКОМЕНДАЦИЯ ДЛЯ CONFIG['cleaner'] ===")
        print(f"  лучший авто-метод по F1: {best_name} (F1={best_f1:.3f}); "
              f"режим manual: F1="
              f"{fmt(mean_or_none([all_results[sid]['manual']['f1'] for sid in all_results]))}")
        print(f"  \"cleaner\": {{\"mode\": \"auto\", \"auto\": {best_cfg!r}}}")

    out_png = resolve_path(cfg["out_png"])
    plot_cleaner_report(cfg, sections, zoom_ctx, zoom_results, all_results, window_rows,
                out_png)
    print(f"\nГрафик: {out_png}")

if __name__ == "__main__":
    main()
