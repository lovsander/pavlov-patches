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
from ..analysis.layout import fit_layout, layout_margins, sector_rmse, zone_mask_on_grid
from ..io.dataset import ring_interp
from .star import STAR_INNER_R, STAR_TOP_R, draw_star, draw_zone_wedges

FIT_STYLES = {
    3:  ("#0072B2", (0, (6, 2))),              # синий, длинный штрих
    4:  ("#E69F00", (0, (2, 1.5))),            # оранжевый, короткий штрих
    5:  ("#56B4E9", (0, (1, 1.5))),            # небесно-голубой, точка
    6:  ("#D55E00", (0, (6, 2))),              # оранжево-красный, длинный штрих
    7:  ("#0072B2", (0, (2, 1.5))),            # синий, короткий штрих
    8:  ("#009E73", (0, (1, 1.5))),            # зелёный, точка
    9:  ("#7B3294", (0, (5, 1.2, 1, 1.2))),    # фиолетовый, штрих-пунктир
    10: ("#A6761D", (0, (2, 1, 2, 1, 2, 4))),  # тёмно-золотой, тройной штрих
    11: ("#000000", (0, (9, 2, 2, 2, 2, 2))),  # чёрный, двойной штрих-точка
    12: ("#7570B3", (0, (4, 1, 1, 1))),        # фиолетово-синий, штрих + точки
}


def fit_style(n_patches):
    """Цвет и узор пунктира для N (для N вне таблицы — серый штрих-пунктир)."""
    return FIT_STYLES.get(int(n_patches), ("0.4", (0, (4, 2, 1, 2))))


def fit_curves_at_phase(cfg, sections, grid, n_patches, phase_deg):
    """
    Кривые ВСЕХ сечений для одного N при одной фазе + RMSE по сетке.

    Расчёт ровно тот же, что в layout_rmse (та же сетка, тот же эталон),
    только кривые сохраняются — рисунок обязан показывать те же числа, что
    в таблице перебора. Совпадение проверяет report_overlay.
    """
    out = {}
    for sid in cfg["sections"]:
        s = sections[sid]
        _, y = fit_layout(s, grid, cfg["model"], n_patches, phase_deg)
        out[sid] = {"fitted": y,
                    "rmse": float(np.sqrt(np.mean((y - s["ideal_grid"]) ** 2)))}
    return out


def overlay_curves(cfg, sections, grid, rows):
    """
    Кривые всех N из cfg["fits_n_patches"], каждый — при СВОЕЙ фазе из rows.

    N без безопасной фазы тоже рисуется (иначе сравнение было бы подыграно
    «удобным» N), но помечается небезопасным и идёт полупрозрачным.
    """
    curves = []
    for row in rows:
        n = int(row["n_patches"])
        if n not in cfg["fits_n_patches"]:
            continue
        fits = fit_curves_at_phase(cfg, sections, grid, n, row["phase"])
        color, ls = fit_style(n)
        curves.append({
            "n_patches": n,
            "phase": float(row["phase"]),
            "min_margin": float(row["min_margin"]),
            "nodes_in_zone": int(row["nodes_in_zone"]),
            "safe": bool(row["min_margin"] >= 0.0),
            "row_rmse": float(row["rmse"]),
            "rmse_by_section": {sid: fits[sid]["rmse"] for sid in cfg["sections"]},
            "rmse_mean": float(np.mean([fits[sid]["rmse"]
                                        for sid in cfg["sections"]])),
            "fits": fits,
            "color": color,
            "linestyle": ls,
        })
    return curves


