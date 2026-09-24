"""
appa.viz.fourier_figs — рисунок «Фурье малой степени + фичер ям» против патчей.

Стиль проекта: >= 2000 px по ширине, dpi из конфига, подписи по-русски, палитра
Okabe-Ito. Рисуется РАДИУС (точки данных + эталон + модели): пользователь просил
«ямы на точках», а не остатки.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .pit_figs import draw_window

# свои цвета для Фурье-вариантов (у патчей цвета остаются из pit_figs.STYLE)
FOURIER_STYLE = {
    "fourier4": {"color": "#7B3294", "ls": (0, (1.5, 1.5)), "lw": 1.1,
                 "label": "Фурье 4 гармоники (без ям)"},
    "fourier6": {"color": "#56B4E9", "ls": (0, (6, 2)), "lw": 1.3,
                 "label": "Фурье 6 гармоник (без ям)"},
    "joint": {"color": "#009E73", "ls": (0, (3, 1.2)), "lw": 1.4,
              "label": "Фурье 6 + ямы, общая подгонка (Фурье видит ямы)"},
    "masked": {"color": "#D55E00", "ls": "-", "lw": 1.9,
               "label": "Фурье 6 (без ям) + ямы фичером (Фурье ям не видит)"},
    "patches": {"color": "#0072B2", "ls": "-", "lw": 1.8,
                "label": "наш метод: поли-патчи + ямы"},
}


def plot_fourier_sweep(cfg, sweep, ref, out_path):
    """
    RMSE против числа гармоник: чистый Фурье, Фурье+ямы (общая подгонка),
    Фурье(слепой)+ямы; горизонтальные линии — наши варианты патчей.

    Это и есть ответ на «а может, Фурье+фичер достаточно»: видно, при каком
    числе гармоник Фурье доходит до уровня патчей и где упирается.
    """
    orders = sorted(sweep)
    fig, axes = plt.subplots(1, 2, figsize=(15.0, 5.2))

    ax = axes[0]
    ax.plot(orders, [sweep[o]["fourier"][0] for o in orders], "o-",
            color=FOURIER_STYLE["fourier6"]["color"], label="Фурье (без ям)")
    ax.plot(orders, [sweep[o]["joint"][0] for o in orders], "s-",
            color=FOURIER_STYLE["joint"]["color"],
            label="Фурье + ямы, общая подгонка")
    ax.plot(orders, [sweep[o]["masked"][0] for o in orders], "^-",
            color=FOURIER_STYLE["masked"]["color"],
            label="Фурье (ям не видит) + ямы фичером")
    ax.axhline(ref["poly"][0], color="#0072B2", ls="--", lw=1.3,
               label=f"патчи-поли: {ref['poly'][0]:.4f} мм")
    ax.axhline(ref["patches"][0], color="#0072B2", ls="-", lw=1.6,
               label=f"патчи + ямы: {ref['patches'][0]:.4f} мм "
                     f"({ref['patches'][2]:.0f} коэф.)")
    ax.set_yscale("log")
    ax.set_xlabel("Число гармоник Фурье")
    ax.set_ylabel("средняя RMSE, мм (лог. шкала)")
    ax.set_title("Точность по кольцу: ряд против патчей", fontsize=10.5)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8, loc="best")

    ax = axes[1]
    ax.plot(orders, [sweep[o]["fourier"][1] for o in orders], "o-",
            color=FOURIER_STYLE["fourier6"]["color"], label="Фурье (без ям)")
    ax.plot(orders, [sweep[o]["joint"][1] for o in orders], "s-",
            color=FOURIER_STYLE["joint"]["color"],
            label="Фурье + ямы, общая подгонка")
    ax.plot(orders, [sweep[o]["masked"][1] for o in orders], "^-",
            color=FOURIER_STYLE["masked"]["color"],
            label="Фурье (ям не видит) + ямы фичером")
    ax.axhline(ref["patches"][1], color="#0072B2", ls="-", lw=1.6,
               label=f"патчи + ямы: {ref['patches'][1]:.4f} мм")
    ax.set_xlabel("Число гармоник Фурье")
    ax.set_ylabel("ошибка в окне ямы, мм")
    ax.set_title("Главное: ошибка у ям", fontsize=10.5)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="best")

    fig.suptitle("Фурье малой степени + фичер ям: развёртка по числу гармоник "
                 f"(средние по сечениям {cfg['sections']}; окно фичера "
                 f"±{cfg['pit_window_sigma'] * cfg['sigma_deg']:.1f}°)",
                 fontsize=11.5)
    plt.tight_layout(rect=(0, 0, 1, 0.93))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)


def plot_fourier_pit(cfg, sections, zones_by_section, crops, rows, out_path,
                     n_harm=6):
    """
    Строки — сечения, столбцы: (0) всё кольцо, (1) крупно самая глубокая яма.

    Панели: точки данных, эталон, чистый Фурье 4/6, Фурье+ямы (общая подгонка),
    Фурье(без ям)+ямы фичером и наш метод (патчи+ямы). На кропе — окно фичера.
    """
    secs = cfg["sections"]
    fig, axes = plt.subplots(len(secs), 2, figsize=(17.0, 3.4 * len(secs)),
                             squeeze=False)
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]

    for i, sid in enumerate(secs):
        s = sections[sid]
        grid = rows[sid]["grid"]

        # --- слева: всё кольцо ---
        ax = axes[i][0]
        ax.plot(s["angles"], s["radii"], ".", color="gray", markersize=1.0,
                alpha=0.25, zorder=1)
        ax.plot(s["angles"], s["ideal"], "-", color="black", lw=0.9,
                alpha=0.8, zorder=2)
        for key in ("fourier6", "masked", "patches"):
            st = FOURIER_STYLE[key]
            ax.plot(grid, rows[sid]["curves"][key], ls=st["ls"], color=st["color"],
                    lw=st["lw"], zorder=3)
        ax.set_xlim(0, 360)
        ax.set_title(f"Сечение {sid} (h = {s['height_mm']:.0f} мм): всё кольцо, "
                     f"радиус\nRMSE: Фурье-6 {rows[sid]['metrics']['fourier6']['rmse']:.4f} "
                     f"| Фурье+ямы(фичер) {rows[sid]['metrics']['masked']['rmse']:.4f} "
                     f"| патчи+ямы {rows[sid]['metrics']['patches']['rmse']:.4f} мм",
                     fontsize=9.5)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("Радиус, мм")
        ax.grid(alpha=0.3)

        # --- справа: крупно самая глубокая яма ---
        ax = axes[i][1]
        it = crops[sid][0]
        half = it["loc"][-1]
        for a, b in zones_by_section[sid]:
            ca = ((a - it["angle"] + 180.0) % 360.0) - 180.0
            cb = ((b - it["angle"] + 180.0) % 360.0) - 180.0
            if cb < ca or cb < -half or ca > half:
                continue
            ax.axvspan(max(ca, -half), min(cb, half), color="tab:red",
                       alpha=0.16, lw=0.0, zorder=0)
        draw_window(ax, win)
        ax.plot(it["pts_a"], it["pts_r"], ".", color="gray", markersize=2.4,
                alpha=0.45, zorder=1, label="данные (очищенные)")
        ax.plot(it["loc"], it["ideal"], "-", color="black", lw=1.0, alpha=0.85,
                zorder=2, label="эталон")
        for key, st in FOURIER_STYLE.items():
            ax.plot(it["loc"], it["curves"][key], ls=st["ls"], color=st["color"],
                    lw=st["lw"], zorder=4 if key == "patches" else 3,
                    label=st["label"])
        ax.set_xlim(-half, half)
        ax.grid(alpha=0.3)
        ax.set_xlabel("Угол к центру ямы, °")
        ax.set_ylabel("Радиус, мм")
        ax.set_title(f"Сечение {sid}: яма {it['angle']:.1f}° (зона "
                     f"{it['width']:.1f}°, глубина ~{it['depth']:.2f} мм)\n"
                     f"у ямы ошибаются: Фурье-6 "
                     f"{rows[sid]['metrics']['fourier6']['peak_at_pit']:.3f}, "
                     f"Фурье+ямы(фичер) "
                     f"{rows[sid]['metrics']['masked']['peak_at_pit']:.3f}, "
                     f"патчи+ямы "
                     f"{rows[sid]['metrics']['patches']['peak_at_pit']:.3f} мм",
                     fontsize=9.5)
        if i == 0:
            ax.legend(fontsize=7.5, loc="best", framealpha=0.92, ncol=2)

    fig.suptitle(
        "Фурье малой степени + фичер ям против поли-патчей (одна звезда N = "
        f"{cfg['n_patches']}, phase = {cfg['phase_deg']:g}°; окно фичера "
        f"±{win:.1f}°)\n"
        f"Фурье учится на {n_harm} гармониках; «без ям» — Фурье видит только "
        "точки вне окон ям, ямы дорисовывает гаусс; «общая подгонка» — Фурье "
        "подбирается вместе с ямами (и искажается)", fontsize=11.5)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    plt.savefig(out_path, dpi=cfg["dpi"], bbox_inches="tight")
    plt.close(fig)
