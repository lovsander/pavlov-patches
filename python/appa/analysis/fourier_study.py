"""
appa.analysis.fourier_study — «Фурье малой степени + фичер ям»: сравнение с
методом поли-патчей.

Зачем: проверить гипотезу «может, хватит ряда Фурье 4-6 гармоник, если ямы
дорисовывать тем же оконным гауссом, и тогда наш метод патчей не нужен».

Три способа сшивки Фурье и фичера:
  fourier  — только Фурье (K гармоник), никаких ям: база «как есть»;
  joint    — Фурье + гауссовы ямы подбираются ОДНИМ МНК по всем точкам.
             Фурье «видит» ямы и частично их догоняет — ряд искажается
             (глобальные волны), у ям появляются «качели»;
  masked   — Фурье учится ТОЛЬКО на точках вне окон ям (ям для него не
             существует), затем при ЗАМОРОЖЕННОМ Фурье по всем точкам
             подбираются только амплитуды ям. База идёт по линии, яму рисует
             исключительно фичер — то, что хотел пользователь.

Модель линейна по всем коэффициентам (Фурье + амплитуды гауссов), поэтому
решается обычным МНК. Форма ямы — общая с патчами: appa.core.pit_feature.
pit_shape_deg (ядро 2σ, плавный уход в 0 к 3.2σ).
"""

import numpy as np

from ..core.pit_feature import pit_shape_deg
from ..io.dataset import ring_interp


def fourier_basis(angles_deg, n_harm):
    """Матрица базиса ряда Фурье: [1, cos θ, sin θ, cos 2θ, sin 2θ, ...]."""
    t = np.deg2rad(np.asarray(angles_deg, dtype=float))
    cols = [np.ones_like(t)]
    for k in range(1, int(n_harm) + 1):
        cols.append(np.cos(k * t))
        cols.append(np.sin(k * t))
    return np.column_stack(cols)


def dist_to_pits(angles_deg, pits):
    """Минимальное круговое расстояние до центров ям, °."""
    a = np.asarray(angles_deg, dtype=float)
    if not len(pits):
        return np.full(a.shape, 180.0)
    p = np.asarray(pits, dtype=float)
    return np.min(np.abs((a[:, None] - p[None, :] + 180.0) % 360.0 - 180.0),
                  axis=1)


class FourierPitModel:
    """Готовая модель: Фурье-коэффициенты + амплитуды оконных гауссов в ямах."""

    def __init__(self, n_harm, fcoefs, pits, amps, mode, sigma_deg=3.0,
                 core_sigma=2.0, window_sigma=3.2, tapering=True, n_fit=0,
                 mask_deg=None):
        self.n_harm = int(n_harm)
        self.fcoefs = np.asarray(fcoefs, dtype=float)
        self.pits = [float(p) % 360.0 for p in pits]
        self.amps = np.asarray(amps, dtype=float)
        self.mode = mode
        self.sigma_deg = float(sigma_deg)
        self.core_sigma = float(core_sigma)
        self.window_sigma = float(window_sigma)
        self.tapering = bool(tapering)
        self.n_fit = int(n_fit)          # сколько точек реально учило Фурье
        self.mask_deg = mask_deg         # радиус исключения точек (для masked)

    def eval_fourier(self, angles_deg):
        return fourier_basis(angles_deg, self.n_harm) @ self.fcoefs

    def eval_pits(self, angles_deg):
        a = np.asarray(angles_deg, dtype=float)
        out = np.zeros(a.shape, dtype=float)
        for c, amp in zip(self.pits, self.amps):
            d = np.abs((a - c + 180.0) % 360.0 - 180.0)
            out += amp * pit_shape_deg(d, self.sigma_deg, self.core_sigma,
                                       self.window_sigma, self.tapering)
        return out

    def eval(self, angles_deg):
        return self.eval_fourier(angles_deg) + self.eval_pits(angles_deg)


def _pit_cols(cfg, x, pits):
    """Столбцы оконных гауссов для точек x (пусто, если ям нет)."""
    if not pits:
        return np.zeros((len(x), 0))
    cols = []
    for c in pits:
        d = np.abs((x - c + 180.0) % 360.0 - 180.0)
        cols.append(pit_shape_deg(d, cfg["sigma_deg"], cfg["pit_core_sigma"],
                                  cfg["pit_window_sigma"],
                                  cfg.get("tapering", True)))
    return np.column_stack(cols)


