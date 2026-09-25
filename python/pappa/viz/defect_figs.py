# вырезано из _src_baseline_defects.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.outlier_cleaner import build_cleaner, median_filter_wrap, window_points
from ..analysis.zones import defect_maps, detect_zones, indicator_curve, load_crack_table, mask_to_zones, score_zones, truth_zone_mask

def plot_windows(cfg, sections, out_path):
    """4 сечения: точки после очистки, эталон и линии фильтра при разных окнах."""
    cyc = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    n = len(cfg["sections"])
    n_cols = 2
    n_rows = int(np.ceil(n / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4.0 * n_rows))
    axes = np.atleast_1d(axes).ravel()

    for ax, sid in zip(axes, cfg["sections"]):
        s = sections[sid]
        a, rc, ac = s["angles"], s["radii_clean"], s["angles_clean"]

        ax.plot(a, s["ideal"], "-", color="black", lw=1.0, alpha=0.75,
                label="эталон (с трещинами)")
        ax.plot(a[::4], s["radii"][::4], ".", color="0.65", ms=1.1, alpha=0.35,
                label="точки (сырые)")

        for i, wdeg in enumerate(cfg["windows_deg"]):
            wp = window_points(ac, wdeg)
            base = median_filter_wrap(rc, wp)
            ax.plot(ac, base, "-", color=cyc[i % len(cyc)], lw=1.0, alpha=0.9,
                    label=f"медиана по кольцу, окно {wdeg:g}° ({wp} тчк)")

        ax.set_title(f"Сечение {sid}, h={s['height_mm']:.0f} мм: "
                     f"median_filter_wrap при разном окне", fontsize=10)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.set_xlim(0, 360)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=6.5, loc="upper right", ncol=2, framealpha=0.85,
                  borderpad=0.3, columnspacing=0.8, handlelength=2.2)

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle(
        "Скользящая медиана по кольцу: маленькое окно «проваливается» в трещину\n"
        "(и в одиночные всплески), большое — срезает глубину трещины и уводит форму",
        fontsize=12, y=1.0)
    plt.tight_layout(rect=(0, 0, 1, 0.93))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_tradeoff(cfg, sections, table, rows, out_path):
    """
    Цена окна фильтра: слева — сохранил ли фильтр дно трещин,
    справа — сколько осталось шума и насколько фильтр увёл форму вне трещин.
    """
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.2))

    wins = [r["window_deg"] for r in rows]

    # --- слева: дно трещин ---
    ax = axes[0]
    n_cracks = len(rows[0]["retained_depth_mm"])
    for ci in range(n_cracks):
        vals = [r["retained_depth_mm"][ci] for r in rows]
        ax.plot(wins, vals, "o-", label=f"трещина {ci + 1}")
    ax.axhline(0.0, color="black", lw=0.9, alpha=0.6)
    ax.axvline(cfg["baseline_deg"], color="tab:purple", lw=1.0, ls="--", alpha=0.8,
               label=f"рабочее окно {cfg['baseline_deg']:g}°")
    ax.set_xscale("log")
    ax.set_xticks(wins)
    ax.set_xticklabels([f"{w:g}" for w in wins])
    ax.set_xlabel("окно медианного фильтра, °")
    ax.set_ylabel("min(эталон − baseline) на дне трещины, мм")
    ax.set_title("Насколько фильтр проследил дно трещины\n"
                 "(0 = проследил, меньше 0 = срезал)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # --- справа: шум и унесённая форма ---
    ax = axes[1]
    ax.plot(wins, [r["noise_mm"] for r in rows], "o-", color="tab:blue",
            label="шум после фильтра: sigma(r − baseline)")
    ax.axvline(cfg["baseline_deg"], color="tab:purple", lw=1.0, ls="--", alpha=0.8,
               label=f"рабочее окно {cfg['baseline_deg']:g}°")
    ax.set_xscale("log")
    ax.set_xticks(wins)
    ax.set_xticklabels([f"{w:g}" for w in wins])
    ax.set_xlabel("окно медианного фильтра, °")
    ax.set_ylabel("шум, мм", color="tab:blue")
    ax.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax.twinx()
    ax2.plot(wins, [r["bias_mm"] for r in rows], "s--", color="tab:red",
             label="уведённая форма: max|baseline − эталон| вне трещин")
    ax2.set_ylabel("смещение, мм", color="tab:red")
    ax2.tick_params(axis="y", labelcolor="tab:red")

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="center left")
    ax.set_title("Шум против уведённой формы\n(среднее по показанным сечениям)")
    ax.grid(True, alpha=0.3)

    fig.suptitle("Компромисс окна медианного фильтра: дно трещин vs шум vs форма",
                 fontsize=12)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_indicators(cfg, sections, table, data, out_path):
    """
    Ход исследования по одному сечению: слева — безразмерные признаки
    (полоса band, огибающая res, d1, d2 и «сырые» d1/d2 с порогами),
    справа — тот же профиль с узким и широким уровнем и найденными зонами.
    """
    det = cfg["detector"]
    n = len(cfg["sections"])
    fig, axes = plt.subplots(n, 2, figsize=(17, 3.4 * n))
    axes = np.atleast_2d(axes)

    for row, sid in enumerate(cfg["sections"]):
        s = sections[sid]
        a, ac = s["angles"], s["angles_clean"]
        d = data[sid]
        m = d["maps"]

        ax = axes[row, 0]
        ax.plot(ac, m["d2_raw_norm"], "-", color="0.85", lw=0.5,
                label="d2 без сглаживания (шум)")
        ax.plot(ac, m["d1_raw_norm"], "-", color="0.7", lw=0.5,
                label="d1 без сглаживания (шум)")
        ax.plot(ac, m["env_norm"], "-", color="tab:blue", lw=0.9,
                label="огибающая |r − узкий уровень|, сглаж. 2°")
        ax.plot(ac, m["d1_norm"], "-", color="tab:green", lw=0.9,
                label="d1 = |Δ уровень|, сглаж. 2°")
        ax.plot(ac, m["d2_norm"], "-", color="tab:red", lw=0.9,
                label="d2 = |Δ² уровень|, сглаж. 2°")
        ax.plot(ac, m["band_norm"], "-", color="tab:orange", lw=1.6,
                label=f"band = |уровень 1° − уровень {cfg['wide_deg']:g}°|, сглаж. 2°")

        ax.axhline(det["env_k"], color="tab:blue", ls=":", lw=1.0, alpha=0.8)
        ax.axhline(det["d1_k"], color="tab:green", ls=":", lw=1.0, alpha=0.8)
        ax.axhline(det["d2_k"], color="tab:red", ls=":", lw=1.0, alpha=0.8)
        ax.axhline(det["band_k"], color="tab:orange", ls=":", lw=1.3, alpha=0.9)

        for z in d["zones_truth"]:
            ax.axvspan(z[0], z[1], color="tab:green", alpha=0.10, lw=0)
        for z in d["zones_band"]:
            ax.axvspan(z[0], z[1], color="tab:red", alpha=0.10, lw=0)

        ax.set_yscale("log")
        ax.set_ylim(0.05, 200)
        ax.set_xlim(0, 360)
        ax.set_title(f"Сечение {sid} (h={s['height_mm']:.0f} мм): признаки "
                     f"дефектности в «MAD-ах», узкий уровень — окно "
                     f"{m['window_deg']:.2f}° ({m['window_points']} тчк)",
                     fontsize=9.5)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("признак / своя sigma (лог. шкала)")
        ax.grid(True, alpha=0.3, which="both")
        if row == 0:
            ax.legend(fontsize=6.2, loc="upper right", ncol=2, framealpha=0.85,
                      borderpad=0.3, columnspacing=0.8, handlelength=2.0)

        ax = axes[row, 1]
        ax.plot(a[::4], s["radii"][::4], ".", color="0.7", ms=1.1, alpha=0.4,
                label="точки (сырые)")
        ax.plot(ac, m["wide"], "-", color="tab:orange", lw=1.2, alpha=0.9,
                label=f"широкий уровень {cfg['wide_deg']:g}°")
        ax.plot(ac, m["baseline"], "-", color="black", lw=1.0, alpha=0.85,
                label="узкий уровень 1°")
        ax.plot(a, s["ideal"], "--", color="tab:gray", lw=0.9, alpha=0.8,
                label="эталон")
        for z in d["zones_truth"]:
            ax.axvspan(z[0], z[1], color="tab:green", alpha=0.12, lw=0)
        for z in d["zones_band"]:
            ax.axvspan(z[0], z[1], color="tab:red", alpha=0.12, lw=0)

        sc = d["score_band"]
        ax.set_title(f"Сечение {sid}: трещин {sc['truth']}, зон по band: "
                     f"{sc['detected']} (TP {sc['tp']}, FP {sc['fp']}, FN {sc['fn']}), "
                     f"P={sc['precision']:.2f} R={sc['recall']:.2f} F1={sc['f1']:.2f}",
                     fontsize=9.5)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.set_xlim(0, 360)
        ax.grid(True, alpha=0.3)
        if row == 0:
            ax.legend(fontsize=6.2, loc="lower right", ncol=1, framealpha=0.85,
                      borderpad=0.3, handlelength=2.0)

    fig.suptitle(
        "Дефектность: зелёные полосы — истинные трещины (таблица генератора), "
        "красные — зоны, найденные по band\n"
        "точечные производные (серые линии) тонут в шуме шага 0.06°, "
        "двухмасштабная band их находит",
        fontsize=12, y=1.0)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_candidates(cfg, sections, cand_res, out_path):
    """Сравнение кандидатов-признаков по зонам (по одному сечению в панели)."""
    secs = cand_res["sections"][:4]
    n_cols = 2
    n_rows = int(np.ceil(len(secs) / n_cols))
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4.4 * n_rows))
    axes = np.atleast_1d(axes).ravel()

    for ax, sid in zip(axes, secs):
        s = sections[sid]
        for zi, z in enumerate(cand_res["truth"][sid]):
            ax.axvspan(z[0], z[1], color="tab:green", alpha=0.12, lw=0,
                       label="истинные зоны трещин" if zi == 0 else None)

        for cand in cfg["candidates"]:
            sc = cand_res["per"][cand["label"]][sid]["score"]
            vals = cand_res["per"][cand["label"]][sid]["values"]
            ax.plot(s["angles_clean"], vals, lw=0.9,
                    label=f"{cand['label']}: P={sc['precision']:.2f} "
                          f"R={sc['recall']:.2f} (зон {sc['detected']}, FP {sc['fp']})")
            ax.axhline(cand["k"], ls=":", lw=0.9, alpha=0.6)

        ax.set_yscale("log")
        ax.set_ylim(0.05, 200)
        ax.set_xlim(0, 360)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("признак / своя sigma (лог. шкала)")
        ax.set_title(f"Сечение {sid}, h={s['height_mm']:.0f} мм — "
                     f"какой признак лучше видит трещины", fontsize=10)
        ax.grid(True, alpha=0.3, which="both")
        ax.legend(fontsize=6.3, loc="upper right", framealpha=0.85,
                  borderpad=0.3, handlelength=2.0)

    for ax in axes[len(secs):]:
        ax.axis("off")

    fig.suptitle("Кандидаты признака дефектности: пунктир — порог k, "
                 "зелёные полосы — истинные зоны трещин. "
                 "Ошибки P/R посчитаны по зонам (не по точкам)", fontsize=12, y=1.0)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_k_sweep(cfg, sweep, out_path):
    """
    «Ход исследования»: слева F1(k) для каждого кандидата (звёздочка — лучшее k),
    справа — P/R/F1 при лучшем k. Так видно, что у band есть широкое плато F1=1,
    а у производных F1 мал при любом k.
    """
    labels = list(sweep.keys())
    cyc = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    colors = {lab: cyc[i % len(cyc)] for i, lab in enumerate(labels)}

    fig, axes = plt.subplots(1, 2, figsize=(16, 5.4))
    ax = axes[0]
    for lab in labels:
        rows = sweep[lab]["rows"]
        b = sweep[lab]["best"]
        ax.plot([r["k"] for r in rows], [r["f1"] for r in rows], "-",
                color=colors[lab], lw=1.4,
                label=f"{lab}: max F1={b['f1']:.2f} при k={b['k']:g}")
        ax.plot([b["k"]], [b["f1"]], "*", color=colors[lab], ms=13,
                mec="black", mew=0.6)
    ax.set_xlabel("порог k, «MAD-ы»")
    ax.set_ylabel("F1 по зонам (среднее по всем сечениям)")
    ax.set_title("Подбор порога: у двухмасштабной band плато F1≈1.0,\n"
                 "у производных потолок низкий при любом k", fontsize=10.5)
    ax.set_ylim(-0.02, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=6.6, loc="lower right", framealpha=0.85, borderpad=0.3,
              handlelength=2.0)

    ax = axes[1]
    x = np.arange(len(labels))
    w = 0.26
    best = [sweep[lab]["best"] for lab in labels]
    ax.bar(x - w, [b["precision"] for b in best], w, label="precision",
           color="tab:blue", alpha=0.85)
    ax.bar(x, [b["recall"] for b in best], w, label="recall",
           color="tab:green", alpha=0.85)
    ax.bar(x + w, [b["f1"] for b in best], w, label="F1",
           color="tab:red", alpha=0.85)
    for xi, b in zip(x, best):
        ax.text(xi, 1.06, f"k={b['k']:g}\nFP={b['fp']:.2f}", ha="center",
                fontsize=6.6)
    ax.set_xticks(x)
    ax.set_xticklabels([lab.replace(", ", ",\n") for lab in labels], fontsize=7)
    ax.set_ylim(0, 1.22)
    ax.set_ylabel("качество по зонам (лучшее k)")
    ax.set_title("Тот же подбор в цифрах: P/R/F1 и число ложных зон на сечение",
                 fontsize=10.5)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=7.5, loc="lower left", ncol=3, framealpha=0.85)

    plt.tight_layout()
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)
