# вырезано из _src_pit_feature.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.patch_approximator import PatchApproximator
from ..analysis.layout import section_crack_zones
from ..io.dataset import attach_ideal_grid, load_sections, ring_interp
from ..paths import resolve_path
from ..viz.pit_figs import VARIANTS

def report_config(cfg, sections, zones_by_section):
    print("=" * 100)
    print("ФИЧЕР ЯМЫ: гауссовы члены в базисе патча + СШИВКА с полиномом")
    print("=" * 100)
    print(f"Одна звезда на все сечения: N = {cfg['n_patches']}, "
          f"phase_deg = {cfg['phase_deg']:g}° (сектор "
          f"{360.0 / cfg['n_patches']:.2f}°)")
    print(f"Оконный гаусс: sigma = {cfg['sigma_deg']:g}°, вес 1 до "
          f"|d| <= {cfg['pit_core_sigma']:g}·sigma = "
          f"{cfg['pit_core_sigma'] * cfg['sigma_deg']:.2f}°, плавный уход в 0 "
          f"к |d| = {cfg['pit_window_sigma']:g}·sigma = "
          f"{cfg['pit_window_sigma'] * cfg['sigma_deg']:.2f}° "
          "(smoothstep с нулевой производной на краях)")
    print("\nЯмы по сечениям (центр зоны-трещины из детектора и её ширина, °):")
    for sid in cfg["sections"]:
        zz = zones_by_section[sid]
        print(f"  сечение {sid:>2} (h={sections[sid]['height_mm']:>5.0f} мм): "
              + (", ".join(f"{0.5 * (a + b):.2f}° (ширина {b - a:.1f}°)"
                           for a, b in zz) or "нет"))


def report_metrics(cfg, rows):
    print("\nМетрики по сечениям (RMSE по сетке против эталона, мм):")
    print(f"  {'сечение':>7} " + " ".join(f"{k:>9}" for k, _ in VARIANTS)
          + f" {'у ям A':>8} {'у ям B':>8} {'у ям C':>8}")
    for sid in cfg["sections"]:
        r = rows[sid]
        print(f"  {sid:>7} "
              + " ".join(f"{r[v]['rmse']:>9.4f}" for v, _ in VARIANTS)
              + "".join(f" {r[v]['peak_at_pit']:>8.4f}" for v, _ in VARIANTS))
    same = all(rows[s]["pit_raw"]["degrees"] == rows[s]["poly"]["degrees"]
               and rows[s]["pit_win"]["degrees"] == rows[s]["poly"]["degrees"]
               for s in cfg["sections"])
    print("Сверка: степени у A, B и C обязаны совпадать (отличается только "
          "описание ямы) — " + ("ок" if same else "НЕ СОВПАЛИ (!)"))
    sid0 = cfg["sections"][0]
    print(f"  степени (сечение {sid0}): {rows[sid0]['poly']['degrees']}")


def report_crops(cfg, crops):
    """Числовая проверка СШИВКИ: где фичер кончается и что он делает на швах."""
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]
    print(f"\nКрупные планы ям: кроп ±{win + cfg['crop_margin_deg']:.1f}° = окно "
          f"фичера ±{win:.1f}° + {cfg['crop_margin_deg']:g}° чистого полинома")
    print("  «дно» — остаток в центре ямы, мм; «хвост» — до какого |Δ| вклад ямы "
          "ещё > 1e-6 мм, °; «шов» — max |вклад ямы| в зоне перекрытия (шов "
          "±5°), мм: > 0 значит амплитуду ямы делят два патча; «до шва» — запас "
          "окна фичера до зоны перекрытия, ° (> 0 — окно внутри одного патча):")
    print(f"  {'сеч':>4} {'центр,°':>8} {'шир.,°':>7} {'глуб.,мм':>9} "
          f"{'дно A':>8} {'дно B':>8} {'дно C':>8} "
          f"{'хвост B':>8} {'хвост C':>8} {'шов B':>8} {'шов C':>8} {'до шва':>8}")
    for sid in cfg["sections"]:
        for it in crops[sid]:
            print(f"  {sid:>4} {it['angle']:>8.2f} {it['width']:>7.1f} "
                  f"{it['depth']:>9.2f} {it['resid_center']['poly']:>8.3f} "
                  f"{it['resid_center']['pit_raw']:>8.3f} "
                  f"{it['resid_center']['pit_win']:>8.3f} "
                  f"{it['span']['pit_raw']:>8.1f} {it['span']['pit_win']:>8.1f} "
                  f"{it['seam_pit']['pit_raw']:>8.4f} "
                  f"{it['seam_pit']['pit_win']:>8.4f} {it['seam_gap']:>8.1f}")
