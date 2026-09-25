# вырезано из _src_pit_feature.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .layout import section_crack_zones
from ..io.dataset import attach_ideal_grid, load_sections, ring_interp
from ..paths import resolve_path
from ..core.pit_feature import MODEL_DEFAULTS, build_model
from ..viz.pit_figs import VARIANTS

def model_kwargs(cfg):
    """
    Параметры модели из CONFIG исследования; недостающие берутся из
    MODEL_DEFAULTS (единый источник раскладки — N=7, phase 24.75°, допуски,
    см. appa/core/pit_feature.py и CONTEXT §27).
    """
    m = dict(MODEL_DEFAULTS)
    m.update(cfg.get("model", {}))
    m["n_patches"] = cfg.get("n_patches", m["n_patches"])
    m["phase_deg"] = cfg.get("phase_deg", m["phase_deg"])
    return m


def fit_variant(cfg, sec, pits, variant):
    """
    Обучить один вариант модели на сечении. variant:
      "poly"    — текущая модель (только полином);
      "pit_raw" — полином + чистый гаусс (как было, без окна);
      "pit_win" — полином + оконный гаусс (сшивка с полиномом, предлагается).

    Степени у всех вариантов ОДИНАКОВЫЕ: у "poly" — правило «локтя» базовой
    модели, у pit-вариантов степень берётся такая же (degree_with_pits=False),
    чтобы сравнивался только способ описания ямы.

    Модель собирается через единую точку сборки build_model() — чтобы N, фаза
    и форма ямы не разъезжались между исследованиями и пайплайном.
    """
    kw = model_kwargs(cfg)
    if variant == "poly":
        ap = build_model(kw, pits=None)
    else:
        ap = build_model(dict(kw,
                              sigma_deg=cfg["sigma_deg"],
                              pit_core_sigma=cfg["pit_core_sigma"],
                              pit_window_sigma=cfg["pit_window_sigma"],
                              pit_min_amp=cfg["pit_min_amp"],
                              tapering=(variant == "pit_win")),
                         pits=pits)
    ap.fit(sec["angles_clean"], sec["radii_clean"])
    return ap


def measure(ap, grid, sec, pits):
    """Метрики модели на сетке: RMSE/MAE/max|Δ| по кольцу и у ям."""
    y = ap.eval(grid)
    res = y - sec["ideal_grid"]
    m = {"rmse": float(np.sqrt(np.mean(res ** 2))),
         "mae": float(np.mean(np.abs(res))),
         "max_err": float(np.max(np.abs(res))),
         "degrees": [int(d) for d in ap.degrees_],
         "n_coefs": int(sum(len(p['coefs']) + len(p.get('pit_coefs', []))
                            for p in ap.patches_))}
    if pits:
        near = np.zeros(len(grid), dtype=bool)
        for p in pits:
            near |= np.abs((grid - p + 180.0) % 360.0 - 180.0) <= 5.0
        m["peak_at_pit"] = float(np.max(np.abs(res[near]))) if near.any() else 0.0
    else:
        m["peak_at_pit"] = 0.0
    return m


