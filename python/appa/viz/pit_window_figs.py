"""
appa.viz.pit_window_figs — рисунки для решения «окно фичера vs фаза».

Рис. 1 (pit_window_geometry.png) — ГЕОМЕТРИЯ, без подгонок:
  профили веса окна 3.2σ / 2.5σ / 2.0σ (тот самый «вектор» весов);
  «какая максимальная полуширина окна ещё не задевает шов» по каждой яме;
  суммарное перекрытие окон ям с зоной сшивки по сечениям для 4 вариантов;
  развёртка кольца для худшего сечения: зоны трещин, плато патчей, зоны сшивки,
  окна ям при общей фазе / своей фазе / фазе «под ямы».

Рис. 2 (pit_window_fits.png) — ПОДГОНКИ на точках: строки — сечения,
  столбцы — самая глубокая яма и яма с худшей геометрией; кривые — прежний вид
  (общая фаза, 3.2σ), 2.5σ, своя фаза, своя фаза + 2.5σ, фаза «под ямы».
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..analysis.pit_window_study import window_profile
from ..core.geometry import node_angles, patch_centers

TONE = {"ok": "#009E73", "tight": "#E69F00", "bad": "#D55E00", "none": "#8B0000"}


def _tone(margin):
    if margin >= 9.6:
        return TONE["ok"]
    if margin >= 7.5:
        return TONE["tight"]
    if margin >= 6.0:
        return TONE["bad"]
    return TONE["none"]


def draw_window_profiles(ax, cfg):
    """Профиль веса окна фичера: 3.2σ (прежний, ±9.6°), 2.5σ, 2.0σ."""
    d = np.linspace(-13.0, 13.0, 1201)
    for wsig, style in ((3.2, "-"), (2.5, "--"), (2.0, ":")):
        w = wsig * cfg["sigma_deg"]
        ax.plot(d, window_profile(d, wsig, cfg["sigma_deg"],
                                  cfg["pit_core_sigma"]),
                style, lw=1.8, label=f"окно {wsig:g}σ = ±{w:.1f}°")
    core = cfg["pit_core_sigma"] * cfg["sigma_deg"]
    for x in (-core, core):
        ax.axvline(x, color="0.4", lw=0.9, ls=(0, (5, 3)))
    ax.axvspan(-cfg["model"]["overlap_use"], cfg["model"]["overlap_use"],
               color="tab:red", alpha=0.12, lw=0.0)
    ax.text(0, 0.06, "зона сшивки\n±5° вокруг шва", ha="center", fontsize=7.5,
            color="tab:red")
    ax.set_xlabel("Расстояние от центра ямы, °")
    ax.set_ylabel("вес оконного гаусса")
    ax.set_title("Профиль веса («вектор») фичера: где он реально живёт\n"
                 "пунктир — край ядра 2σ (дно не искажаем), красное — зона сшивки",
                 fontsize=9.5)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")


def draw_pit_thresholds(ax, rows, cfg):
    """
    По каждой яме: расстояние до ближайшего шва минус половина зоны сшивки =
    максимальная полуширина окна, которая ещё не задевает шов. Пороги — окна
    3.2σ / 2.5σ / 2.0σ.
    """
    x = np.arange(len(rows))
    vals = [r["dist_shared"] - cfg["model"]["overlap_use"] for r in rows]
    ax.bar(x, vals, 0.75, color=[_tone(v) for v in vals], alpha=0.85)
    for lvl, lbl, col in ((3.2 * cfg["sigma_deg"], "окно 3.2σ", "#0072B2"),
                          (2.5 * cfg["sigma_deg"], "окно 2.5σ", "#E69F00"),
                          (2.0 * cfg["sigma_deg"], "окно 2.0σ", "#D55E00")):
        ax.axhline(lvl, color=col, lw=1.3, ls=(0, (6, 2)), label=lbl)
    labels, last = [], None
    for r in rows:
        if r["section"] != last:
            labels.append(f"сеч. {r['section']}\n{r['pit']:.1f}°")
            last = r["section"]
        else:
            labels.append(f"{r['pit']:.1f}°")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=6.2, rotation=90)
    ax.set_ylabel("запас до шва, ° (без зоны сшивки)")
    ax.set_title("Сколько «полуокна» влезает до зоны сшивки для каждой ямы\n"
                 "столбик ниже порога — окно такой ширины заезжает в сшивку",
                 fontsize=9.5)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=7.5, loc="upper right")


def draw_overlap_by_section(ax, per_section):
    """Суммарное перекрытие окон ям с зоной сшивки по сечениям, 4 варианта."""
    sids = sorted(per_section)
    x = np.arange(len(sids))
    w = 0.2
    keys = [("shared", 3.2, "общая фаза, окно 3.2σ", "#0072B2"),
            ("shared", 2.5, "общая фаза, окно 2.5σ", "#56B4E9"),
            ("own", 3.2, "своя фаза, окно 3.2σ", "#E69F00"),
            ("best", 3.2, "фаза «под ямы», окно 3.2σ", "#009E73")]
    for i, (key, wsig, lbl, col) in enumerate(keys):
        vals = [per_section[s][key][wsig]["sum_overlap"] for s in sids]
        ax.bar(x + (i - 1.5) * w, vals, w, color=col, alpha=0.85, label=lbl)
        for xi, v in zip(x + (i - 1.5) * w, vals):
            ax.text(xi, v, f"{v:.1f}", ha="center", va="bottom", fontsize=6.0,
                    rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels([f"сеч. {s}" for s in sids], fontsize=8)
    ax.set_ylabel("суммарное перекрытие, ° (0 = чисто)")
    ax.set_title("Насколько окна ям заезжают в зону сшивки (сумма по ямам)\n"
                 "общая фаза 24.75° против своей фазы и фазы «под ямы»",
                 fontsize=9.5)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(fontsize=7.5, loc="upper right")


def draw_phase_strips(ax, cfg, zones, pits, phases, n_patches, labels):
    """
    Развёртка кольца: зоны трещин (красное), плато патчей (синее), зоны сшивки
    (серые штриховые) и окна ям (оранжевое) — по строке на вариант фазы.
    """
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]
    ou = cfg["model"]["overlap_use"]
    half = 180.0 / n_patches
    m = len(phases)

    for a, b in zones:
        ax.axvspan(a, b, ymin=0.0, ymax=1.0, color="tab:red", alpha=0.16, lw=0.0)
    for k, (ph, lbl) in enumerate(zip(phases, labels)):
        y0, y1 = 1.0 - (k + 0.62) / m, 1.0 - (k + 0.30) / m
        for c in patch_centers(n_patches, ph):
            ax.axvspan(c - half, c + half, ymin=y0, ymax=y1, color="#0072B2",
                       alpha=0.15, lw=0.0)
        for nd in node_angles(n_patches, ph):
            ax.axvspan(nd - ou, nd + ou, ymin=y0, ymax=y1, color="0.3",
                       alpha=0.45, lw=0.0)
        yw0, yw1 = 1.0 - (k + 0.98) / m, 1.0 - (k + 0.66) / m
        for c in pits:
            ax.axvspan(c - win, c + win, ymin=yw0, ymax=yw1, color="#D55E00",
                       alpha=0.45, lw=0.0)
        ax.text(2.0, 0.5 * (y0 + yw1), lbl, fontsize=8, va="center")
    ax.set_xlim(0, 360)
    ax.set_xlabel("Угол, °")
    ax.set_yticks([])
    ax.set_title("Худшее сечение: окна ям против швов при разных фазах\n"
                 "синие полосы — плато патчей, тёмные — зоны сшивки, оранжевые — "
                 "окна ям", fontsize=9.5)


def draw_crop(ax, it, zones, zone_angle, win, variants, xlabel=False):
    """Крупный план ямы: точки, эталон и кривые всех вариантов."""
    half = it["loc"][-1]
    for a, b in zones:
        ca = ((a - zone_angle + 180.0) % 360.0) - 180.0
        cb = ((b - zone_angle + 180.0) % 360.0) - 180.0
        if cb < ca or cb < -half or ca > half:
            continue
        ax.axvspan(max(ca, -half), min(cb, half), color="tab:red", alpha=0.16,
                   lw=0.0, zorder=0)
    ax.axvspan(-win, win, color="0.35", alpha=0.10, lw=0.0, zorder=0)
    for x in (-win, win):
        ax.axvline(x, color="0.35", lw=0.9, ls=(0, (5, 3)), zorder=1)
    ax.plot(it["pts_a"], it["pts_r"], ".", color="gray", markersize=2.2,
            alpha=0.45, zorder=2, label="данные (очищенные)")
    ax.plot(it["loc"], it["ideal"], "-", color="black", lw=1.0, alpha=0.85,
            zorder=3, label="эталон")
    for key, st in variants.items():
        ax.plot(it["loc"], it["curves"][key], ls=st["ls"], color=st["color"],
                lw=st["lw"], zorder=4, label=st["label"])
    ax.set_xlim(-half, half)
    ax.grid(alpha=0.3)
    if xlabel:
        ax.set_xlabel("Угол к центру ямы, °")
    ax.set_ylabel("Радиус, мм")



def plot_window_geometry(cfg, rows, per_section, sections, zones_by_section,
                         pits_by_section, sid_worst, out_path):
    """Рис. 1: геометрия окна и фаз (профили, пороги, перекрытия, развёртка)."""
    fig, axes = plt.subplots(2, 2, figsize=(16.0, 10.0))

    draw_window_profiles(axes[0][0], cfg)
    draw_pit_thresholds(axes[0][1], rows, cfg)
    draw_overlap_by_section(axes[1][0], per_section)

    own = cfg["own_phase"]
    shared = cfg["phase_deg"]
    best = per_section[sid_worst]["best_phase"]
    draw_phase_strips(axes[1][1], cfg, zones_by_section[sid_worst],
                      pits_by_section[sid_worst],
                      [shared, own[sid_worst], best], cfg["n_patches"],
                      [f"общая фаза {shared:g}°",
                       f"своя фаза {own[sid_worst]:g}°",
                       f"«под ямы» {best:g}°"])

    fig.suptitle(
        "Окно фичера против фазы: геометрия (без подгонок)\n"
        f"звезда N = {cfg['n_patches']}, sigma = {cfg['sigma_deg']:g}°, ядро "
        f"{cfg['pit_core_sigma']:g}σ = ±{cfg['pit_core_sigma'] * cfg['sigma_deg']:.1f}°; "
        f"худшее сечение для окон ям — {sid_worst}", fontsize=12)
    plt.tight_layout(rect=(0, 0, 1, 0.93))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_window_fits(cfg, sections, zones_by_section, crops, rows_fits,
                     variants, out_path):
    """
    Рис. 2: подгонки на точках. Строки — сечения, столбцы — самая глубокая яма
    и яма с худшей геометрией; в заголовке — RMSE варианта по этому сечению.
    """
    secs = cfg["sections"]
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]
    fig, axes = plt.subplots(len(secs), 2, figsize=(17.0, 3.3 * len(secs)),
                             squeeze=False)

    for i, sid in enumerate(secs):
        deep, worst = crops[sid][0], crops[sid][1]
        for j, it in enumerate((deep, worst)):
            ax = axes[i][j]
            draw_crop(ax, it, zones_by_section[sid], it["angle"], win, variants,
                      xlabel=(i == len(secs) - 1))
            rmse = " | ".join(f"{k} {rows_fits[sid]['metrics'][k]['rmse']:.4f}"
                              for k in variants)
            ax.set_title(f"сечение {sid}: яма {it['angle']:.1f}° "
                         f"(зона {it['width']:.1f}°, глубина ~{it['depth']:.2f} мм)"
                         f" — {'самая глубокая' if j == 0 else 'худшая по шву'}\n"
                         f"RMSE: {rmse} мм", fontsize=9)
            if i == 0 and j == 0:
                ax.legend(fontsize=7.5, loc="best", framealpha=0.92)

    fig.suptitle(
        "Подгонки: прежний вид (общая фаза, окно 3.2σ) против окна 2.5σ, своей "
        "фазы и фазы «под ямы»\n"
        f"серый коридор — окно фичера ±{win:.1f}°, штриховые вертикали — его "
        "края, точки — очищенные данные", fontsize=11.5)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)

