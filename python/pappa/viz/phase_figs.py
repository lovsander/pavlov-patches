# вырезано из _src_per_section_phase.py (рефакторинг, см. CONTEXT.md §21)

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..analysis.layout import fit_layout, layout_margins, section_crack_zones, union_zones, zone_margin_deg
from ..core.geometry import node_angles, patch_centers
from ..io.dataset import attach_ideal_grid, load_sections
from ..paths import resolve_path
from ..analysis.per_section_phase import pit_center_offsets, section_rmse

SEC_COLORS = ["#D55E00", "#0072B2", "#009E73", "#7B3294",
              "#E69F00", "#56B4E9", "#CC79A7", "#A6761D"]


def plot_phase_fits(cfg, sections, grid, zones_by_section, n, own_rows, shared_row,
              out_path):
    """
    4 сечения: своя фаза (цвет) против общей фазы (серый пунктир).
    Внизу — отметки швов: зелёный (отступ >= 0) / красный (шов в зоне).
    """
    secs = cfg["sections"]
    fig, axes = plt.subplots(2, 2, figsize=(16.5, 10.5))
    axes = np.atleast_1d(axes).ravel()

    for ax, sid in zip(axes, secs):
        s = sections[sid]
        for a, b in zones_by_section[sid]:
            ax.axvspan(a, b, color="tab:red", alpha=0.14, lw=0.0, zorder=0)
        ax.plot(s["angles"], s["radii"], ".", color="gray", markersize=1.0,
                alpha=0.18)
        ax.plot(s["angles"], s["ideal"], "-", color="black", lw=0.9, alpha=0.6)

        r_own = own_rows[sid]
        _, y_own = fit_layout(s, grid, cfg["model"], n, r_own["phase"])
        _, y_sh = fit_layout(s, grid, cfg["model"], n, shared_row["phase"])
        ax.plot(grid, y_sh, ls=(0, (6, 2)), color="0.45", lw=1.3,
                label=f"общая фаза {shared_row['phase']:g}° — RMSE "
                      f"{section_rmse(cfg, s, grid, n, shared_row['phase']):.4f}")
        ax.plot(grid, y_own, "-", color=SEC_COLORS[secs.index(sid)], lw=1.6,
                label=f"своя фаза {r_own['phase']:g}° — RMSE "
                      f"{r_own['rmse']:.4f}, отступ {r_own['margin']:+.1f}°")

        y_lo, y_hi = ax.get_ylim()
        pad = 0.07 * (y_hi - y_lo)
        ax.set_ylim(y_lo - 1.1 * pad, y_hi + 0.5 * pad)
        bad = 0
        for nd in node_angles(n, r_own["phase"]):
            m = zone_margin_deg(nd, zones_by_section[sid], cfg["guard_deg"])
            bad += int(m < 0)
            ax.plot([nd, nd], [y_lo - 0.95 * pad, y_lo - 0.2 * pad],
                    color="tab:green" if m >= 0 else "tab:red", lw=2.2)
        ax.set_title(f"Сечение {sid}, h = {s['height_mm']:.0f} мм | своя фаза "
                     f"{r_own['phase']:g}°, швов в запретной зоне: {bad}",
                     fontsize=10)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.set_xlim(0, 360)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="upper right", framealpha=0.9)

    fig.suptitle(
        f"Звезда N = {n}: на каждом сечении СВОЯ фаза (цвет) против общей фазы "
        f"{shared_row['phase']:g}° (серый пунктир)\n"
        "Фон — зоны-трещины ЭТОГО сечения; полоски внизу — швы раскладки "
        "(зелёный = отступ >= 0, красный = шов на трещине)", fontsize=12)
    plt.tight_layout(rect=(0, 0, 1, 0.92))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_overview(cfg, sections, zones_by_section, own_all, shared_rows,
                  n_report, out_path):
    """
    4 панели: фаза против высоты (свип трещины), RMSE «своя против общей»,
    смещение ям от центра патча, звёзды всех сечений на одной полярной оси.
    """
    fig = plt.figure(figsize=(16.5, 11.0))
    secs = cfg["sections"]
    heights = {sid: sections[sid]["height_mm"] for sid in cfg["all_sections"]}
    sector = 360.0 / n_report

    # --- (0,0) фаза против высоты (углы приведены к сектору) ---
    ax = fig.add_subplot(2, 2, 1)
    for sid in cfg["all_sections"]:
        for a, b in zones_by_section[sid]:
            ax.plot([heights[sid]], [0.5 * (a + b) % sector], marker="d", ms=5,
                    color="tab:red", alpha=0.75)
    ax.plot([], [], marker="d", ls="", color="tab:red",
            label=f"центр зоны-трещины, ° mod сектор ({sector:.1f}°)")
    for k, n in enumerate(cfg["n_patches_compare"]):
        sec_n = 360.0 / n
        hs = [heights[sid] for sid in cfg["all_sections"]]
        ph = [own_all[n][sid]["phase"] for sid in cfg["all_sections"]]
        ax.plot(hs, ph, "o-", ms=4.5, color=SEC_COLORS[k % len(SEC_COLORS)],
                label=f"своя фаза, N = {n} (в секторе {sec_n:.1f}°)")
        ax.axhline(shared_rows[n]["phase"], ls=":", lw=1.1,
                   color=SEC_COLORS[k % len(SEC_COLORS)], alpha=0.85)
    ax.plot([], [], ls=":", color="0.3", label="общая фаза (горизонтали)")
    ax.set_xlabel("Высота сечения, мм")
    ax.set_ylabel("Угол внутри сектора, °")
    ax.set_title("Трещина свипается с высотой (~20° за 45 мм): своя фаза\n"
                 "следует за ней, общая фаза — одна горизонталь на всё тело",
                 fontsize=10)
    ax.legend(fontsize=7.5, ncol=2)
    ax.grid(alpha=0.3)

    # --- (0,1) RMSE: своя фаза против общей ---
    ax = fig.add_subplot(2, 2, 2)
    x = np.arange(len(secs))
    n_n = len(cfg["n_patches_compare"])
    w = 0.8 / (2 * n_n)
    for k, n in enumerate(cfg["n_patches_compare"]):
        own = [own_all[n][s]["rmse"] for s in secs]
        sh = [own_all[n][s]["rmse_shared"] for s in secs]
        off = (2 * k - n_n + 0.5) * w
        col = SEC_COLORS[k % len(SEC_COLORS)]
        ax.bar(x + off - w / 2, own, w, color=col, alpha=0.85,
               label=f"N = {n}: своя фаза")
        ax.bar(x + off + w / 2, sh, w, color=col, alpha=0.3, hatch="///",
               edgecolor=col, label=f"N = {n}: общая фаза")
    ax.set_xticks(x)
    ax.set_xticklabels([f"с{s}\nh = {sections[s]['height_mm']:.0f} мм" for s in secs],
                       fontsize=8)
    ax.set_ylabel("RMSE против эталона, мм")
    ax.set_title("Точность на сечении: заливка — своя фаза,\n"
                 "штриховка — общая фаза (единая на всё тело)", fontsize=10)
    ax.legend(fontsize=7.5, ncol=2)
    ax.grid(alpha=0.3, axis="y")

    # --- (1,0) смещение ям от центра патча ---
    ax = fig.add_subplot(2, 2, 3)
    limit = sector * cfg["pit_center_frac"]
    ax.axhspan(-limit, limit, color="tab:green", alpha=0.12, lw=0.0,
               label=f"центральная половина патча (±{limit:.1f}°)")
    for k, sid in enumerate(secs):
        own = pit_center_offsets(zones_by_section[sid], n_report,
                                 own_all[n_report][sid]["phase"])
        sh = pit_center_offsets(zones_by_section[sid], n_report,
                                shared_rows[n_report]["phase"])
        ax.plot([k] * len(sh), sh, marker="_", ls="", ms=26, mew=2.5,
                color="0.55", label="общая фаза" if k == 0 else None)
        ax.plot([k] * len(own), own, marker="o", ls="", ms=8,
                color=SEC_COLORS[k % len(SEC_COLORS)],
                label="своя фаза" if k == 0 else None)
    ax.set_xticks(range(len(secs)))
    ax.set_xticklabels([f"с{s}\nh = {sections[s]['height_mm']:.0f} мм" for s in secs],
                       fontsize=8)
    ax.set_ylabel("|смещение центра ямы от центра патча|, °")
    ax.set_title(f"Яма против центра патча (N = {n_report}): чем ниже точка,\n"
                 "тем «центральнее» яма в своём патче", fontsize=10)
    ax.legend(fontsize=7.5)
    ax.grid(alpha=0.3, axis="y")

    # --- (1,1) звёзды всех сечений на одной полярной оси ---
    ax = fig.add_subplot(2, 2, 4, projection="polar")
    for k, sid in enumerate(secs):
        col = SEC_COLORS[k % len(SEC_COLORS)]
        for a, b in zones_by_section[sid]:
            ax.bar(np.deg2rad(0.5 * (a + b)), 0.28, width=np.deg2rad(b - a),
                   bottom=1.0, color=col, alpha=0.22, lw=0.0, align="center")
        nd = node_angles(n_report, own_all[n_report][sid]["phase"])
        ax.plot(np.deg2rad(nd), np.full(len(nd), 0.84), marker="o", ls="",
                ms=6, color=col,
                label=f"сечение {sid} (h = {sections[sid]['height_mm']:.0f} мм)")
        ax.plot(np.linspace(0, 2 * np.pi, 200), np.ones(200), "-", color="0.7",
                lw=0.8)
    ax.set_ylim(0, 1.28)
    ax.set_yticks([])
    ax.set_xticks(np.deg2rad(np.arange(0, 360, 45)))
    ax.set_xticklabels([f"{d}°" for d in range(0, 360, 45)], fontsize=7)
    ax.set_title(f"Звёзды N = {n_report} при своей фазе: кружки — швы,\n"
                 "дуги — зоны-трещины того же сечения", fontsize=10, pad=14)
    ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, -0.24), ncol=2)

    fig.suptitle("Per-section фаза: звезда вписывается в СВОЮ фазу на каждой "
                 "высоте (объединение зон по сечениям не используется)",
                 fontsize=13)
    plt.tight_layout(rect=(0, 0, 1, 0.93))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)
