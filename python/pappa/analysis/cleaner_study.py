# вырезано из compare_cleaner_auto_src.py (рефакторинг, см. CONTEXT.md §21)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
from ..core.outlier_cleaner import AutoOutlierCleaner, build_cleaner
from ..core.patch_approximator import PatchApproximator
from ..io.dataset import ring_interp

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
