# вырезано из _src_star_layout.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.outlier_cleaner import build_cleaner
from ..core.patch_approximator import PatchApproximator
from ..analysis.zones import crack_depths_mm, detect_zones, indicator_curve, load_crack_table, mask_to_zones, truth_zone_mask

def report_overlay(curves, cfg):
    """Таблица «N -> его оптимальная фаза, отступ, RMSE по сечениям» + сверка."""
    secs = cfg["sections"]
    print("Каждый N — при СВОЕЙ оптимальной фазе (сначала безопасность, затем "
          "RMSE среди безопасных фаз).")
    print("Отступ < 0 — у этого N НЕТ фазы без узла в запретной зоне: кривая "
          "показана для сравнения")
    print("и на рисунке полупрозрачная.")
    head = (f"{'N':>3} {'фаза,°':>7} {'отступ,°':>9} {'узлов в зоне':>13} ")
    head += " ".join(f"{'RMSE с' + str(sid):>9}" for sid in secs)
    print(head + f" {'средняя':>9} {'ок':>4}")
    for c in curves:
        line = (f"{c['n_patches']:>3} {c['phase']:>7.2f} {c['min_margin']:>+9.2f} "
                f"{c['nodes_in_zone']:>13} ")
        line += " ".join(f"{c['rmse_by_section'][sid]:>9.4f}" for sid in secs)
        print(line + f" {c['rmse_mean']:>9.4f} "
              f"{('да' if c['safe'] else 'НЕТ'):>4}")

    worst = max(abs(c["rmse_mean"] - c["row_rmse"]) for c in curves)
    print(f"Сверка с таблицей перебора: макс. расхождение средней RMSE "
          f"{worst:.2e} мм (должно быть ~0 — тот же расчёт и та же сетка).")
    safe = ", ".join(f"N={c['n_patches']}" for c in curves if c["safe"]) or "нет"
    bad = ", ".join(f"N={c['n_patches']}" for c in curves if not c["safe"]) or "нет"
    print(f"На рисунке: безопасные раскладки — {safe}; без безопасной фазы — {bad}")


def report_rows(rows, guard_deg, phase_step_deg=0.25):
    """Таблица «N -> фаза, отступ, узлов в зоне, RMSE, безопасных фаз»."""
    print(f"Запас безопасности узла (guard): {guard_deg:g}°; "
          f"отступ > 0 — узел стоит в гладкой зоне с запасом")
    print(f"Фаза перебрана с шагом {phase_step_deg:g}° внутри сектора 360/N "
          f"(по безопасности), затем уточнена по RMSE (rmse_phase_step_deg).")
    print(f"{'N':>3} {'фаз,°':>7} {'отступ,°':>9} {'макс.отступ,°':>14} "
          f"{'сред.отступ,°':>14} {'узлов в зоне':>13} {'безопасных фаз':>15} "
          f"{'RMSE, мм':>9} {'ок':>4}")
    for r in rows:
        rmse = r.get("rmse")
        print(f"{r['n_patches']:>3} {r['phase']:>7.2f} {r['min_margin']:>9.2f} "
              f"{r['max_margin']:>14.2f} "
              f"{r['mean_margin']:>14.2f} {r['nodes_in_zone']:>13} "
              f"{r['safe_phases']:>15} "
              f"{(f'{rmse:.4f}' if rmse is not None else '—'):>9} "
              f"{('да' if r['min_margin'] >= 0 else 'НЕТ'):>4}")
    print("Столбцы «отступ» и «сред.отступ» — на выбранной (по RMSE) фазе, "
          "«макс.отступ» — лучшая фаза по безопасности.")


def report_chosen(chosen, flex_info, zones_by_section):
    """Итог: выбранная раскладка, отступы по сечениям и гибкие узлы."""
    print(f"\nВЫБРАННАЯ РАСКЛАДКА: N = {chosen['n_patches']}, "
          f"phase_deg = {chosen['phase']:g}° "
          f"(сектор {360.0 / chosen['n_patches']:.2f}°)")
    print(f"  мин. отступ узла: {chosen['min_margin']:+.2f}°, "
          f"узлов в запретной зоне: {chosen['nodes_in_zone']}, "
          f"RMSE {chosen['rmse']:.4f} мм")
    print("  отступ по сечениям отдельно (мин. по узлам):")
    for sid, m in chosen["per_section"].items():
        zones = len(zones_by_section[sid])
        print(f"    сечение {sid:>2}: {m:>+6.2f}°, зон-трещин {zones}, "
              f"{'ок' if m >= 0 else 'узел у трещины'}")
    print(f"  предложение в конфиг пайплайна: "
          f"{{\"n_patches\": {chosen['n_patches']}, "
          f"\"phase_deg\": {chosen['phase']:g}}}")

    print(f"\nГИБКИЕ УЗЛЫ (flex ±{flex_info['flex_deg']:g}°): "
          f"мин. отступ {flex_info['history'][0]:+.2f}° -> "
          f"{flex_info['min_margin']:+.2f}°, сдвиг узлов до "
          f"{flex_info['cost_deg']:.2f}°")
    print("  узлы: " + ", ".join(f"{nd:.1f}°" for nd in flex_info["nodes"]))
    print("  ВНИМАНИЕ: RMSE для гибкой раскладки не измерялся — "
          "PatchApproximator строит равномерную сетку (+phase_deg), поэтому "
          "flex — рекомендация для\n  неоднородной раскладки, а не режим "
          "модели. Симметричная раскладка + phase_deg работает уже сейчас.")
