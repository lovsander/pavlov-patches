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

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # только сохранение в файл, без GUI
import matplotlib.pyplot as plt
from pathlib import Path

from outlier_cleaner import build_cleaner, AutoOutlierCleaner
from patch_approximator import PatchApproximator


# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

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


# ============================================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ============================================================================

def resolve_path(name):
    """Путь к файлу относительно папки скрипта (не текущего каталога)."""
    p = Path(name)
    if p.is_absolute():
        return p
    return Path(__file__).resolve().parent / name


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


def fit_grid_rmse(a_fit, r_fit, a_grid, ref_r, model_cfg):
    """RMSE модели, обученной на (a_fit, r_fit), относительно ref_r по сетке."""
    ap = PatchApproximator(
        n_patches=int(model_cfg["n_patches"]),
        deg_min=int(model_cfg["deg_min"]),
        deg_max=int(model_cfg["deg_max"]),
        amplitude_scale=float(model_cfg["amplitude_scale"]),
        overlap_train=float(model_cfg["overlap_train"]),
        overlap_use=float(model_cfg["overlap_use"]),
        phase_deg=float(model_cfg.get("phase_deg", 0.0)),
    )
    ap.fit(np.asarray(a_fit, dtype=float), np.asarray(r_fit, dtype=float))
    y = ap.eval(a_grid)
    return float(np.sqrt(np.mean((y - ref_r) ** 2)))


def mask_metrics(mask, truth):
    """TP/FP/FN, precision, recall, F1 относительно истины."""
    mask = np.asarray(mask, dtype=bool)
    if truth is None:
        return {"tp": None, "fp": None, "fn": None,
                "precision": None, "recall": None, "f1": None}
    truth = np.asarray(truth, dtype=bool)
    tp = int(np.sum(mask & truth))
    fp = int(np.sum(mask & ~truth))
    fn = int(np.sum(~mask & truth))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1}


def deepest_pit(angles, ideal):
    """Угол самой глубокой ямы эталона."""
    order = np.argsort(angles)
    return float(np.asarray(angles)[order][int(np.argmin(np.asarray(ideal)[order]))])


def in_window(angles, center, half_width_deg):
    """Маска точек в окне ±half_width_deg вокруг центра (по кольцу)."""
    d = np.abs((np.asarray(angles, dtype=float) - center + 180.0) % 360.0 - 180.0)
    return d <= half_width_deg


def fmt(value, spec=".3f"):
    """Форматирование числа; None печатается как «-»."""
    return "-" if value is None else format(value, spec)


def mean_or_none(values):
    """Среднее по списку, игнорируя None (если нечего усреднять — None)."""
    vals = [v for v in values if v is not None]
    return float(np.mean(vals)) if vals else None


def cleaner_params(cleaner, angles, radii):
    """
    Единый набор «порогов» для протокола.

    У AutoOutlierCleaner это вычисленные автопороги (params_), у ручного
    OutlierCleaner — заданные руками значения плюс измеренный разброс (MAD).
    """
    if cleaner is None:
        return {}
    if hasattr(cleaner, "params_"):
        return dict(cleaner.params_)
    st = cleaner.stats(angles, radii)
    return {
        "mad_value_mm": st.get("mad_value"),
        "threshold_deriv_mm": cleaner.threshold_deriv,
        "mad_k": cleaner.mad_k,
        "z_threshold": cleaner.z_threshold,
    }


def describe_params(params):
    """Короткая строка с автопорогами (мм и сигмы) для протокола."""
    if not params:
        return "-"
    bits = []
    for key in ("threshold_mm", "threshold_deriv_mm", "sigma_res_mm",
                "sigma_diff_mm", "iqr_res_mm", "mad_value_mm"):
        value = params.get(key)
        if value is not None:
            bits.append(f"{key}={value:.3f}")
    for key in ("z_threshold", "k_sigma", "iqr_k", "deriv_k"):
        value = params.get(key)
        if value is not None:
            bits.append(f"{key}={value:g}")
    if params.get("baseline_window_points"):
        bits.append(f"baseline_pts={params['baseline_window_points']}")
    if params.get("hampel_window_points"):
        bits.append(f"hampel_pts={params['hampel_window_points']}")
    return ", ".join(bits) if bits else "-"


# ============================================================================
# ОЦЕНКА МЕТОДА НА ОДНОМ СЕЧЕНИИ
# ============================================================================

