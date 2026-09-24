# вырезано из compare_cleaner_auto_src.py (рефакторинг, см. CONTEXT.md §21)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from ..core.outlier_cleaner import AutoOutlierCleaner, build_cleaner
from ..core.patch_approximator import PatchApproximator
from ..analysis.cleaner_study import describe_params, fmt, mean_or_none

def print_section_report(sid, sec, results):
    """Таблица по одному сечению."""
    n_truth = int(sec["truth"].sum()) if sec["truth"] is not None else 0
    print(f"\nСечение {sid} (h={sec['height_mm']:.0f} мм, точек {len(sec['angles'])}, "
          f"истинных выбросов {n_truth}):")
    print(f"  {'метод':<14}{'отбр.':>7}{'TP':>6}{'FP':>5}{'FN':>5}"
          f"{'P':>8}{'R':>8}{'F1':>8}{'потеряно':>10}{'RMSE_эт':>10}{'RMSE_сыр':>10}")
    for name, res in results.items():
        print(f"  {name:<14}{res['n_out']:>7}{fmt(res['tp'], 'd'):>6}"
              f"{fmt(res['fp'], 'd'):>5}{fmt(res['fn'], 'd'):>5}"
              f"{fmt(res['precision']):>8}{fmt(res['recall']):>8}{fmt(res['f1']):>8}"
              f"{res['lost_near_pit']:>10}{res['rmse_ideal']:>10.5f}"
              f"{res['rmse_raw']:>10.5f}")
    for name, res in results.items():
        if res["params"]:
            print(f"    {name:<12} автопороги: {describe_params(res['params'])}")


def print_summary(all_results):
    """Средние по всем сечениям."""
    names = list(next(iter(all_results.values())).keys())
    print("\n" + "=" * 78)
    print("ИТОГО (средние по сечениям)")
    print("=" * 78)
    print(f"  {'метод':<14}{'отбр.%':>8}{'P':>8}{'R':>8}{'F1':>8}"
          f"{'потеряно':>10}{'RMSE_эт':>10}{'RMSE_сыр':>10}")
    for name in names:
        per = [all_results[sid][name] for sid in all_results]
        print(f"  {name:<14}"
              f"{np.mean([p['percent_out'] for p in per]):>8.2f}"
              f"{fmt(mean_or_none([p['precision'] for p in per])):>8}"
              f"{fmt(mean_or_none([p['recall'] for p in per])):>8}"
              f"{fmt(mean_or_none([p['f1'] for p in per])):>8}"
              f"{np.mean([p['lost_near_pit'] for p in per]):>10.1f}"
              f"{np.mean([p['rmse_ideal'] for p in per]):>10.5f}"
              f"{np.mean([p['rmse_raw'] for p in per]):>10.5f}")
