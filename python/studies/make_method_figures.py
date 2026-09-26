"""make_method_figures.py — картинки для описания метода, его раскладки, выбора
степени, очистки и его сравнения с Фурье и локальной полиномиальной регрессией (LPR).

Что рисуется (в docs/assets/ — эти файлы коммитятся, .gitignore их пропускает):

  method_patches.png     метод «изнутри»: патчи на кольце, partition of unity
                         (smoothstep-веса), ошибка приближения;
  method_star.png        раскладка «звезда»: лучи-центры, швы, «обучение шире
                         применения» и фаза против трещин (отступ шва от ямы по
                         ВСЕМ сечениям файла);
  method_degrees.png     выбор степени: правило RMSE-«локтя» по каждому патчу и
                         цена против ошибки (одинаковая степень на всех патчах
                         против адаптивной);
  method_cleaning.png    авто-очистка выбросов: маска, severity против порога IQR
                         и что дала бы модель БЕЗ очистки (та же детектор/модель);
  method_detector.png    детектор band: индикатор в MAD-ах, порог, найденные зоны;
  method_vs_fourier.png  PAPPA против усечённого ряда Фурье (4/6/12/24 гармоники);
  method_vs_lpr.png      PAPPA против LPR с ФИКСИРОВАННЫМ окном (degree 1/2, h=2°/10°).

Числа (max|Δ|, RMSE, отступы швов, степени, счётчики очистки) печатаются в stdout:
их берут README и docs/method.md, чтобы текст и картинки не разъезжались. Там же
печатаются две самопроверки: зеркало правила «локтя» на рисунке даёт ровно те
степени, что модель, а маска очистки совпадает с прямым вызовом build_cleaner.

Почему сравнения вообще честные: все методы обучаются на ОДНИХ И ТЕХ ЖЕ точках
сечения из python/synthetic_data.csv и оцениваются на ОДНОЙ И ТОЙ ЖЕ сетке; Фурье и
LPR — без «подглядывания» в истину (radius_ideal_mm нужен только для счёта ошибки).

Запуск: <python с numpy и matplotlib> python/studies/make_method_figures.py
"""

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pappa.analysis.zones import detect_zones, indicator_curve
from pappa.core.geometry import node_angles
from pappa.core.outlier_cleaner import build_cleaner
from pappa.core.pit_feature import DETECTOR_DEFAULTS, MODEL_DEFAULTS, build_model
from pappa.io.dataset import attach_ideal_grid, load_sections

CSV = ROOT / "python" / "synthetic_data.csv"
OUT = ROOT / "docs" / "assets"
SECTION = 0
GRID = np.linspace(0.0, 360.0, 1441)[:-1]      # 0.25° — та же сетка, что у сверки порта
K_ZONES = float(DETECTOR_DEFAULTS["k"])
FIXED_DEGREES = (4, 6, 8, 10, 12, 14)          # «одна степень на все патчи» — §4: цена/ошибка
DPI = 130
# Тот же очиститель, что у пайплайна: сравнивать методы на «грязных» точках нельзя —
# выброс генератора испортит любой метод, и разницы между методами не будет видно.
CLEANER = {"mode": "auto", "auto": {"method": "iqr"}}


def load_section(section_id):
    """Сечение: очищенные точки, истина на сетке GRID и «сырьё» для рисунка очистки.

    Загрузчик берём референсный (pappa.io.dataset): он же применяет авто-очистку
    `iqr`, поэтому обучающая выборка у всех методов сравнения ОДНА И ТА ЖЕ, а
    `radius_ideal_mm` даёт честную ошибку на той же сетке.

    Возвращает (angles_clean, radii_clean, ideal_grid, raw), где raw — кортеж
    (angles_all, radii_all, mask) по возрастанию угла (маска True = выброс).
    """
    sections = load_sections(str(CSV), "radius_ideal_mm", CLEANER)
    attach_ideal_grid(sections, GRID)
    s = sections[section_id]
    a_all = np.asarray(s["angles"], dtype=float)
    r_all = np.asarray(s["radii"], dtype=float)
    mask = np.asarray(s["mask"], dtype=bool)
    a = np.asarray(s["angles_clean"], dtype=float)
    r = np.asarray(s["radii_clean"], dtype=float)
    ideal = np.asarray(s["ideal_grid"], dtype=float)
    order = np.argsort(a, kind="stable")
    return a[order], r[order], ideal, (a_all, r_all, mask)



def errors(truth, got):
    d = np.asarray(got, dtype=float) - np.asarray(truth, dtype=float)
    return float(np.max(np.abs(d))), float(np.sqrt(np.mean(d * d)))


# ---------------------------------------------------------------- базовые методы

def make_fourier(angles_deg, radii, order):
    """Усечённый ряд Фурье: 1 + order·(sin kθ, cos kθ), МНК по тем же точкам."""
    t = np.radians(np.asarray(angles_deg, dtype=float))

    def basis(theta):
        cols = [np.ones_like(theta)]
        for k in range(1, order + 1):
            cols += [np.sin(k * theta), np.cos(k * theta)]
        return np.column_stack(cols)

    c, *_ = np.linalg.lstsq(basis(t), radii, rcond=None)
    return (lambda grid: basis(np.radians(np.asarray(grid, dtype=float))) @ c,
            int(1 + 2 * order))


def make_lpr(angles_deg, radii, grid, half_deg, deg):
    """LPR с фиксированным окном: своя полиномиальная подгонка в каждой точке сетки.

    Окно задано в ГРАДУСАХ и одинаково на всём кольце — это ровно то, чем LPR
    отличается от патчей: ни степень, ни форма окна не адаптируются к дефекту.
    Локальная координата нормируется на полуширину окна, как у патчей PAPPA.
    """
    a = np.asarray(angles_deg, dtype=float)
    r = np.asarray(radii, dtype=float)
    grid = np.asarray(grid, dtype=float)
    out = np.empty_like(grid)
    for i, g in enumerate(grid):
        dx = (a - g + 180.0) % 360.0 - 180.0
        m = np.abs(dx) <= half_deg
        if np.count_nonzero(m) < deg + 2:
            out[i] = np.mean(r[m]) if np.any(m) else np.mean(r)
            continue
        x = dx[m] / half_deg
        A = np.vander(x, deg + 1, increasing=True)
        c, *_ = np.linalg.lstsq(A, r[m], rcond=None)
        out[i] = c[0]                      # значение полинома в самом g (x = 0)
    return out


