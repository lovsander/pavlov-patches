# вырезано из compare_cleaner_auto_src.py (рефакторинг, см. CONTEXT.md §21)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from ..core.outlier_cleaner import AutoOutlierCleaner, build_cleaner
from ..core.patch_approximator import PatchApproximator

def plot_cleaner_report(cfg, sections, zoom_ctx, zoom_results, all_results, window_rows,
                out_path):
    """Сводный отчёт одной картинкой (2x3)."""
    fig, axes = plt.subplots(2, 3, figsize=(19, 10))
    names = [name for name, _ in cfg["methods"]]
    section = sections[cfg["zoom"]["section"]]
    a, r = section["angles"], section["radii"]

    # --- 1-2. профиль с флагами: целиком и зум на самую глубокую яму ---
    for ax, half in ((axes[0, 0], None), (axes[0, 1], cfg["zoom"]["half_width_deg"])):
        ax.plot(a, section["ideal"], "k-", lw=1.2, alpha=0.8, label="эталон")
        ax.plot(a, r, ".", ms=1.5, color="0.6", label="сырые точки")
        if "manual" in zoom_results:
            m = zoom_results["manual"]["mask"]
            ax.plot(a[m], r[m], "x", ms=3.5, color="tab:red",
                    label=f"manual ({int(m.sum())} шт.)")
        if "hampel" in zoom_results:
            m = zoom_results["hampel"]["mask"]
            ax.plot(a[m], r[m], "o", ms=3.2, mfc="none", color="tab:green",
                    label=f"hampel auto ({int(m.sum())} шт.)")
        if half is None:
            ax.set_xlim(0, 360)
            ax.set_title(f"Сечение {cfg['zoom']['section']}: флаги выбросов")
        else:
            pit = zoom_ctx["pit_angle"]
            ax.set_xlim(pit - half, pit + half)
            ax.set_title(f"Зум на самую глубокую яму ({pit:.0f}°)")
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    # --- 3. F1 по методам ---
    ax = axes[0, 2]
    vals = [np.mean([all_results[sid][n]["f1"] for sid in all_results])
            for n in names]
    ax.bar(names, vals, color="tab:blue", alpha=0.8)
    ax.set_ylim(0, 1.1)
    ax.set_title("F1 обнаружения выбросов (истина: is_outlier)")
    ax.set_ylabel("F1")
    ax.tick_params(axis="x", rotation=30)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    # --- 4. RMSE модели по методам ---
    ax = axes[1, 0]
    all_names = ["raw"] + names
    x = np.arange(len(all_names))
    rm_ideal = [np.mean([all_results[sid][n]["rmse_ideal"] for sid in all_results])
                for n in all_names]
    rm_raw = [np.mean([all_results[sid][n]["rmse_raw"] for sid in all_results])
              for n in all_names]
    ax.bar(x - 0.2, rm_ideal, 0.4, label="к эталону", color="tab:purple")
    ax.bar(x + 0.2, rm_raw, 0.4, label="к сырым точкам", color="tab:orange")
    ax.set_xticks(x)
    ax.set_xticklabels(all_names, rotation=30)
    ax.set_title("RMSE подгонки (N патчей) по сетке")
    ax.set_ylabel("RMSE, мм")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    # --- 5. свип порога (tune) ---
    ax = axes[1, 1]
    rows = zoom_results.get("iqr-tuned", {}).get("tuned_rows") or []
    if rows:
        thr = [row["threshold"] for row in rows]
        score = [row["score"] for row in rows]
        ax.plot(thr, score, "o-", color="tab:blue", label="сеточная RMSE")
        best = [row for row in rows if row.get("best")]
        if best:
            ax.plot(best[0]["threshold"], best[0]["score"], "*", ms=16,
                    color="tab:red", label=f"выбрано k={best[0]['threshold']:.2f}")
        ax.set_xlabel("порог k (сигм локального MAD)")
        ax.set_ylabel("RMSE, мм")
        ax.set_title("Автоподбор порога по критерию (сечение "
                     f"{cfg['zoom']['section']})")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    else:
        ax.set_title("Автоподбор порога: нет данных")

    # --- 6. чувствительность к окну Хампеля ---
    ax = axes[1, 2]
    wins = [row["window"] for row in window_rows]
    ax.plot(wins, [row["f1_local"] for row in window_rows], "o-", color="tab:red",
            label="F1 (масштаб в окне)")
    ax.plot(wins, [row["f1_global"] for row in window_rows], "s--",
            color="tab:green", label="F1 (общий масштаб)")
    ax.set_xlabel("окно фильтра Хампеля, точек")
    ax.set_ylabel("F1")
    ax.set_ylim(0, 1.1)
    ax2 = ax.twinx()
    ax2.plot(wins, [row["rmse_global"] for row in window_rows], "^-",
             color="tab:purple", label="RMSE к эталону (общий масштаб)")
    ax2.set_ylabel("RMSE, мм", color="tab:purple")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8)
    ax.set_title("Чувствительность hampel к окну")
    ax.grid(True, alpha=0.3)

    fig.suptitle("Очистка выбросов: ручные пороги vs автоподбор "
                 "(синтетика, истина is_outlier)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_path, dpi=cfg["dpi"])
    plt.close(fig)