def overlay_legend(cfg, curves):
    """
    Handles легенды: эталон, запретные зоны и все N (N, его фаза и его RMSE).

    Легенда собирается вручную, потому что фон зон — это axvspan без подписи,
    а кривые рисуются без label (иначе 12 подписей в каждой из 4 панелей).
    """
    st = cfg["style"]
    handles = [
        plt.Line2D([], [], color="black", lw=st["ideal_lw"], alpha=0.7,
                   label="эталон"),
        plt.Line2D([], [], color="tab:red", lw=6.0, alpha=st["zone_alpha"] + 0.1,
                   label="запретные зоны (объединение)"),
    ]
    for c in curves:
        handles.append(plt.Line2D(
            [], [], color=c["color"], ls=c["linestyle"], lw=st["variant_lw"],
            alpha=st["safe_alpha"] if c["safe"] else st["unsafe_alpha"],
            label=f"N={c['n_patches']} — фаза {c['phase']:g}°, "
                  f"RMSE {c['rmse_mean']:.4f}"
                  + ("" if c["safe"] else " — НЕТ безопасной фазы")))
    return handles


def draw_zone_background(ax, cfg, union):
    """Фон запретных зон (объединение по всем сечениям) — без подписи."""
    for z in union:
        ax.axvspan(z[0], z[1], color="tab:red", alpha=cfg["style"]["zone_alpha"],
                   lw=0.0, zorder=0)


def plot_layout_fits(cfg, sections, grid, union, curves, out_path):
    """
    4 сечения: N из cfg["fits_n_patches"] (по умолчанию 6..9) наложены,
    каждый — при своей оптимальной фазе.

    Это «глазами по профилю» то же, что таблица перебора: видно, куда именно
    каждый N укладывает ямы (у N=6..7 окна шире, и глубокая яма попадает не на
    узел, а на середину патча). Заголовок — одна строка: всё остальное (фаза и
    RMSE каждого N) уже есть в легенде, а панели должны быть крупными.
    """
    st = cfg["style"]
    secs = cfg["sections"]
    n_cols = 2
    n_rows = int(np.ceil(len(secs) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16.5, 10.5))
    axes = np.atleast_1d(axes).ravel()
    handles = overlay_legend(cfg, curves)

    for ax, sid in zip(axes, secs):
        s = sections[sid]
        draw_zone_background(ax, cfg, union)
        ax.plot(s["angles"], s["radii"], ".", color="gray",
                markersize=st["data_ms"], alpha=st["data_alpha"])
        ax.plot(s["angles"], s["ideal"], "-", color="black", lw=st["ideal_lw"],
                alpha=0.6)
        for c in curves:
            ax.plot(grid, c["fits"][sid]["fitted"], color=c["color"],
                    ls=c["linestyle"], lw=st["variant_lw"],
                    alpha=st["safe_alpha"] if c["safe"] else st["unsafe_alpha"])
        ax.set_title(f"Сечение {sid}, h={s['height_mm']:.0f} мм | "
                     f"чистых {len(s['angles_clean'])}/{len(s['angles'])}",
                     fontsize=10)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.set_xlim(0, 360)
        ax.grid(True, alpha=0.3)
        ax.legend(handles=handles, fontsize=6.5, loc="upper right", ncol=2,
                  framealpha=0.85, borderpad=0.3, columnspacing=0.8,
                  handlelength=2.4)

    for ax in axes[len(secs):]:
        ax.axis("off")

    fig.suptitle(
        "Наложение N = " + ", ".join(str(c["n_patches"]) for c in curves) +
        " на 4 сечения — каждый N при СВОЕЙ оптимальной фазе\n"
        "(сначала безопасность узлов, затем RMSE; фаза и RMSE — в легенде)",
        fontsize=12.5, y=0.985)
    plt.tight_layout(rect=(0, 0, 1, 0.945))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def local_offset_deg(angles, center_deg):
    """Угол относительно центра патча, ° (в диапазоне ±180): режет 0/360."""
    return np.mod(np.asarray(angles, dtype=float) - center_deg + 180.0, 360.0) - 180.0