# ------------------------------------------------------------- геометрия патчей

def patch_layout():
    """Центры патчей и веса: те же формулы, что у порта и референса."""
    n = int(MODEL_DEFAULTS["n_patches"])
    phase = float(MODEL_DEFAULTS["phase_deg"])
    sector = 360.0 / n
    half_sector = sector / 2.0
    half_use = half_sector + float(MODEL_DEFAULTS.get("overlap_use", 5.0))
    centers = np.array([(i * sector + half_sector + phase) % 360.0 for i in range(n)])
    return centers, half_sector, half_use, float(MODEL_DEFAULTS.get("overlap_train", 15.0))


def weight(d_deg, half_sector, half_use):
    """Вес патча: 1 в своём секторе, smoothstep к нулю на перекрытии."""
    d = np.asarray(d_deg, dtype=float)
    w = np.zeros_like(d)
    w[d <= half_sector] = 1.0
    mid = (d > half_sector) & (d <= half_use)
    t = 1.0 - (d[mid] - half_sector) / (half_use - half_sector)
    w[mid] = t * t * (3.0 - 2.0 * t)
    return w


def circ_dist(a, b):
    d = (np.asarray(a, dtype=float) - float(b) + 180.0) % 360.0 - 180.0
    return np.abs(d)


def interp_ring(angles_deg, values, grid):
    """Интерполяция по кольцу: данные периодичны, копия сдвинута на ±360°."""
    a = np.asarray(angles_deg, dtype=float)
    v = np.asarray(values, dtype=float)
    xs = np.concatenate([a - 360.0, a, a + 360.0])
    ys = np.concatenate([v, v, v])
    return np.interp(np.asarray(grid, dtype=float), xs, ys)


# ------------------------------------------- раскладка «звезда» и её отступы

def margin_to_seam(pits, n_patches, phase_deg):
    """Отступ каждого центра ямы от ближайшего ШВА (узла), °. < 0 — шов в яме."""
    nodes = node_angles(n_patches, phase_deg)
    return [float(np.min(circ_dist(nodes, p))) for p in pits]


def detect_all_sections():
    """Ямы по ВСЕМ сечениям файла — тем же детектором band, что в пайплайне.

    Раскладка патчей ОДНА на всё тело, поэтому «шов не на трещине» надо судить
    по всем сечениям сразу: фаза может быть безопасной в одном и плохой в другом.
    """
    sections = load_sections(str(CSV), "radius_ideal_mm", CLEANER)
    out = []
    for sid in sorted(sections):
        s = sections[sid]
        a = np.asarray(s["angles_clean"], dtype=float)
        r = np.asarray(s["radii_clean"], dtype=float)
        order = np.argsort(a, kind="stable")
        a, r = a[order], r[order]
        ind = indicator_curve(a, r, DETECTOR_DEFAULTS["kind"],
                              window_deg=DETECTOR_DEFAULTS["window_deg"],
                              envelope_deg=0.5,
                              smooth_deg=DETECTOR_DEFAULTS["smooth_deg"],
                              wide_deg=DETECTOR_DEFAULTS["wide_deg"])
        zones = detect_zones(a, ind, DETECTOR_DEFAULTS["k"],
                             min_len_deg=DETECTOR_DEFAULTS["min_zone_deg"])
        out.append((sid, [0.5 * (z[0] + z[1]) for z in zones]))
    return out


# ------------------------------------------- выбор степени: «локоть» и цена/ошибка

def degree_curve(angles, radii, center, model):
    """RMSE(deg) на обучающем окне патча — зеркало правила «локтя» (§4).

    Считается РОВНО так же, как PatchApproximator._estimate_degree: то же
    кольцевое окно half_train, та же нормировка x = Δ/half_train ∈ [-1, 1] и тот
    же МНК по x^deg..x^0. Совпадение выбранной степени с моделью проверяется в
    main(): рисунок не должен показывать «другую» кривую.
    """
    half_train = 180.0 / model.n_patches + model.overlap_train
    angles = np.asarray(angles, dtype=float)
    radii = np.asarray(radii, dtype=float)
    ae = np.concatenate([angles - 360.0, angles, angles + 360.0])
    re = np.concatenate([radii, radii, radii])
    m = (ae >= center - half_train) & (ae <= center + half_train)
    x = (ae[m] - center) / half_train
    y = re[m]
    degs = np.arange(model.deg_min, model.deg_max + 1, 2)
    rmse = []
    for d in degs:
        c = np.polyfit(x, y, int(d))
        rmse.append(float(np.sqrt(np.mean((np.polyval(c, x) - y) ** 2))))
    return degs, np.asarray(rmse)


def fixed_degree_models(a, r, pits):
    """Модели, у которых ВСЕ патчи одной степени (deg_min = deg_max = d).

    Так выглядит «простой» вариант: одна степень на всю деталь. Число
    коэффициентов считается по документу (полином + ямные члены) — pit_report().
    """
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")        # RankWarning на высоких степенях
        for d in FIXED_DEGREES:
            m = build_model({"deg_min": int(d), "deg_max": int(d)}, pits)
            m.fit(a, r)
            rows.append((int(d), m, sum(p["n_coefs"] for p in m.pit_report())))
    return rows


# ------------------------------------------------------------------- рисунки