def pit_crop_info(cfg, sections, zones_by_section, models):
    """
    По каждому сечению — список ям для КРУПНЫХ ПЛАНОВ: {sid: [ {...}, ... ]}.

    Полуширина кропа = окно фичера (window_sigma·sigma) + crop_margin_deg, то есть
    в кадр попадают и дно ямы, и участок ЧИСТОГО полинома за окном (выход ямы в
    полином). Ямы сортируются по ЛОКАЛЬНОЙ глубине (медиана плеч ±(w+3…w+12)°
    минус минимум в ядре |Δ| <= w+1°) — так глубина не смешивается с общим
    наклоном профиля; в рисунок идут max_crops самых глубоких.

    Для каждой ямы считается ЧИСЛОВАЯ проверка сшивки: максимальная кривизна
    |r''| остатка на выходе из ямы (1.5σ <= |Δ| <= край кропа) для pit_raw и
    pit_win. Меньше — плавнее выход в полином; именно по этому числу сшивка и
    проверяется (картинки при работе не рассматриваются).
    """
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]
    crop_half = win + cfg["crop_margin_deg"]
    step = 360.0 / cfg["grid_points"]
    n_loc = 2 * int(round(crop_half / step)) + 1        # нечётное -> 0 в центре
    out = {}
    for sid in cfg["sections"]:
        s = sections[sid]
        # швы (стыки патчей) и вклад фичера по всему кольцу — для проверки сшивки
        chain = models[sid]["pit_win"]
        nodes = np.array([(c + chain.half_sector_) % 360.0 for c in chain.centers_])
        full = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
        d_node = np.min(np.abs((full[:, None] - nodes[None, :] + 180.0)
                               % 360.0 - 180.0), axis=1)
        seam = d_node <= chain.overlap_use      # зона перекрытия: два патча
        pit_full = {v: models[sid][v].eval_part(full, "pit")
                    for v in ("pit_raw", "pit_win")}

        items = []
        for a, b in zones_by_section[sid]:
            c = 0.5 * (a + b)
            w = 0.5 * (b - a)
            dl = np.abs((s["angles_clean"] - c + 180.0) % 360.0 - 180.0)
            shoulder = (dl >= w + 3.0) & (dl <= w + 12.0)
            core = dl <= w + 1.0
            depth = (float(np.median(s["radii_clean"][shoulder])
                           - np.min(s["radii_clean"][core]))
                     if shoulder.any() and core.any() else 0.0)

            loc = np.linspace(-crop_half, crop_half, n_loc)
            glob = (c + loc) % 360.0
            ideal = ring_interp(s["angles"], s["ideal"], glob)
            curves = {v: models[sid][v].eval(glob) for v, _ in VARIANTS}
            resid = {v: curves[v] - ideal for v, _ in VARIANTS}
            i0 = int(np.argmin(np.abs(loc)))            # дно ямы

            # где фичер реально живёт: 1e-6 мм — порог «вклад ещё есть».
            # Соседние ямы исключаем (у них своё окно), иначе их вклад
            # приписывается этой яме.
            d_full = np.abs((full - c + 180.0) % 360.0 - 180.0)
            others = [0.5 * (aa + bb) for aa, bb in zones_by_section[sid]
                      if abs(((aa + bb) * 0.5 - c + 180.0) % 360.0 - 180.0) > 1e-6]
            if others:
                oth = np.asarray(others, dtype=float)
                d_other = np.min(np.abs((full[:, None] - oth[None, :] + 180.0)
                                        % 360.0 - 180.0), axis=1)
            else:
                d_other = np.full(full.shape, 999.0)
            local = (d_full <= 60.0) & (d_other > win)
            span, seam_pit = {}, {}
            for v in ("pit_raw", "pit_win"):
                vis = local & (np.abs(pit_full[v]) > 1e-6)
                span[v] = float(np.max(d_full[vis])) if vis.any() else 0.0
                both = local & seam
                seam_pit[v] = (float(np.max(np.abs(pit_full[v][both])))
                               if both.any() else 0.0)
            # запас окна фичера до ЗОНЫ ПЕРЕКРЫТИЯ (шов ± overlap_use): > 0 — окно
            # целиком внутри плато одного патча (амплитуду ямы никто не делит)
            gap = float(np.min(np.abs((nodes - c + 180.0) % 360.0 - 180.0))
                        - chain.overlap_use - win)
            items.append({"angle": float(c), "width": float(2.0 * w),
                          "depth": depth, "crop_half": float(crop_half),
                          "loc": loc, "ideal": ideal, "curves": curves,
                          "resid": resid,
                          "resid_center": {v: float(resid[v][i0])
                                           for v, _ in VARIANTS},
                          "span": span, "seam_pit": seam_pit, "seam_gap": gap})
        items.sort(key=lambda it: -it["depth"])
        out[sid] = items[:cfg["max_crops"]]
    return out