def fit_fourier_pit(cfg, angles, radii, pits, n_harm, mode):
    """
    Обучить модель. mode: "fourier" | "joint" | "masked" (см. docstring модуля).

    Ямы берутся из детектора (центры зон-трещин), их полуширина — из cfg
    (sigma_deg, pit_core_sigma, pit_window_sigma).
    """
    sigma = cfg["sigma_deg"]
    core = cfg["pit_core_sigma"]
    win = cfg["pit_window_sigma"]
    window_deg = win * sigma
    a = np.asarray(angles, dtype=float)
    r = np.asarray(radii, dtype=float)
    pits = [float(p) % 360.0 for p in pits]
    common = {"sigma_deg": sigma, "core_sigma": core, "window_sigma": win,
              "tapering": cfg.get("tapering", True)}

    if mode == "fourier":
        coef, *_ = np.linalg.lstsq(fourier_basis(a, n_harm), r, rcond=None)
        return FourierPitModel(n_harm, coef, [], np.zeros(0), mode,
                               n_fit=len(a), **common)

    if mode == "joint":
        A = np.column_stack([fourier_basis(a, n_harm), _pit_cols(cfg, a, pits)])
        coef, *_ = np.linalg.lstsq(A, r, rcond=None)
        nf = 2 * int(n_harm) + 1
        return FourierPitModel(n_harm, coef[:nf], pits, coef[nf:], mode,
                               n_fit=len(a), **common)

    if mode == "masked":
        # 1) Фурье учится только на «чистых» точках (ям не видит)
        mask = dist_to_pits(a, pits) > window_deg
        coef, *_ = np.linalg.lstsq(fourier_basis(a[mask], n_harm), r[mask],
                                   rcond=None)
        # 2) при замороженном Фурье подбираем только амплитуды ям — по ВСЕМ точкам
        base = fourier_basis(a, n_harm) @ coef
        P = _pit_cols(cfg, a, pits)
        amps = (np.linalg.lstsq(P, r - base, rcond=None)[0]
                if P.shape[1] else np.zeros(0))
        return FourierPitModel(n_harm, coef, pits, amps, mode,
                               n_fit=int(np.count_nonzero(mask)),
                               mask_deg=float(window_deg), **common)

    raise ValueError(f"неизвестный режим: {mode}")


def measure(model, grid, ideal_grid, cfg, pits):
    """Метрики модели: RMSE по кольцу, ошибка у ям (в окне фичера)."""
    res = model.eval(grid) - ideal_grid
    out = {"rmse": float(np.sqrt(np.mean(res ** 2))),
           "max_err": float(np.max(np.abs(res)))}
    if pits:
        near = (dist_to_pits(grid, pits)
                <= cfg["pit_window_sigma"] * cfg["sigma_deg"])
        out["peak_at_pit"] = float(np.max(np.abs(res[near]))) if near.any() else 0.0
    else:
        out["peak_at_pit"] = 0.0
    return out


def base_drift(ref, other, grid, cfg, pits):
    """
    Насколько «поехала» база (Фурье-часть) из-за ям: (макс. |Δ| вне окон ям, мм;
    относительное изменение коэффициентов). ref — база «как надо» (Фурье,
    обученный без ям), other — проверяемая.
    """
    outside = (dist_to_pits(grid, pits)
               > cfg["pit_window_sigma"] * cfg["sigma_deg"])
    dy = np.abs(ref.eval_fourier(grid)[outside] - other.eval_fourier(grid)[outside])
    n = min(len(ref.fcoefs), len(other.fcoefs))
    rel = float(np.linalg.norm(ref.fcoefs[:n] - other.fcoefs[:n])
                / max(np.linalg.norm(ref.fcoefs[:n]), 1e-12))
    return (float(np.max(dy)) if outside.any() else 0.0, rel)


def sweep_orders(cfg, sections, pits_by_section, orders, grid):
    """
    Развёртка по числу гармоник: средние RMSE и ошибка у ям для трёх режимов.

    Отвечает на вопрос «при каком числе гармоник Фурье (+фичер) догоняет патчи»
    и «узкое место — ямы или сама база». Возвращает
    {order: {"fourier": (rmse, peak), "joint": (...), "masked": (...)}}.
    """
    out = {}
    for order in orders:
        acc = {m: [] for m in ("fourier", "joint", "masked")}
        for sid in cfg["sections"]:
            s = sections[sid]
            pits = pits_by_section[sid]
            for mode in acc:
                model = fit_fourier_pit(cfg, s["angles_clean"],
                                        s["radii_clean"], pits, order, mode)
                acc[mode].append(measure(model, grid, s["ideal_grid"], cfg, pits))
        out[order] = {m: (float(np.mean([r["rmse"] for r in rs])),
                          float(np.mean([r["peak_at_pit"] for r in rs])))
                      for m, rs in acc.items()}
    return out


def crop_data(cfg, sections, zones_by_section, models, sids, crop_half_deg,
              n=601):
    """
    Данные для крупных планов ям: точки, эталон и кривые всех моделей.

    models[sid] — словарь {имя: объект с .eval(angles)}. Возвращает
    {sid: [ {angle, width, depth, loc, ideal, curves, pts_a, pts_r}, ... ]},
    ямы отсортированы по локальной глубине (плечи ±(w+3..w+12)° минус ядро).
    """
    out = {}
    for sid in sids:
        s = sections[sid]
        items = []
        for a, b in zones_by_section[sid]:
            c, w = 0.5 * (a + b), 0.5 * (b - a)
            dl = np.abs((s["angles_clean"] - c + 180.0) % 360.0 - 180.0)
            shoulder = (dl >= w + 3.0) & (dl <= w + 12.0)
            core = dl <= w + 1.0
            depth = (float(np.median(s["radii_clean"][shoulder])
                           - np.min(s["radii_clean"][core]))
                     if shoulder.any() and core.any() else 0.0)
            loc = np.linspace(-crop_half_deg, crop_half_deg, n)
            glob = (c + loc) % 360.0
            near = np.abs((s["angles_clean"] - c + 180.0) % 360.0 - 180.0) \
                <= crop_half_deg
            items.append({
                "angle": float(c), "width": float(2.0 * w), "depth": depth,
                "loc": loc, "glob": glob,
                "ideal": ring_interp(s["angles"], s["ideal"], glob),
                "curves": {k: m.eval(glob) for k, m in models[sid].items()},
                "pts_a": (s["angles_clean"][near] - float(c)),
                "pts_r": s["radii_clean"][near],
            })
        items.sort(key=lambda it: -it["depth"])
        out[sid] = items
    return out