def fig_method_patches(a, r, ideal, curve, degrees, pits, centers, half_sector, half_use):
    fig, axes = plt.subplots(3, 1, figsize=(11.0, 9.6), sharex=True)
    data_grid = interp_ring(a, r, GRID)
    ideal_grid = np.asarray(ideal, dtype=float)      # истина уже на сетке GRID

    ax = axes[0]
    ax.plot(a, r, ".", ms=2.5, color="#9a9a9a", label="измерения (CSV)")
    ax.plot(GRID, ideal_grid, "-", lw=1.0, color="#2e8b57", alpha=0.8, label="истина")
    ax.plot(GRID, curve, "-", lw=1.7, color="#c0392b", label="PAPPA (модель)")
    top = ax.get_ylim()[1]
    for c, d in zip(centers, degrees):
        ax.axvline(c, color="#2c7fb8", lw=0.8, alpha=0.5)
        ax.text(c, 0.97, "deg %d" % d, transform=ax.get_xaxis_transform(), fontsize=7,
                ha="center", va="top", color="#2c7fb8",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
    for p in pits:
        ax.axvspan(p - 1.0, p + 1.0, color="#e67e22", alpha=0.18)
    ax.set_ylabel("r, мм")
    ax.set_title("PAPPA: 7 патчей с адаптивной степенью (deg) и фичером ям "
                 "(оранжевые полосы — ямы, найденные детектором)", fontsize=10)
    ax.legend(fontsize=8, loc="lower right", ncol=3)
    ax.grid(alpha=0.25)

    ax = axes[1]
    for c in centers:
        ax.plot(GRID, weight(circ_dist(GRID, c), half_sector, half_use), lw=1.2)
    total = sum(weight(circ_dist(GRID, c), half_sector, half_use) for c in centers)
    ax.plot(GRID, total, "k--", lw=1.0, label="Σ весов: в перекрытии 1..2, модель делит на неё")
    ax.set_ylabel("вес патча")
    ax.set_title("Smoothstep-веса: в ядре сектора 1, к перекрытию плавно 0. "
                 "Σ весов не равна 1 — поэтому контур НОРМИРУЕТСЯ на Σ "
                 "(half_sector = %.1f°, half_use = %.1f°)" % (half_sector, half_use),
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    ax = axes[2]
    err_data = np.abs(curve - data_grid)
    err_ideal = np.abs(curve - ideal_grid)
    ax.semilogy(GRID, np.maximum(err_data, 1e-16), lw=1.0, color="#c0392b",
                label="|PAPPA − измерения|")
    ax.semilogy(GRID, np.maximum(err_ideal, 1e-16), lw=1.0, color="#2e8b57",
                label="|PAPPA − истина|")
    for p in pits:
        ax.axvspan(p - 1.0, p + 1.0, color="#e67e22", alpha=0.18)
    ax.set_xlabel("угол, °")
    ax.set_ylabel("|Δr|, мм")
    ax.set_xlim(0.0, 360.0)
    ax.set_title("Ошибка по кольцу: дефекты попадают в окна патчей, а не «звенят» "
                 "по всему сечению", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, which="both")

    fig.tight_layout()
    path = OUT / "method_patches.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def fig_method_detector(a, r, indicator, zones, pits):
    fig, axes = plt.subplots(2, 1, figsize=(11.0, 6.6), sharex=True)

    ax = axes[0]
    ax.plot(a, r, ".", ms=2.2, color="#607d8b")
    for z in zones:
        ax.axvspan(z[0], z[1], color="#e67e22", alpha=0.22)
    for p in pits:
        ax.axvline(p, color="#c0392b", lw=1.0, ls="--")
        ax.text(p, ax.get_ylim()[0], "%.1f°" % p, fontsize=7, color="#c0392b",
                ha="center", va="bottom", rotation=90)
    ax.set_ylabel("r, мм")
    ax.set_title("Детектор «band»: индикатор = |узкая медиана (1°) − широкая медиана "
                 "(10°)|, сглаженный (2°) и нормированный на свою робастную sigma",
                 fontsize=10)
    ax.grid(alpha=0.25)

    ax = axes[1]
    ax.plot(a, indicator, lw=1.0, color="#2c7fb8")
    ax.axhline(K_ZONES, color="#c0392b", lw=1.0, ls="--", label="порог k = %.1f MAD" % K_ZONES)
    for z in zones:
        ax.axvspan(z[0], z[1], color="#e67e22", alpha=0.22)
    ax.set_xlabel("угол, °")
    ax.set_ylabel("индикатор, MAD")
    ax.set_xlim(0.0, 360.0)
    ax.set_ylim(0.0, max(1.2 * float(np.max(indicator)), K_ZONES + 1.0))
    ax.set_title("Зоны = участки выше порога длиной не короче 2°; их середины — центры ям",
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    path = OUT / "method_detector.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def fig_vs_fourier(a, r, results, focus):
    data_grid = interp_ring(a, r, GRID)
    fig, axes = plt.subplots(2, 1, figsize=(11.0, 7.6))

    ax = axes[0]
    ax.plot(a, r, ".", ms=1.8, color="#9a9a9a", label="измерения")
    for label, curve, ncoef, _, _ in results:
        pappa = label.startswith("PAPPA")
        ax.plot(GRID, curve, "-" if pappa else "--", lw=1.7 if pappa else 1.0,
                label="%s (%d коэф.)" % (label, ncoef))
    ax.set_xlim(0.0, 360.0)
    ax.set_ylabel("r, мм")
    ax.set_title("Всё кольцо: усечённый Фурье ошибается глобально (рябь по всему "
                 "сечению), PAPPA — локально", fontsize=10)
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.25)

    ax = axes[1]
    lo, hi = focus - 12.0, focus + 12.0
    m = (GRID >= lo) & (GRID <= hi)
    md = (a >= lo) & (a <= hi)
    ax.plot(a[md], r[md], "o", ms=4, color="#9a9a9a", label="измерения")
    for label, curve, ncoef, _, _ in results:
        pappa = label.startswith("PAPPA")
        ax.plot(GRID[m], curve[m], "-" if pappa else "--", lw=1.8 if pappa else 1.1,
                label=label)
    ax.set_xlabel("угол, °")
    ax.set_ylabel("r, мм")
    ax.set_title("Крупно яма около %.1f°" % focus, fontsize=10)
    ax.legend(fontsize=8, ncol=3)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    path = OUT / "method_vs_fourier.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def fig_vs_lpr(a, r, truth, results, focus):
    fig, axes = plt.subplots(2, 1, figsize=(11.0, 7.6))

    ax = axes[0]
    lo, hi = focus - 12.0, focus + 12.0
    m = (GRID >= lo) & (GRID <= hi)
    md = (a >= lo) & (a <= hi)
    ax.plot(a[md], r[md], "o", ms=4, color="#9a9a9a", label="измерения")
    for label, curve, ncoef, _, _ in results:
        pappa = label.startswith("PAPPA")
        ax.plot(GRID[m], curve[m], "-" if pappa else "--", lw=1.8 if pappa else 1.1,
                label=label)
    ax.set_xlabel("угол, °")
    ax.set_ylabel("r, мм")
    ax.set_title("Крупно яма около %.1f°: PAPPA повторяет дно, широкое окно LPR (±10°) "
                 "размывает его, узкое (±2°) ловит шум измерений" % focus, fontsize=10)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.25)

    ax = axes[1]
    for label, curve, ncoef, _, _ in results:
        pappa = label.startswith("PAPPA")
        ax.semilogy(GRID, np.maximum(np.abs(curve - np.asarray(truth, dtype=float)), 1e-16),
                    lw=1.6 if pappa else 1.0, label=label)
    ax.set_xlabel("угол, °")
    ax.set_ylabel("|Δr| к истине, мм")
    ax.set_xlim(0.0, 360.0)
    ax.set_title("Ошибка к истине по всему кольцу (логарифмическая шкала): у LPR она "
                 "размазана, у PAPPA — у дефектов", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, which="both")

    fig.tight_layout()
    path = OUT / "method_vs_lpr.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def fig_method_star(a, r, curve, degrees, centers, half_sector, half_use,
                    pits, phase_deg, margin_now, margin_zero, bad_zero):
    """Раскладка «звезда»: почему N перекрытий, почему обучение шире применения,
    почему фаза сдвинута — и что было бы без сдвига."""
    from matplotlib.patches import Patch

    n = len(centers)
    half_train = half_sector + float(MODEL_DEFAULTS["overlap_train"])
    star_inner = 0.72                 # радиус «впадин» (швов) в условной шкале звезды
    fig = plt.figure(figsize=(11.0, 10.4))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 0.16, 1.0], hspace=0.22)

    # --- сверху: развёртка кольца, окна патчей, швы и ямы -------------------
    ax = fig.add_subplot(gs[0])
    for c in centers:                       # обучение шире применения + замыкание кольца
        for shift in (-360.0, 0.0, 360.0):
            ax.axvspan(c + shift - half_train, c + shift + half_train,
                       color="#2c7fb8", alpha=0.06, lw=0.0)
            ax.axvspan(c + shift - half_use, c + shift + half_use,
                       color="#2c7fb8", alpha=0.18, lw=0.0)
    for p in pits:
        ax.axvspan(p - 1.0, p + 1.0, color="#e67e22", alpha=0.30, lw=0.0)
    ax.plot(a, r, ".", ms=1.5, color="#9a9a9a")
    ax.plot(GRID, curve, "-", lw=1.4, color="#c0392b")
    for nd in node_angles(n, 0.0):
        ax.axvline(nd, color="#9e9e9e", lw=0.7, ls=":", alpha=0.9)
    for nd in node_angles(n, phase_deg):
        ax.axvline(nd, color="#333333", lw=1.1, ls="--")
    for i, (c, d) in enumerate(zip(centers, degrees)):
        ax.axvline(c, color="#1f4e79", lw=0.9, alpha=0.8)
        ha = "left" if c < 40.0 else ("right" if c > 320.0 else "center")
        ax.text(c, 0.99, "P%d: deg %d" % (i, d), transform=ax.get_xaxis_transform(),
                fontsize=6.5, ha=ha, va="top", color="#1f4e79",
                bbox=dict(boxstyle="round,pad=0.10", fc="white", ec="none", alpha=0.75))
    ax.set_xlim(0.0, 360.0)
    ax.set_xlabel("угол, °")
    ax.set_ylabel("r, мм")
    ax.set_title("Раскладка «звезда»: N = %d перекрывающихся патчей на всё тело. "
                 "Отступ шва от ямы: %.2f° при phase = %g° против %.2f° при phase = 0°%s"
                 % (n, margin_now, phase_deg, margin_zero,
                    (" — там шов попадал в трещину в %d сечениях" % bad_zero)
                    if bad_zero else ""), fontsize=10)
    ax.grid(alpha=0.25)

    # --- отдельная строка под легенду: чтобы она не закрывала данные -------
    axl = fig.add_subplot(gs[1])
    axl.axis("off")
    axl.legend(handles=[
        Patch(color="#2c7fb8", alpha=0.18,
              label="зона ПРИМЕНЕНИЯ ±half_use = ±%.1f°" % half_use),
        Patch(color="#2c7fb8", alpha=0.06,
              label="окно ОБУЧЕНИЯ ±half_train = ±%.1f° (шире применения на %.0f°)"
                    % (half_train, half_train - half_use)),
        plt.Line2D([], [], color="#1f4e79", lw=1.0, label="центры патчей (лучи)"),
        plt.Line2D([], [], color="#333333", lw=1.1, ls="--",
                   label="швы (узлы) при phase = %g°" % phase_deg),
        plt.Line2D([], [], color="#9e9e9e", lw=0.7, ls=":",
                   label="швы при phase = 0 (историческое поведение)"),
        Patch(color="#e67e22", alpha=0.30, label="ямы по детектору band"),
        plt.Line2D([], [], color="#c0392b", lw=1.4, label="модель PAPPA"),
        plt.Line2D([], [], color="#9a9a9a", marker=".", ls="", label="измерения"),
    ], fontsize=7, ncol=4, loc="center")

    # --- снизу: та же раскладка в полярных координатах ---------------------
    axp = fig.add_subplot(gs[2], projection="polar")
    axp.set_theta_zero_location("N")
    axp.set_theta_direction(-1)
    axp.set_ylim(0.0, 1.30)
    axp.set_yticks([1.0])
    axp.set_yticklabels([""], fontsize=7)
    theta = np.radians(GRID)
    colors = plt.cm.tab10(np.linspace(0.0, 1.0, n))
    for i, c in enumerate(centers):
        w_i = weight(circ_dist(GRID, c), half_sector, half_use)
        axp.fill_between(theta, 0.0, w_i, color=colors[i], alpha=0.45, lw=0.0,
                         label="патч P%d" % i)
    nodes = node_angles(n, phase_deg)
    star_th, star_r = [], []
    for i in range(n):                      # лучи — центры, впадины — швы
        star_th += [np.radians(nodes[i]), np.radians(centers[i])]
        star_r += [star_inner, 1.0]
    axp.plot(np.append(star_th, star_th[0]), np.append(star_r, star_r[0]),
             "-", color="0.35", lw=1.4, zorder=3)
    axp.text(np.radians(nodes[0]), star_inner - 0.12, "впадина = шов", fontsize=7,
             color="0.35", ha="center", va="top")
    axp.text(np.radians(centers[2]), 1.10, "луч = центр патча", fontsize=7,
             color="#1f4e79", ha="center")
    for p in pits:
        rad = np.radians(p)
        axp.plot([rad, rad], [1.02, 1.18], color="#e67e22", lw=2.0)
        ha = "left" if 90.0 < p < 270.0 else "right"
        axp.text(rad, 1.19, "%.0f°" % p, fontsize=7, color="#e67e22", ha=ha)
    axp.set_title("«Звезда» в полярных координатах: 7 лучей, впадины — швы. "
                  "Лепестки — веса smoothstep\n(в ядре сектора 1, к краю 0); "
                  "оранжевые штрихи — трещины по детектору", fontsize=9, pad=16)
    axp.legend(fontsize=6.5, ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.20))

    # tight_layout() с полярными осями ругается и портит полярную панель —
    # расставляем поля вручную.
    fig.subplots_adjust(left=0.06, right=0.98, top=0.95, bottom=0.03)
    path = OUT / "method_star.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def fig_method_degrees(a, r, ideal, curve, model, degrees, centers, frontier,
                       fourier_rows, lpr_rows, ncoef_doc):
    """Степень: как она выбирается (правило «локтя») и чего стоит отказ от выбора."""
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 6.2))
    colors = plt.cm.tab10(np.linspace(0.0, 1.0, len(centers)))

    # --- слева: кривые RMSE(deg) по патчам и порог «локтя» -----------------
    ax = axes[0]
    handles = []
    for i, c in enumerate(centers):
        degs, rmse = degree_curve(a, r, c, model)
        limit = float(np.min(rmse)) * (1.0 + float(model.deg_elbow_tol))
        ax.semilogy(degs, rmse, "o-", ms=3.2, lw=1.1, color=colors[i], alpha=0.9)
        ax.axhline(limit, color=colors[i], ls=":", lw=0.8, alpha=0.7)
        sel = int(degrees[i])
        h, = ax.plot(sel, rmse[degs == sel], "*", ms=12, color=colors[i],
                     label="P%d → %d (центр %.0f°)" % (i, sel, c))
        handles.append(h)
    noise = float(np.median([degree_curve(a, r, c, model)[1][0] for c in centers]))
    ax.axhline(noise, color="0.55", lw=0.8, ls="-.")
    ax.text(13.9, noise, "уровень шума в окне ≈ %.2f мм " % noise, fontsize=6.5,
            color="0.4", ha="right", va="bottom")
    ax.set_xlabel("чётная степень полинома (звёздочка = выбранная)")
    ax.set_ylabel("RMSE на СВОЁМ обучающем окне, мм")
    ax.set_xticks(list(FIXED_DEGREES))
    ax.set_title("Правило «локтя»: берётся САМАЯ ДЕШЁВАЯ степень,\n"
                 "у которой RMSE ≤ best·(1 + %.2f)" % float(model.deg_elbow_tol),
                 fontsize=10, pad=10)
    ax.grid(alpha=0.25, which="both")
    ax.legend(handles=handles, fontsize=6.5, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.20))

    # --- справа: цена (число коэффициентов) против ошибки ------------------
    ax = axes[1]
    xs = [row[2] for row in frontier]
    rm_f, me_f = [], []
    for _, m, _ in frontier:
        me, rm = errors(ideal, m.eval(GRID))
        rm_f.append(rm)
        me_f.append(me)
    ax.loglog(xs, rm_f, "o-", color="#1f4e79", lw=1.3,
              label="одна степень на все патчи: RMSE")
    ax.loglog(xs, me_f, "s--", color="#1f4e79", alpha=0.6, lw=1.1,
              label="одна степень на все патчи: max|Δ|")
    for (d, _, _), x, y in zip(frontier, xs, rm_f):
        ax.annotate("deg %d" % d, (x, y), textcoords="offset points", xytext=(4, 5),
                    fontsize=7, color="#1f4e79")
    me_p, rm_p = errors(ideal, curve)
    ax.loglog([ncoef_doc], [rm_p], "*", ms=16, color="#c0392b",
              label="PAPPA, степень адаптивна: RMSE")
    ax.loglog([ncoef_doc], [me_p], "*", ms=16, color="#c0392b", alpha=0.6,
              label="PAPPA, степень адаптивна: max|Δ|")
    for label, rows, color in (("Фурье", fourier_rows, "#2e8b57"),
                               ("LPR", lpr_rows, "#8e44ad")):
        ax.loglog([row[2] for row in rows], [row[4] for row in rows], "v-", ms=5,
                  lw=1.0, color=color, alpha=0.8, label="%s: RMSE" % label)
    ax.set_xlabel("число коэффициентов в документе")
    ax.set_ylabel("ошибка к истине, мм")
    ax.set_xlim(1.5, 900.0)
    f8 = [row for row in frontier if row[0] == 8][0]
    me8, _ = errors(ideal, f8[1].eval(GRID))
    best_fixed = min(frontier, key=lambda row: errors(ideal, row[1].eval(GRID))[0])
    me_bf = errors(ideal, best_fixed[1].eval(GRID))[0]
    # Подписи — прямо у кривых: легенда тут закрывала бы точки (правый нижний
    # угол плотно забит рядом «цена ↔ ошибка»).
    ax.annotate("фикс. степень: RMSE", (xs[-1], rm_f[-1]), textcoords="offset points",
                xytext=(8, -3), fontsize=6.5, color="#1f4e79", va="center")
    ax.annotate("фикс. степень: max|Δ|", (xs[-1], me_f[-1]),
                textcoords="offset points", xytext=(8, 3), fontsize=6.5,
                color="#1f4e79", alpha=0.75, va="center")
    ax.annotate("PAPPA (адаптивная)", (ncoef_doc, rm_p), textcoords="offset points",
                xytext=(-9, -6), fontsize=6.5, color="#c0392b", ha="right")
    ax.annotate("Фурье", (fourier_rows[0][2], fourier_rows[0][4]),
                textcoords="offset points", xytext=(5, 6), fontsize=6.5,
                color="#2e8b57")
    ax.annotate("LPR (фикс. окно)", (lpr_rows[-1][2], lpr_rows[-1][4]),
                textcoords="offset points", xytext=(6, -9), fontsize=6.5,
                color="#8e44ad")
    ax.set_title("Цена против ошибки: одна степень против адаптивной\n"
                 "deg 8 (%d коэф.): max|Δ| %.3f мм, а у PAPPA (%d коэф.) — %.3f мм;\n"
                 "deg %d (%d коэф., %.1f×): %.3f мм, то есть точнее, но дороже"
                 % (f8[2], me8, ncoef_doc, me_p, best_fixed[0], best_fixed[2],
                    best_fixed[2] / float(ncoef_doc), me_bf), fontsize=9, pad=10)
    ax.grid(alpha=0.25, which="both")
    ax.grid(alpha=0.25, which="both")

    fig.tight_layout(rect=(0.0, 0.16, 1.0, 1.0))
    path = OUT / "method_degrees.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def fig_method_cleaning(a_all, r_all, mask, severity, params, a, r, ideal,
                        curve_clean, curve_raw, model_raw):
    """Авто-очистка: маска, severity против порога и цена отказа от очистки."""
    fig, axes = plt.subplots(3, 1, figsize=(11.0, 9.8), sharex=True)

    ax = axes[0]
    ax.plot(a, r, ".", ms=2.0, color="#607d8b", label="оставлено: %d точек" % a.size)
    ax.plot(a_all[mask], r_all[mask], "x", ms=5.5, color="#c0392b", mew=1.2,
            label="выброшено: %d точек (%.2f%%)"
                  % (int(mask.sum()), 100.0 * mask.sum() / a_all.size))
    ax.plot(GRID, ideal, "-", lw=1.0, color="#2e8b57", alpha=0.85, label="истина")
    ax.set_ylabel("r, мм")
    ax.set_title("Авто-очистка (iqr) идёт ПЕРЕД выбором степени, детектором и\n"
                 "амплитудами ям: медианное окно по кольцу %.1f° (%.0f точек), "
                 "iqr_k = %g, порог %.3f мм"
                 % (float(params.get("baseline_window_deg", 0.0)),
                    float(params.get("baseline_window_points", 0.0)),
                    float(params.get("iqr_k", 0.0)),
                    float(params.get("threshold_mm", 0.0) or 0.0)), fontsize=9, pad=8)
    ax.legend(fontsize=8, ncol=3, loc="upper right")
    ax.grid(alpha=0.25)

    ax = axes[1]
    ax.semilogy(a_all, np.maximum(severity, 1e-3), lw=0.7, alpha=0.85,
                color="#2c7fb8", label="severity всех точек")
    ax.semilogy(a_all[mask], np.maximum(severity[mask], 1e-3), "x", ms=4.5,
                mew=1.1, color="#c0392b", label="выброшенные (%d)" % int(mask.sum()))
    ax.axhline(float(params.get("iqr_k", 3.0)), color="#c0392b", ls="--", lw=1.1,
               label="порог iqr_k = %g · IQR(остатка)"
                     % float(params.get("iqr_k", 3.0)))
    ax.set_ylim(1e-2, 3e1)
    ax.set_ylabel("severity, IQR")
    ax.set_title("«Ненормальность» точки = |остаток − медиана| / IQR(остатка); остаток — "
                 "отклонение от скользящей МЕДИАНЫ по кольцу.\nФорма профиля снята, "
                 "поэтому порог не зависит ни от наклона, ни от глубины ям",
                 fontsize=9, pad=8)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25, which="both")

    ax = axes[2]
    err_c = errors(ideal, curve_clean)
    err_r = errors(ideal, curve_raw)
    ax.semilogy(GRID, np.maximum(np.abs(np.nan_to_num(curve_clean) -
                                        np.asarray(ideal, dtype=float)), 1e-16),
                lw=1.2, color="#c0392b",
                label="с очисткой: max|Δ| %.3g мм, RMSE %.3g мм" % err_c)
    ax.semilogy(GRID, np.maximum(np.abs(np.nan_to_num(curve_raw) -
                                        np.asarray(ideal, dtype=float)), 1e-16),
                lw=1.2, color="#8e44ad",
                label="без очистки (те же детектор и правило): max|Δ| %.3g мм, "
                      "RMSE %.3g мм; степени %s"
                      % (err_r[0], err_r[1], model_raw.get_degrees()))
    ax.set_xlabel("угол, °")
    ax.set_ylabel("|Δr| к истине, мм")
    ax.set_xlim(0.0, 360.0)
    ax.set_title("Цена отказа от очистки: выбросы «съедают» и выбор степени, и "
                 "амплитуды ям — та же модель, обученная на грязных точках",
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, which="both")

    fig.tight_layout()
    path = OUT / "method_cleaning.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a, r, ideal, raw = load_section(SECTION)
    data_grid = interp_ring(a, r, GRID)

    indicator = indicator_curve(a, r, "band", window_deg=1.0, envelope_deg=0.5,
                                smooth_deg=2.0, wide_deg=10.0)
    zones = detect_zones(a, indicator, K_ZONES, min_len_deg=2.0)
    pits = [0.5 * (z[0] + z[1]) for z in zones]

    model = build_model({}, pits)
    model.fit(a, r)
    curve = np.asarray(model.eval(GRID), dtype=float)
    degrees = list(model.get_degrees())
    centers, half_sector, half_use, _ = patch_layout()

    results = []
    for order in (4, 6, 12, 24):
        ev, ncoef = make_fourier(a, r, order)
        c = ev(GRID)
        me, rm = errors(ideal, c)
        results.append(("Фурье-%d" % order, c, ncoef, me, rm))
    lpr = []
    for half, deg in ((2.0, 1), (5.0, 2), (10.0, 2)):
        c = make_lpr(a, r, GRID, half, deg)
        me, rm = errors(ideal, c)
        lpr.append(("LPR: ±%g°, степень %d" % (half, deg), c, deg + 1, me, rm))

    ncoef_pappa = sum(d + 1 for d in degrees)
    me_p, rm_p = errors(ideal, curve)
    pappa = [("PAPPA (7 патчей + ямы)", curve, ncoef_pappa, me_p, rm_p)]

    f6 = [row for row in results if row[0] == "Фурье-6"][0][1]
    focus = float(GRID[int(np.argmax(np.abs(f6 - ideal)))])

    # --- раскладка «звезда»: отступ швов от ям по ВСЕМ сечениям ------------
    n_patches = int(MODEL_DEFAULTS["n_patches"])
    phase_deg = float(MODEL_DEFAULTS["phase_deg"])
    half_train = half_sector + float(MODEL_DEFAULTS["overlap_train"])
    sections_pits = detect_all_sections()
    margins_now, margins_zero = [], []
    for _, pp in sections_pits:
        margins_now.append(min(margin_to_seam(pp, n_patches, phase_deg))
                           if pp else float("nan"))
        margins_zero.append(min(margin_to_seam(pp, n_patches, 0.0))
                            if pp else float("nan"))
    bad_zero = sum(1 for m in margins_zero if m < 0.0)
    finite_now = [m for m in margins_now if np.isfinite(m)]
    finite_zero = [m for m in margins_zero if np.isfinite(m)]

    # --- степени: зеркало правила «локтя» + цена фиксированной степени -----
    mirror_ok = True
    for i, c in enumerate(centers):
        degs, rmse = degree_curve(a, r, c, model)
        best = float(np.min(rmse))
        ok = np.flatnonzero(rmse <= best * (1.0 + float(model.deg_elbow_tol)))
        sel = int(degs[ok[0]]) if ok.size else int(degs[int(np.argmin(rmse))])
        mirror_ok = mirror_ok and (sel == degrees[i])
    frontier = fixed_degree_models(a, r, pits)
    ncoef_doc = sum(p["n_coefs"] for p in model.pit_report())

    # --- очистка: маска/severity и модель БЕЗ очистки ----------------------
    a_all, r_all, mask = raw
    cleaner = build_cleaner(CLEANER)
    mask_check = cleaner.clean(a_all, r_all)
    severity = np.asarray(cleaner.severity_, dtype=float)
    cleaner_params = dict(cleaner.params_)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")        # выбросы делают МНК плохо обусловленным
        model_raw = build_model({}, pits)
        model_raw.fit(a_all, r_all)
    curve_raw = np.asarray(model_raw.eval(GRID), dtype=float)

    print("Сечение %d: очищенных точек %d, шаг %.1f°" % (SECTION, a.size,
                                                         float(np.median(np.diff(a)))))
    print("Детектор band: зон %d, центры ям: %s"
          % (len(pits), ", ".join("%.2f°" % p for p in pits)))
    print("Степени патчей: %s" % degrees)
    print()
    print("Ошибка к ИСТИНЕ (radius_ideal_mm), та же сетка %.2f°:" % (360.0 / GRID.size))
    print("%-30s %8s %14s %12s %14s %12s"
          % ("метод", "коэф.", "max|Δ|, мм", "RMSE, мм", "max|Δ|изм", "RMSEизм"))
    for label, c, ncoef, me, rm in results + lpr + pappa:
        me2, rm2 = errors(data_grid, c)
        print("%-30s %8d %14.3e %12.3e %14.3e %12.3e"
              % (label, ncoef, me, rm, me2, rm2))
    print("  (max|Δ|изм/RMSEизм — та же модель против ОЧИЩЕННЫХ измерений;")
    print("   истина задана генератором, поэтому по ней видно именно ошибку метода)")
    print()
    print("Фокус для крупных планов: %.2f° (максимум ошибки Фурье-6 к истине)" % focus)

    print()
    print("РАСКЛАДКА «ЗВЕЗДА»: N = %d, сектор %.2f°, phase = %g°, "
          "half_train = %.2f°, half_use = %.2f° (обучение шире применения на %.1f°)"
          % (n_patches, 360.0 / n_patches, phase_deg, half_train, half_use,
             half_train - half_use))
    print("  %-4s %-4s %14s %15s %15s %13s"
          % ("сеч", "ям", "отступ(выбр)", "отступ(phase 0)", "швов в ямe (0)",
             "|отступ|<2° (0)"))
    for (sid, pp), mn, mz in zip(sections_pits, margins_now, margins_zero):
        n_in = sum(1 for p in pp if min(margin_to_seam([p], n_patches, 0.0)) < 0.0)
        n_near = sum(1 for p in pp if min(margin_to_seam([p], n_patches, 0.0)) < 2.0)
        print("  %-4d %-4d %+14.2f %+15.2f %15d %13d"
              % (sid, len(pp), mn, mz, n_in, n_near))
    near_zero = sum(1 for m in margins_zero if m < 2.0)
    print("  минимум по всем %d сечениям: phase = %g° -> %+.2f°, phase = 0 -> %+.2f°; "
          "шов в самой трещине при phase = 0: %d сечений, шов ближе 2° к трещине: "
          "phase = 0 -> %d сечений, выбранная фаза -> %d"
          % (len(sections_pits), phase_deg, min(finite_now), min(finite_zero),
             bad_zero, near_zero, sum(1 for m in finite_now if m < 2.0)))

    print()
    print("ВЫБОР СТЕПЕНИ (правило «локтя», deg_elbow_tol = %g):" % model.deg_elbow_tol)
    print("  %-5s %9s %9s %14s %14s %9s"
          % ("патч", "центр,°", "степень", "RMSE(выбр), мм", "RMSE(лучш), мм", "точек"))
    for i, p in enumerate(model.patches_):
        m = p["metrics"]
        print("  P%-4d %9.2f %9d %14.3e %14.3e %9d"
              % (i, p["center"], p["degree"], m["rmse_selected_mm"],
                 m["rmse_best_mm"], m["n_train_points"]))
    print("  самопроверка рисунка: зеркало правила дало те же степени — %s"
          % ("да" if mirror_ok else "НЕТ"))

    print()
    print("ЦЕНА ПРОТИВ ОШИБКИ (то же сечение): одна степень на все патчи против "
          "адаптивной")
    print("  %-28s %7s %13s %13s" % ("вариант", "коэф.", "max|Δ|, мм", "RMSE, мм"))
    for d, m, ncoef in frontier:
        me, rm = errors(ideal, m.eval(GRID))
        print("  %-28s %7d %13.3e %13.3e" % ("все патчи deg %d" % d, ncoef, me, rm))
    print("  %-28s %7d %13.3e %13.3e"
          % ("PAPPA (степень по патчам)", ncoef_doc, me_p, rm_p))
    print("  (коэф. = полиномы + ямные члены, как в документе; у PAPPA это %d "
          "полиномиальных + %d ямных)" % (ncoef_pappa, ncoef_doc - ncoef_pappa))
    f8 = [row for row in frontier if row[0] == 8][0]
    me8, rm8 = errors(ideal, f8[1].eval(GRID))
    best_fixed = min(frontier, key=lambda row: errors(ideal, row[1].eval(GRID))[0])
    me_bf, rm_bf = errors(ideal, best_fixed[1].eval(GRID))
    print("  ЧЕСТНО: при похожем бюджете адаптивная точнее любой одинаковой "
          "(deg 8, %d коэф.: max|Δ| %.3e/RMSE %.3e против %.3e/%.3e у PAPPA, %d коэф.),"
          % (f8[2], me8, rm8, me_p, rm_p, ncoef_doc))
    print("  но абсолютный максимум точности даёт однородный deg %d: %.3e/%.3e при "
          "%d коэф. (%.1f× бюджета PAPPA) — за это платят размером документа и "
          "обусловленностью МНК на x^14"
          % (best_fixed[0], me_bf, rm_bf, best_fixed[2],
             best_fixed[2] / float(ncoef_doc)))

    me_raw, rm_raw = errors(ideal, curve_raw)
    print()
    print("ОЧИСТКА ВЫБРОСОВ (iqr, авто): всего %d точек, выброшено %d (%.2f%%), "
          "iqr_k = %g, порог %.4f мм (IQR остатка %.4f мм)"
          % (a_all.size, int(mask.sum()), 100.0 * mask.sum() / a_all.size,
             float(cleaner_params.get("iqr_k", float("nan"))),
             float(cleaner_params.get("threshold_mm", float("nan"))),
             float(cleaner_params.get("iqr_res_mm", float("nan")))))
    print("  самопроверка: маска очистки из load_sections совпала с прямым вызовом "
          "build_cleaner — %s" % ("да" if np.array_equal(mask, mask_check) else "НЕТ"))
    print("  с очисткой: степени %s, max|Δ| %.3e мм, RMSE %.3e мм" % (degrees, me_p, rm_p))
    print("  без очистки (те же детектор и правило): степени %s, max|Δ| %.3e мм, "
          "RMSE %.3e мм" % (model_raw.get_degrees(), me_raw, rm_raw))

    made = [
        fig_method_patches(a, r, ideal, curve, degrees, pits, centers, half_sector,
                           half_use),
        fig_method_star(a, r, curve, degrees, centers, half_sector, half_use, pits,
                        phase_deg, min(finite_now), min(finite_zero), bad_zero),
        fig_method_degrees(a, r, ideal, curve, model, degrees, centers, frontier,
                           results, lpr, ncoef_doc),
        fig_method_cleaning(a_all, r_all, mask, severity, cleaner_params, a, r, ideal,
                            curve, curve_raw, model_raw),
        fig_method_detector(a, r, indicator, zones, pits),
        fig_vs_fourier(a, r, results + pappa, focus),
        fig_vs_lpr(a, r, ideal, lpr + pappa, focus),
    ]
    print()
    for path in made:
        print("рисунок: %s (%.0f КБ)" % (path.relative_to(ROOT),
                                         path.stat().st_size / 1024.0))


if __name__ == "__main__":
    main()