def evaluate_method(cleaner_cfg, sec, ctx, tuned_cfg, model_cfg):
    """
    Прогоняет один режим очистки по одному сечению.

    cleaner_cfg = "raw"  — без очистки (базовая линия);
    cleaner_cfg = None   — метод с автоподбором порога (tune по сеточной RMSE);
    иначе                — секция конфига для build_cleaner().
    """
    a = sec["angles"]
    r = sec["radii"]
    truth = sec["truth"]
    tuned_rows = None

    if cleaner_cfg == "raw":
        cleaner = None
        mask = np.zeros(len(a), dtype=bool)
    elif cleaner_cfg is None:
        cleaner = AutoOutlierCleaner(method=tuned_cfg["method"],
                                     **tuned_cfg.get("kwargs", {}))

        def score_fn(a_kept, r_kept):
            return fit_grid_rmse(a_kept, r_kept, ctx["grid"], ctx["ideal_grid"],
                                 model_cfg)

        tuned_rows = cleaner.tune(a, r, score_fn,
                                  candidates=tuned_cfg["candidates"])
        mask = cleaner.clean(a, r)
    else:
        cleaner = build_cleaner(cleaner_cfg)
        mask = cleaner.clean(a, r)

    metrics = mask_metrics(mask, truth)
    win = in_window(a, ctx["pit_angle"], ctx["pit_window_deg"])
    pit_noise = win & (~truth if truth is not None else np.ones(len(a), dtype=bool))

    result = {
        "n_total": int(len(a)),
        "n_out": int(mask.sum()),
        "percent_out": 100.0 * float(mask.sum()) / len(a),
        "lost_near_pit": int(np.sum(mask & pit_noise)),
        "params": cleaner_params(cleaner, a, r),
        "tuned_rows": tuned_rows,
    }
    result.update(metrics)
    result["rmse_ideal"] = fit_grid_rmse(a[~mask], r[~mask], ctx["grid"],
                                         ctx["ideal_grid"], model_cfg)
    result["rmse_raw"] = fit_grid_rmse(a[~mask], r[~mask], ctx["grid"],
                                       ctx["raw_grid"], model_cfg)
    result["mask"] = mask
    result["cleaner"] = cleaner
    return result


def make_ctx(sec, grid, cfg):
    """Общий контекст сечения: сетка, эталон на сетке, сырые точки, дно ямы."""
    return {
        "grid": grid,
        "pit_window_deg": cfg["pit_window_deg"],
        "ideal_grid": ring_interp(sec["angles"], sec["ideal"], grid),
        "raw_grid": ring_interp(sec["angles"], sec["radii"], grid),
        "pit_angle": deepest_pit(sec["angles"], sec["ideal"]),
    }


def hampel_window_sweep(cfg, sections, grid):
    """Чувствительность фильтра Хампеля к окну (два варианта масштаба)."""
    rows = []
    for w in cfg["hampel_window_sweep"]:
        f1_local, f1_global, rmses = [], [], []
        for sid in cfg["sections"]:
            sec = sections[sid]
            ctx = make_ctx(sec, grid, cfg)
            for scale, bucket in (("local", f1_local), ("global", f1_global)):
                cleaner = AutoOutlierCleaner(method="hampel", hampel_window=w,
                                             hampel_scale=scale)
                mask = cleaner.clean(sec["angles"], sec["radii"])
                bucket.append(mask_metrics(mask, sec["truth"])["f1"])
                if scale == "global":
                    rmses.append(fit_grid_rmse(sec["angles"][~mask],
                                               sec["radii"][~mask], grid,
                                               ctx["ideal_grid"], cfg["model"]))
        rows.append({"window": w,
                     "f1_local": float(np.mean(f1_local)),
                     "f1_global": float(np.mean(f1_global)),
                     "rmse_global": float(np.mean(rmses))})
    return rows


# ============================================================================
# ГРАФИКИ
# ============================================================================

def plot_report(cfg, sections, zoom_ctx, zoom_results, all_results, window_rows,
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


# ============================================================================
# ОСНОВНОЙ СЦЕНАРИЙ
# ============================================================================

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
    plot_report(cfg, sections, zoom_ctx, zoom_results, all_results, window_rows,
                out_png)
    print(f"\nГрафик: {out_png}")


# ============================================================================
# ПЕЧАТЬ ОТЧЁТА
# ============================================================================

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


if __name__ == "__main__":
    main()