def zone_fill_local(ax, cfg, center_deg, union, y_lo, y_hi, half_deg):
    """
    Запретные зоны в ЛОКАЛЬНЫХ координатах патча.

    axvspan тут не годится: зона, заворачивающаяся через 0°, распалась бы на
    два куска. Считаем маску на локальной сетке и заливаем fill_between.
    """
    dx = np.linspace(-half_deg, half_deg, 1201)
    glob = np.mod(center_deg + dx, 360.0)
    mask = zone_mask_on_grid(glob, union)
    if mask.any():
        ax.fill_between(dx, y_lo, y_hi, where=mask, facecolor="tab:red",
                        alpha=cfg["style"]["zone_alpha"], lw=0.0, zorder=0)


def plot_patches(cfg, sections, grid, union, chosen, ap, curves, out_path):
    """
    Обучение патчей выбранной раскладки: панель = патч (как в архивном
    final_step2_training.png, deprecated/scripts/patches_about*.py).

    На панели: все измерения сечения (серый фон), точки, попавшие в обучение
    этого патча (цвет раскладки), полином патча (deg), границы обучения
    (серый пунктир, half_train) и границы blend (зелёный, half_use), фон
    запретных зон и вертикали узлов с их отступом. По горизонтали — угол
    ОТНОСИТЕЛЬНО центра патча, поэтому окно каждого патча показано крупно.

    Последняя панель — «проблемное место»: самый тесный узел среди всех
    сравниваемых N (cfg["fits_n_patches"]) в окне ±issue_half_deg, с кривыми
    всех N и пиковой невязкой рядом с узлом.

    Возвращает словарь с параметрами этой панели (сечение, N, угол узла,
    отступ, пиковые |Δr| по N) — чтобы те же числа можно было напечатать в
    консоль: рисунок и текст не должны расходиться.
    """
    st = cfg["style"]
    sid0 = cfg["sections"][0]
    s = sections[sid0]
    n = int(chosen["n_patches"])
    phase = float(chosen["phase"])
    color, _ = fit_style(n)
    nodes, margins = layout_margins(n, phase, union, cfg["guard_deg"])

    y_lo, y_hi = np.percentile(s["radii"], [1.0, 99.0])
    y_lo, y_hi = float(y_lo) - 0.5, float(y_hi) + 0.5

    n_cols = 4
    n_panels = n + 1                      # патчи + «проблемный узел»
    n_rows = int(np.ceil(n_panels / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4.8 * n_cols, 4.4 * n_rows))
    axes = np.atleast_1d(axes).ravel()

    # --- панели патчей ---
    for j, p in enumerate(ap.patches_):
        ax = axes[j]
        half = p["half_train"] + st["window_pad_deg"]
        dx_data = local_offset_deg(s["angles"], p["center"])

        zone_fill_local(ax, cfg, p["center"], union, y_lo, y_hi, half)
        ax.axvspan(-p["half_sector"], p["half_sector"], color=color,
                   alpha=st["patch_col_alpha"], lw=0.0, zorder=0)
        ax.plot(dx_data, s["radii"], ".", color="0.55",
                markersize=st["data_ms"], alpha=st["data_alpha"], zorder=1)
        ax.plot(dx_data, s["ideal"], "-", color="black",
                lw=st["ideal_lw"], alpha=0.45, zorder=2)

        mask = np.abs(dx_data) <= p["half_train"]
        ax.scatter(dx_data[mask], s["radii"][mask], s=st["train_ms"],
                   color=color, alpha=0.55, zorder=3,
                   label=f"обучающие точки ({int(mask.sum())})")

        dxp = np.linspace(-p["half_train"], p["half_train"], 400)
        # коэффициенты хранятся в каноне: x ∈ [-1,1] (coord_mode="normalized")
        ax.plot(dxp, np.polyval(p["coefs"], dxp / p["half_train"]), "-",
                color=color, lw=2.2,
                label=f"полином deg={p['degree']}", zorder=4)

        for b in (-1.0, 1.0):
            ax.axvline(b * p["half_train"], color="0.4", ls=":", lw=0.9)
            ax.axvline(b * p["half_use"], color="#009E73", ls="--", lw=1.1,
                       alpha=0.8)

        for nd, m in zip(nodes, margins):            # узлы (швы) в окне патча
            nd_dx = float(local_offset_deg(nd, p["center"]))
            if abs(nd_dx) > half:
                continue
            ax.axvline(nd_dx, color="#009E73" if m >= 0 else "#D55E00",
                       lw=st["node_lw"], alpha=0.85)
            ax.text(nd_dx, y_hi, f"узел {m:+.1f}°", fontsize=6.5, rotation=90,
                    ha="right", va="top",
                    color="#00765a" if m >= 0 else "#a84600")

        ax.set_xlim(-half, half)
        ax.set_ylim(y_lo, y_hi)
        ax.set_title(f"Патч {j + 1}: центр {p['center']:.1f}°, "
                     f"deg={p['degree']}, точек={p['n_points']}", fontsize=9)
        ax.set_xlabel("угол относительно центра патча, °")
        ax.set_ylabel("радиус, мм")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=6.5, loc="lower right", framealpha=0.85)

    # --- панель «проблемное место» среди всех сравниваемых N ---
    issue = min(curves, key=lambda c: c["min_margin"])
    n_w, phase_w = int(issue["n_patches"]), float(issue["phase"])
    nodes_w, margins_w = layout_margins(n_w, phase_w, union, cfg["guard_deg"])
    idx = int(np.argmin(margins_w))
    node_deg, node_margin = float(nodes_w[idx]), float(margins_w[idx])
    half = st["issue_half_deg"]

    ax = axes[n]
    zone_fill_local(ax, cfg, node_deg, union, y_lo, y_hi, half)
    dx_data = local_offset_deg(s["angles"], node_deg)
    ax.plot(dx_data, s["radii"], ".", color="0.55", markersize=st["data_ms"],
            alpha=st["data_alpha"], zorder=1)
    ax.plot(dx_data, s["ideal"], "-", color="black", lw=st["ideal_lw"],
            alpha=0.45, zorder=2)

    dx = np.linspace(-half, half, 801)
    glob = np.mod(node_deg + dx, 360.0)
    ideal_local = ring_interp(grid, s["ideal_grid"], glob)
    near = np.abs(dx) <= 5.0
    peaks = {}
    for c in curves:
        vals = ring_interp(grid, c["fits"][sid0]["fitted"], glob)
        peak = float(np.max(np.abs(vals[near] - ideal_local[near])))
        peaks[int(c["n_patches"])] = peak
        ax.plot(dx, vals, color=c["color"], ls=c["linestyle"],
                lw=st["variant_lw"],
                alpha=st["safe_alpha"] if c["safe"] else st["unsafe_alpha"],
                label=f"N={c['n_patches']} (отступ {c['min_margin']:+.1f}°, "
                      f"макс |Δr| ±5°: {peak:.4f} мм)")

    ax.axvline(0.0, color="#D55E00", lw=1.6, alpha=0.9)
    ax.text(0.0, y_hi, f"узел {node_deg:.1f}° / отступ {node_margin:+.2f}°",
            fontsize=7, ha="center", va="top", color="#a84600")
    ax.set_xlim(-half, half)
    ax.set_ylim(y_lo, y_hi)
    ax.set_title(f"Проблемное место: N={n_w}, узел {node_deg:.1f}° "
                 f"(отступ {node_margin:+.2f}°, узлов в зоне "
                 f"{issue['nodes_in_zone']})", fontsize=9)
    ax.set_xlabel("угол относительно узла, °")
    ax.set_ylabel("радиус, мм")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=6.5, loc="lower right", framealpha=0.85)

    for ax in axes[n_panels:]:
        ax.axis("off")

    fig.suptitle(
        f"Обучение {n} патчей выбранной раскладки (фаза {phase:g}°), "
        f"сечение {sid0} (h={s['height_mm']:.0f} мм): панель = патч; "
        "серый пунктир — граница обучения, зелёный — граница blend\n"
        "последняя панель — самый тесный узел среди N = "
        + ", ".join(str(c["n_patches"]) for c in curves),
        fontsize=12)
    plt.tight_layout(rect=(0, 0, 1, 0.945))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)

    return {"section": sid0, "n_patches": n_w, "node_deg": node_deg,
            "node_margin": node_margin,
            "nodes_in_zone": int(issue["nodes_in_zone"]),
            "peaks_mm": peaks, "half_deg": half}


