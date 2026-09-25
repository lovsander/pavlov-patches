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

VARIANTS = [("poly", "A) полином (текущая модель)"),
            ("pit_raw", "B) + гаусс без окна (как было)"),
            ("pit_win", "C) + ОКОННЫЙ гаусс (сшивка с полиномом)")]


STYLE = {
    "poly": {"color": "#0072B2", "ls": (0, (6, 2)), "lw": 1.4,
             "label": "A) полином (текущая модель)"},
    "pit_raw": {"color": "#009E73", "ls": (0, (3, 1.2)), "lw": 1.3,
                "label": "B) гаусс без окна (как было)"},
    "pit_win": {"color": "#D55E00", "ls": "-", "lw": 1.7,
                "label": "C) оконный гаусс (сшивка с полиномом)"},
    "zone_alpha": 0.16,
    "window_alpha": 0.12,
    "data": {"color": "gray", "ms": 2.2, "alpha": 0.40,
             "label": "данные (очищенные)"},
    "ideal": {"color": "black", "ls": "-", "lw": 1.0, "alpha": 0.85,
              "label": "эталон"},
}


def draw_window(ax, win_deg):
    """
    Окно фичера: серая полоса + штриховые вертикали «здесь яма выходит в
    полином». За вертикалями модель обязана быть чистым полиномом.
    """
    ax.axvspan(-win_deg, win_deg, color="0.35", alpha=STYLE["window_alpha"],
               lw=0.0, zorder=0)
    for x in (-win_deg, win_deg):
        ax.axvline(x, color="0.35", lw=0.9, ls=(0, (5, 3)), zorder=1)


def plot_pit_crops(cfg, sections, zones_by_section, crops, nodes_by_section,
                   out_path):
    """
    ТОЛЬКО крупные планы участков ям: строки — сечения, столбцы — ямы этого
    сечения. Рисуется РАДИУС (мм): ТОЧКИ данных, эталон и три модели (A/B/C) —
    «ямы на точках», как просил пользователь. Масштаб по вертикали берётся по
    кропу (яма ~0.6-1.3 мм), поэтому он же и есть крупный план глубины.

    Серая полоса — окно фичера, штриховые вертикали — его края (за ними модель
    обязана быть чистым полиномом), серые пунктирные вертикали — швы патчей
    (там blend двух полигонов), красная полоса — зона-трещина из детектора.

    Панелей «RMSE», «степени», «коэффициенты» здесь НЕТ: по просьбе рисуются
    только кропы.
    """
    secs = cfg["sections"]
    ncol = max(len(crops[sid]) for sid in secs)
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]

    fig, axes = plt.subplots(len(secs), ncol,
                             figsize=(6.4 * ncol, 3.1 * len(secs)), squeeze=False)
    for i, sid in enumerate(secs):
        s = sections[sid]
        items = crops[sid]
        for j in range(ncol):
            ax = axes[i][j]
            if j >= len(items):
                ax.axis("off")
                continue
            it = items[j]
            loc = it["loc"]
            half = it["crop_half"]

            for a, b in zones_by_section[sid]:      # зона-трещина в углах кропа
                ca = ((a - it["angle"] + 180.0) % 360.0) - 180.0
                cb = ((b - it["angle"] + 180.0) % 360.0) - 180.0
                if cb < ca or cb < -half or ca > half:
                    continue
                ax.axvspan(max(ca, -half), min(cb, half), color="tab:red",
                           alpha=STYLE["zone_alpha"], lw=0.0, zorder=0)
            draw_window(ax, win)
            for nd in nodes_by_section[sid]:        # швы патчей внутри кропа
                dn = ((nd - it["angle"] + 180.0) % 360.0) - 180.0
                if -half <= dn <= half:
                    ax.axvline(dn, color="0.45", lw=0.8, ls=(0, (1.5, 2.5)),
                               zorder=1)

            # точки данных (очищенные) внутри кропа — «яма на точках»
            d_all = np.abs((s["angles_clean"] - it["angle"] + 180.0)
                           % 360.0 - 180.0)
            near = d_all <= half
            ax.plot(s["angles_clean"][near] - it["angle"], s["radii_clean"][near],
                    ".", color=STYLE["data"]["color"],
                    markersize=STYLE["data"]["ms"], alpha=STYLE["data"]["alpha"],
                    label=STYLE["data"]["label"], zorder=2)
            ax.plot(loc, it["ideal"], ls=STYLE["ideal"]["ls"],
                    color=STYLE["ideal"]["color"], lw=STYLE["ideal"]["lw"],
                    alpha=STYLE["ideal"]["alpha"], label=STYLE["ideal"]["label"],
                    zorder=3)
            for v, _ in VARIANTS:
                st = STYLE[v]
                ax.plot(loc, it["curves"][v], ls=st["ls"], color=st["color"],
                        lw=st["lw"], label=st["label"], zorder=4)

            ax.set_xlim(-half, half)
            ax.grid(alpha=0.3)
            ax.set_title(
                f"сечение {sid} (h = {s['height_mm']:.0f} мм): яма "
                f"{it['angle']:.1f}°, зона {it['width']:.1f}°, глубина "
                f"~{it['depth']:.2f} мм\n"
                f"остаток на дне: A {it['resid_center']['poly']:+.3f}, "
                f"B {it['resid_center']['pit_raw']:+.3f}, "
                f"C {it['resid_center']['pit_win']:+.3f} мм | хвост ямы: "
                f"B до {it['span']['pit_raw']:.0f}°, C до "
                f"{it['span']['pit_win']:.0f}°", fontsize=9)
            if i == len(secs) - 1:
                ax.set_xlabel("Угол к центру ямы, °")
            if j == 0:
                ax.set_ylabel("Радиус, мм")
            if i == 0 and j == 0:
                handles, _ = ax.get_legend_handles_labels()
                handles.append(plt.Rectangle((0, 0), 1, 1, color="tab:red",
                                             alpha=STYLE["zone_alpha"] + 0.15,
                                             label="зона-трещина (детектор)"))
                handles.append(plt.Line2D([], [], color="0.45", lw=0.8,
                                          ls=(0, (1.5, 2.5)),
                                          label="шов патчей (blend полигонов)"))
                ax.legend(handles=handles, fontsize=7, loc="best", framealpha=0.9)

    fig.suptitle(
        "Фичер ямы: крупные планы участков ям на точках (радиус)\n"
        f"Одна звезда на все сечения: N = {cfg['n_patches']}, "
        f"phase_deg = {cfg['phase_deg']:g}°, sigma = {cfg['sigma_deg']:g}° "
        f"(вес 1 до ±{cfg['pit_core_sigma'] * cfg['sigma_deg']:.1f}°, плавный "
        f"уход в 0 к ±{win:.1f}°)\n"
        "серая полоса — окно фичера, за штриховыми вертикалями модель обязана "
        "быть чистым полиномом", fontsize=11.5)
    plt.tight_layout(rect=(0, 0, 1, 0.92))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)
