"""make_method_figures.py — картинки для описания метода и его сравнения с Фурье и
локальной полиномиальной регрессией (LPR).

Что рисуется (в docs/assets/ — эти файлы коммитятся, .gitignore их пропускает):

  method_patches.png     метод «изнутри»: патчи на кольце, partition of unity
                         (smoothstep-веса), ошибка приближения;
  method_detector.png    детектор band: индикатор в MAD-ах, порог, найденные зоны;
  method_vs_fourier.png  PAPPA против усечённого ряда Фурье (4/6/12/24 гармоники);
  method_vs_lpr.png      PAPPA против LPR с ФИКСИРОВАННЫМ окном (degree 1/2, h=2°/10°).

Числа (max|Δ| и RMSE по тому же сечению) печатаются в stdout: их берут README и
docs/method.md, чтобы текст и картинки не разъезжались.

Почему сравнения вообще честные: все методы обучаются на ОДНИХ И ТЕХ ЖЕ точках
сечения из python/synthetic_data.csv и оцениваются на ОДНОЙ И ТОЙ ЖЕ сетке; Фурье и
LPR — без «подглядывания» в истину (radius_ideal_mm нужен только для счёта ошибки).

Запуск: <python с numpy и matplotlib> python/studies/make_method_figures.py
"""

import sys
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
from pappa.core.pit_feature import MODEL_DEFAULTS, build_model
from pappa.io.dataset import attach_ideal_grid, load_sections

CSV = ROOT / "python" / "synthetic_data.csv"
OUT = ROOT / "docs" / "assets"
SECTION = 0
GRID = np.linspace(0.0, 360.0, 1441)[:-1]      # 0.25° — та же сетка, что у сверки порта
K_ZONES = 5.5
DPI = 130
# Тот же очиститель, что у пайплайна: сравнивать методы на «грязных» точках нельзя —
# выброс генератора испортит любой метод, и разницы между методами не будет видно.
CLEANER = {"mode": "auto", "auto": {"method": "iqr"}}


def load_section(section_id):
    """Очищенные точки одного сечения + истина на общей сетке GRID.

    Загрузчик берём референсный (pappa.io.dataset): он же применяет авто-очистку
    `iqr`, поэтому обучающая выборка у всех методов сравнения ОДНА И ТА ЖЕ, а
    `radius_ideal_mm` даёт честную ошибку на той же сетке.
    """
    sections = load_sections(str(CSV), "radius_ideal_mm", CLEANER)
    attach_ideal_grid(sections, GRID)
    s = sections[section_id]
    a = np.asarray(s["angles_clean"], dtype=float)
    r = np.asarray(s["radii_clean"], dtype=float)
    ideal = np.asarray(s["ideal_grid"], dtype=float)
    order = np.argsort(a, kind="stable")
    return a[order], r[order], ideal



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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a, r, ideal = load_section(SECTION)
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

    made = [
        fig_method_patches(a, r, ideal, curve, degrees, pits, centers, half_sector,
                           half_use),
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