def plot_variants(cfg, rows, union, out_path):
    """
    Звёзды N из cfg["star_n_patches"] (по умолчанию 6..9) при лучшей по
    безопасности фазе: где стоят узлы относительно трещин.

    2 звезды в ряд (а не 5): панели крупные, а «отсечённые» N<6 / N>9 не
    отвлекают от рабочего диапазона.
    """
    sel = [r for r in rows if int(r["n_patches"]) in cfg["star_n_patches"]]
    n_cols = 2
    n_rows = int(np.ceil(len(sel) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(7.6 * n_cols, 7.0 * n_rows),
                             subplot_kw={"projection": "polar"})
    axes = np.atleast_1d(axes).ravel()

    for ax, row in zip(axes, sel):
        n = row["n_patches"]
        nodes, margins = layout_margins(n, row["phase"], union, cfg["guard_deg"])

        draw_zone_wedges(ax, union, STAR_INNER_R, STAR_TOP_R - STAR_INNER_R)
        draw_star(ax, n, row["phase"])
        for nd, m in zip(nodes, margins):
            ok = m >= 0
            ax.plot([np.deg2rad(nd)], [STAR_INNER_R],
                    marker="o" if ok else "X", ms=6.5 if ok else 8,
                    mew=1.8, color="tab:green" if ok else "tab:red", zorder=6)

        ax.set_ylim(0, STAR_TOP_R)
        ax.set_yticks([])
        ax.set_xticks(np.deg2rad(np.arange(0, 360, 45)))
        ax.set_xticklabels([f"{d}°" for d in range(0, 360, 45)], fontsize=6)
        # подписи углов жмём к окружности, а заголовок — к своей звезде:
        # иначе нижняя подпись «270°» верхнего ряда садится на заголовок нижнего
        ax.tick_params(pad=0.5)
        ax.grid(alpha=0.25)
        rmse_txt = f", RMSE {row['rmse']:.3f} мм" if row.get("rmse") else ""
        ax.set_title(f"N = {n}, фаза {row['phase']:g}°\n"
                     f"мин. отступ {row['min_margin']:+.1f}°, "
                     f"узлов в зоне {row['nodes_in_zone']}{rmse_txt}", fontsize=8.5,
                     pad=3.0)

    for ax in axes[len(sel):]:
        ax.axis("off")

    fig.suptitle(
        "Раскладка патчей «звездой»: лучи — патчи, впадины — узлы (швы между патчами)\n"
        "Закрашены запретные зоны (трещины) — объединение по всем 10 сечениям: "
        "зелёный узел стоит в гладкой зоне, красный попал на трещину.\n"
        f"Показаны N = {', '.join(str(n) for n in cfg['star_n_patches'])} "
        "(фаза у каждого — по максимуму минимального отступа узла)",
        fontsize=11.5)
    # h_pad: между рядами полярных осей нужно больше воздуха, чем считает
    # tight_layout (он плохо учитывает подписи углов у polar-осей)
    plt.tight_layout(rect=(0, 0, 1, 0.90), h_pad=3.5)
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_layout_report(cfg, sections, table, union, rows, chosen, flex_info, out_path):
    """
    4 панели: выбранная звезда (лучи раскрашены по RMSE патча), развёртка по
    углу (трещины, узлы, гибкие узлы), отступ от фазы, сводка по N.
    """
    n_chosen = chosen["n_patches"]
    phase = chosen["phase"]
    sid0 = cfg["sections"][0]
    s = sections[sid0]
    det = cfg["detector"]
    fig = plt.figure(figsize=(17, 11.5))

    # --- (0,0) выбранная раскладка ---
    ax = fig.add_subplot(2, 2, 1, projection="polar")
    xs = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    ap, _ = fit_layout(s, xs, cfg["model"], n_chosen, phase)
    sec_rmse = sector_rmse(ap, xs, s["ideal_grid"], n_chosen, phase,
                           cfg["model"]["overlap_use"])
    cmap = plt.get_cmap("viridis")
    lo, hi = float(np.nanmin(sec_rmse)), float(np.nanmax(sec_rmse))
    span = (hi - lo) or 1.0
    arm_colors = [cmap((v - lo) / span) for v in sec_rmse]

    nodes, margins = layout_margins(n_chosen, phase, union, cfg["guard_deg"])
    draw_zone_wedges(ax, union, STAR_INNER_R, STAR_TOP_R - STAR_INNER_R)
    draw_star(ax, n_chosen, phase, arm_colors=arm_colors, alpha_fill=0.06)

    truth_zones = mask_to_zones(s["angles"], truth_zone_mask(
        s["angles"], s["height_mm"], table, det["truth_depth_frac"]), 0.1)
    for z in truth_zones:                     # истинные трещины — чёрные дуги
        ax.bar(np.deg2rad(0.5 * (z[0] + z[1])), 0.05,
               width=np.deg2rad(z[1] - z[0]), bottom=1.0, color="black",
               alpha=0.85, lw=0.0, align="center")
    for nd, m in zip(nodes, margins):
        col = "tab:green" if m >= 0 else "tab:red"
        ax.plot([np.deg2rad(nd), np.deg2rad(nd)], [STAR_INNER_R, 0.34],
                "-", color=col, lw=0.9, alpha=0.75)
        ax.plot([np.deg2rad(nd)], [0.52], marker="o", ms=3.2, color=col, zorder=6)
        ax.text(np.deg2rad(nd), 0.22, f"{m:+.0f}", fontsize=6, ha="center",
                va="center", color="0.25")
    ax.set_ylim(0, STAR_TOP_R)
    ax.set_yticks([])
    ax.set_xticks(np.deg2rad(np.arange(0, 360, 45)))
    ax.set_xticklabels([f"{d}°" for d in range(0, 360, 45)], fontsize=7)
    ax.grid(alpha=0.25)
    ax.set_title(f"Выбранная раскладка: N={n_chosen}, фаза {phase:g}° "
                 f"(сечение {sid0}, h={s['height_mm']:.0f} мм)\n"
                 "лучи раскрашены по RMSE патча (видно самый «слабый» луч), "
                 "красное — запретные зоны,\nчёрные дуги — истинные трещины, "
                 "цифры у центра — отступ узла, °", fontsize=9)

    # --- (0,1) развёртка по углу ---
    ax = fig.add_subplot(2, 2, 2)
    y_lo = float(np.min(s["ideal"]))
    y_hi = float(np.max(s["ideal"]))
    pad = 0.08 * (y_hi - y_lo or 1.0)
    ax.plot(s["angles"], s["ideal"], "-", color="black", lw=0.8, alpha=0.6,
            label=f"эталон (сечение {sid0}, с трещинами)")
    for k, z in enumerate(union):
        ax.axvspan(z[0], z[1], color="tab:red", alpha=0.16, lw=0.0,
                   label="запретная зона (объединение)" if k == 0 else None)
    for z in truth_zones:
        for e in z:
            ax.axvline(e, color="black", lw=0.8, ls=":", alpha=0.7)
    ax.set_xlim(0, 360)
    ax.set_ylim(y_lo - 2.5 * pad, y_hi + 3.0 * pad)
    for nd, m in zip(nodes, margins):
        ax.axvline(nd, color="tab:green" if m >= 0 else "tab:red", lw=1.4, alpha=0.85)
        ax.text(nd, ax.get_ylim()[1], f"{m:+.1f}", fontsize=6.5, rotation=90,
                va="top", ha="right", color="0.25")
    for nd in flex_info["nodes"]:
        ax.plot([nd], [ax.get_ylim()[0] + 0.35 * pad], marker="^", ms=6,
                color="tab:blue")
    ax.set_xticks(np.arange(0, 361, 30))
    ax.set_xlabel("угол, °")
    ax.set_ylabel("радиус, мм")
    h, l = ax.get_legend_handles_labels()
    h.append(plt.Line2D([], [], marker="^", ls="", color="tab:blue"))
    l.append("гибкие узлы (flex)")
    ax.legend(h, l, fontsize=7.5, loc="upper right", ncol=2, framealpha=0.9)
    ax.set_title("Развёртка по углу: куда попали швы\n"
                 f"симметрично {chosen['min_margin']:+.1f}° -> гибкие узлы "
                 f"{flex_info['min_margin']:+.1f}° (цена: сдвиг до "
                 f"{flex_info['cost_deg']:.1f}°)", fontsize=9)
    ax.grid(alpha=0.3)

    # --- (1,0) отступ от фазы ---
    ax = fig.add_subplot(2, 2, 3)
    ax.axhspan(-12, 0, color="tab:red", alpha=0.07, lw=0.0)
    ax.axhline(0, color="tab:red", lw=1.0, alpha=0.8)
    for row in rows:
        bold = row["n_patches"] == n_chosen
        ax.plot(row["curve_phase"], row["curve_margin"],
                "-" if bold else "--", lw=2.0 if bold else 0.9,
                alpha=0.95 if bold else 0.5,
                label=f"N={row['n_patches']}" + (" (выбран)" if bold else ""))
    ax.axvline(phase, color="tab:green", lw=1.2, ls=":", alpha=0.9)
    ax.set_xlabel("фаза раскладки, ° (внутри сектора 360/N)")
    ax.set_ylabel("мин. отступ узла до трещины, °")
    ax.set_title("Отступ от фазы: где у раскладки «плато» безопасности\n"
                 "(красная область — узел в запретной зоне или ближе запаса)")
    ax.legend(fontsize=7, ncol=2, loc="lower right")
    ax.grid(alpha=0.3)

    # --- (1,1) сводка по N ---
    ax = fig.add_subplot(2, 2, 4)
    ns = [r["n_patches"] for r in rows]
    x = np.arange(len(ns))
    vals = [r["min_margin"] for r in rows]
    ax.bar(x, vals, color=["tab:green" if v >= 0 else "tab:red" for v in vals],
           alpha=0.55, label="мин. отступ узла, °")
    ax.axhline(0, color="black", lw=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in ns])
    ax.set_xlabel("число патчей N")
    ax.set_ylabel("мин. отступ узла, °", color="0.2")

    ax2 = ax.twinx()
    ax2.plot(x, [r.get("rmse", float("nan")) for r in rows], "o-",
             color="tab:blue", label="RMSE модели, мм")
    ax2.set_ylabel("RMSE относительно эталона, мм", color="tab:blue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")
    ax2.axvline(ns.index(n_chosen), color="tab:green", lw=1.2, ls=":", alpha=0.9)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="lower left")
    ax.set_title("Сводка: патчей больше — RMSE ниже,\nно узлы чаще попадают "
                 "на трещины (зелёное = безопасно)")
    ax.grid(alpha=0.3)

    fig.suptitle("Раскладка патчей: узлы (швы) не должны попадать на трещины",
                 fontsize=13)
    plt.tight_layout(rect=(0, 0, 1, 0.955))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)
