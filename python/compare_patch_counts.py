"""
compare_patch_counts.py

Сравнение одного и того же метода (Adaptive Poly-Patch Approximation)
при РАЗНОМ числе патчей N.

Последовательность:
1. Загрузка сечений из CSV.
2. Очистка выбросов (OutlierCleaner).
3. Обучение PatchApproximator для каждого варианта N (число патчей),
   входящего в CONFIG['variants'].
4. Отрисовка: 4 сечения в сетке 2x2, на каждом наложены кривые результата
   для каждого N; внизу — средняя RMSE по всем показанным сечениям.

Все параметры метода задаются в CONFIG (число патчей, deg_min/deg_max,
amplitude_scale, перекрытия обучения/применения и т.д.).
Сектора и зоны перекрытия пересчитываются автоматически под каждое N.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # только сохранение в файл, без GUI
import matplotlib.pyplot as plt
from pathlib import Path

from outlier_cleaner import OutlierCleaner
from patch_approximator import PatchApproximator


# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

CONFIG = {
    # --- данные ---
    "csv": "synthetic_data.csv",
    "sections": [0, 1, 2, 3],      # какие сечения показать (первым берём 4)
    "grid_points": 1440,           # точек сетки углов для отрисовки/оценки
    "ideal_column": "radius_ideal_mm",

    # --- очистка выбросов ---
    "cleaner": {
        "threshold_deriv": 0.5,
        "mad_k": 9.5,
        "z_threshold": 3.5,
    },

    # --- базовые параметры метода (применяются ко всем вариантам) ---
    "base": {
        "deg_min": 4,
        "deg_max": 14,
        "amplitude_scale": 180.0,
        "overlap_train": 15.0,
        "overlap_use": 5.0,
    },

    # --- варианты: тут задаётся число патчей и (опц.) переопределения base ---
    # Любой ключ из 'base' можно переопределить прямо в варианте.
    # Ключи 'color'/'label'/'linestyle' — только для отрисовки (в метод не идут).
    # Пунктирные стили намеренно разные, чтобы наложенные кривые не сливались.
    "variants": [
        {"n_patches": 4,  "color": "tab:blue",   "label": "4 патча",
         "linestyle": (0, (6, 2))},                    # длинный пунктир
        {"n_patches": 8,  "color": "tab:orange", "label": "8 патчей",
         "linestyle": (0, (2.5, 1.5))},                # короткий пунктир
        {"n_patches": 12, "color": "tab:green",  "label": "12 патчей",
         "linestyle": (0, (1, 1.2))},                  # точечный
        {"n_patches": 16, "color": "tab:red",    "label": "16 патчей",
         "linestyle": (0, (5, 1.2, 1, 1.2))},          # штрих-пунктир
    ],

    # --- стиль графиков (линии тонкие и пунктирные: сильное наложение) ---
    "style": {
        "variant_lw": 0.9,       # толщина кривых аппроксимации
        "ideal_lw": 0.8,         # толщина линии эталона (сплошная)
        "data_ms": 1.0,          # размер маркера «данные»
        "data_alpha": 0.20,      # прозрачность фона данных
        "sector_lw": 0.4,        # толщина границ секторов
        "sector_alpha": 0.08,    # прозрачность границ секторов
        "zero_lw": 0.7,          # толщина нулевой линии на графике невязок
    },

    # --- вывод ---
    "output": "patch_count_comparison.png",
    "output_residuals": "patch_count_comparison_residuals.png",
    "show_residuals": True,        # второй график: невязка (fitted - ideal)
    "dpi": 120,
}

# Ключи варианта, которые используются ТОЛЬКО для отрисовки
# и не передаются в PatchApproximator.
PLOT_ONLY_KEYS = ("color", "label", "linestyle")


# ============================================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ============================================================================

def resolve_path(name):
    """Путь к файлу относительно папки скрипта (не текущего каталога)."""
    p = Path(name)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parent / name


def build_variant_config(base, variant):
    """Сливает базовые параметры метода с переопределениями варианта."""
    params = dict(base)
    params.update({k: v for k, v in variant.items()
                   if k not in PLOT_ONLY_KEYS})
    return params


def make_approximator(params):
    """Создаёт PatchApproximator строго из известных ему аргументов."""
    return PatchApproximator(
        n_patches=int(params["n_patches"]),
        deg_min=int(params["deg_min"]),
        deg_max=int(params["deg_max"]),
        amplitude_scale=float(params["amplitude_scale"]),
        overlap_train=float(params["overlap_train"]),
        overlap_use=float(params["overlap_use"]),
    )


# ============================================================================
# ЗАГРУЗКА + ОЧИСТКА
# ============================================================================

def load_and_clean(csv_path, cleaner_cfg, ideal_column):
    """
    Читает CSV, группирует по section_id, чистит выбросы.

    Возвращает dict: section_id -> {
        'angles', 'radii',           # чистые (без выбросов) точки
        'angles_all', 'radii_all',   # все точки (для фона)
        'ideal_deg', 'ideal_r',      # эталон (углы, радиус)
        'n_total', 'n_out',          # всего точек / выброшено
        'height_mm',
    }
    """
    data = pd.read_csv(csv_path)
    cleaner = OutlierCleaner(**cleaner_cfg)

    sections = {}
    for sid in sorted(data["section_id"].unique()):
        sec = data[data["section_id"] == sid] \
            .copy().sort_values("angle_deg").reset_index(drop=True)

        a_all = sec["angle_deg"].values
        r_all = sec["radius_mm"].values

        mask = cleaner.clean(a_all, r_all)

        sections[sid] = {
            "angles": a_all[~mask],
            "radii": r_all[~mask],
            "angles_all": a_all,
            "radii_all": r_all,
            "ideal_deg": sec["angle_deg"].values,
            "ideal_r": sec[ideal_column].values,
            "n_total": len(a_all),
            "n_out": int(mask.sum()),
            "height_mm": float(sec["height_mm"].iloc[0]),
        }
    return sections


# ============================================================================
# ОБУЧЕНИЕ И ОЦЕНКА
# ============================================================================

def evaluate_variant(section, params, angles_grid):
    """
    Обучает PatchApproximator variant-параметрами на очищенном сечении
    и считает RMSE по отношению к эталону на сетке углов.

    Возвращает (fitted, rmse, info), где info содержит степени патчей и
    геометрию секторов (half_sector/half_train/half_use).
    """
    approx = make_approximator(params)
    approx.fit(section["angles"], section["radii"])

    fitted = approx.eval(angles_grid)

    ideal_grid = np.interp(angles_grid,
                           section["ideal_deg"], section["ideal_r"])
    rmse = float(np.sqrt(np.mean((fitted - ideal_grid) ** 2)))

    info = {
        "degrees": approx.get_degrees(),
        "half_sector": approx.half_sector_,
        "half_train": approx.half_sector_ + approx.overlap_train,
        "half_use": approx.half_sector_ + approx.overlap_use,
        "n_patches": approx.n_patches,
    }
    return fitted, rmse, info


# ============================================================================
# MAIN
# ============================================================================

def main():
    cfg = CONFIG
    csv_path = resolve_path(cfg["csv"])

    print("=" * 70)
    print("СРАВНЕНИЕ ЧИСЛА ПАТЧЕЙ (Adaptive Poly-Patch Approximation)")
    print("=" * 70)
    print(f"Данные:    {csv_path.name}")
    print(f"Сечения:   {cfg['sections']}")
    print(f"Варианты N: {[v['n_patches'] for v in cfg['variants']]}")

    # --- загрузка + очистка ---
    sections = load_and_clean(csv_path, cfg["cleaner"], cfg["ideal_column"])

    print("\n=== ОЧИСТКА ===")
    for sid in cfg["sections"]:
        s = sections[sid]
        pct = 100.0 * s["n_out"] / s["n_total"] if s["n_total"] else 0.0
        print(f"  Сечение {sid} (h={s['height_mm']:.0f} мм): "
              f"выбросов {s['n_out']}/{s['n_total']} ({pct:.1f}%), "
              f"чистых {len(s['angles'])}")

    angles_grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)

    # --- обучение по всем сечениям x вариантам ---
    # results[sid][vi] = {'fitted':..., 'rmse':..., 'info':...}
    results = {sid: [] for sid in cfg["sections"]}

    for variant in cfg["variants"]:
        params = build_variant_config(cfg["base"], variant)
        params["n_patches"] = variant["n_patches"]

        print(f"\n=== ВАРИАНТ: {variant['label']} (N={params['n_patches']}) ===")
        for sid in cfg["sections"]:
            fitted, rmse, info = evaluate_variant(
                sections[sid], params, angles_grid)
            results[sid].append({"fitted": fitted, "rmse": rmse, "info": info})
            print(f"  Сечение {sid}: RMSE={rmse:.5f}  "
                  f"half_sector={info['half_sector']:.2f}° "
                  f"half_use={info['half_use']:.2f}°  "
                  f"deg={info['degrees']}")

    # --- средняя RMSE по всем показанным сечениям для каждого варианта ---
    mean_rmse = [
        float(np.mean([results[sid][vi]["rmse"] for sid in cfg["sections"]]))
        for vi in range(len(cfg["variants"]))
    ]

    print("\n=== СРЕДНЯЯ RMSE ПО СЕЧЕНИЯМ ===")
    for vi, variant in enumerate(cfg["variants"]):
        print(f"  {variant['label']:>10}: {mean_rmse[vi]:.5f} мм")

    # ================= ОТРИСОВКА: 4 СЕЧЕНИЯ, 2x2 =================
    style = cfg.get("style", {})
    variant_lw = style.get("variant_lw", 0.9)
    ideal_lw = style.get("ideal_lw", 0.8)
    data_ms = style.get("data_ms", 1.0)
    data_alpha = style.get("data_alpha", 0.20)
    sector_lw = style.get("sector_lw", 0.4)
    sector_alpha = style.get("sector_alpha", 0.08)
    zero_lw = style.get("zero_lw", 0.7)

    n_sec = len(cfg["sections"])
    n_cols = 2
    n_rows = int(np.ceil(n_sec / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 10))
    axes = np.atleast_1d(axes).ravel()

    for ax, sid in zip(axes, cfg["sections"]):
        s = sections[sid]

        # фон: все точки (включая выбросы)
        ax.plot(s["angles_all"], s["radii_all"], ".", color="gray",
                markersize=data_ms, alpha=data_alpha, label="данные")

        # эталон
        ax.plot(s["ideal_deg"], s["ideal_r"], "-", color="black",
                lw=ideal_lw, alpha=0.6, label="эталон")

        # результат для каждого числа патчей — тонкий пунктир со своим узором
        for vi, variant in enumerate(cfg["variants"]):
            r = results[sid][vi]
            ax.plot(angles_grid, r["fitted"], color=variant["color"],
                    lw=variant_lw, ls=variant.get("linestyle", "--"),
                    alpha=0.95,
                    label=f"{variant['label']} (RMSE={r['rmse']:.4f})")

            # границы секторов для этого N (едва заметные вертикальные штрихи)
            step = 360.0 / variant["n_patches"]
            for k in range(variant["n_patches"]):
                ax.axvline(k * step, color=variant["color"],
                           lw=sector_lw, alpha=sector_alpha, zorder=0)

        ax.set_title(f"Сечение {sid}, h={s['height_mm']:.0f} мм | "
                     f"чистых {len(s['angles'])}/{s['n_total']}", fontsize=10)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.set_xlim(0, 360)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7, loc="upper right", ncol=1)

    for ax in axes[n_sec:]:
        ax.axis("off")

    # сводка средней RMSE в заголовке рисунка
    summary = "   ".join(
        f"{v['label']}: {mean_rmse[i]:.5f} мм"
        for i, v in enumerate(cfg["variants"])
    )
    fig.suptitle(
        "Сравнение числа патчей на 4 сечениях — средняя RMSE:  " + summary,
        fontsize=12, y=0.995)

    plt.tight_layout(rect=(0, 0, 1, 0.97))
    out = resolve_path(cfg["output"])
    plt.savefig(out, dpi=cfg["dpi"], bbox_inches="tight")
    print(f"\nГрафик сохранён: {out}")

    # ================= ОТРИСОВКА: НЕВЯЗКА (fitted - ideal) =================
    # На основном графике масштаб радиусов ~15 мм, и разница между N внутри
    # шума. Здесь показываем ту же разницу как невязку к эталону.
    if cfg.get("show_residuals", True):
        fig2, axes2 = plt.subplots(n_rows, n_cols, figsize=(16, 10),
                                   sharex=True, sharey=True)
        axes2 = np.atleast_1d(axes2).ravel()

        for ax, sid in zip(axes2, cfg["sections"]):
            s = sections[sid]
            ideal_grid = np.interp(angles_grid, s["ideal_deg"], s["ideal_r"])

            for vi, variant in enumerate(cfg["variants"]):
                r = results[sid][vi]
                ax.plot(angles_grid, r["fitted"] - ideal_grid,
                        color=variant["color"], lw=variant_lw,
                        ls=variant.get("linestyle", "--"), alpha=0.95,
                        label=f"{variant['label']} (RMSE={r['rmse']:.4f})")

            ax.axhline(0.0, color="black", lw=zero_lw, alpha=0.5)
            ax.set_title(f"Сечение {sid}, h={s['height_mm']:.0f} мм — "
                         f"невязка (аппроксимация − эталон)", fontsize=10)
            ax.set_xlabel("Угол, °")
            ax.set_ylabel("Δr, мм")
            ax.set_xlim(0, 360)
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=7, loc="upper right", ncol=1)

        for ax in axes2[n_sec:]:
            ax.axis("off")

        fig2.suptitle("Невязка аппроксимации к эталону — средняя RMSE:  "
                      + summary, fontsize=12, y=0.995)
        plt.tight_layout(rect=(0, 0, 1, 0.97))
        out2 = resolve_path(cfg["output_residuals"])
        plt.savefig(out2, dpi=cfg["dpi"], bbox_inches="tight")
        print(f"График невязок сохранён: {out2}")


if __name__ == "__main__":
    main()
