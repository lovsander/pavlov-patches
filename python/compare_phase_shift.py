"""
compare_phase_shift.py

Обзор фазовых смещений сетки патчей (phase_deg).

Зачем: сетка патчей строится всегда от угла 0 (centers = i*sector +
half_sector), поэтому при разных N «ямы» профиля (трещины) попадают в разные
места патча: то под центр полинома, то на границу секторов. Здесь это
исследуется на ОДНОМ сечении: перебираются N из CONFIG['n_patches_list'], и
для каждого N свипается фаза от 0 до sector (= 360/N) — сдвиг на sector даёт
ту же конфигурацию, поэтому достаточно одного сектора.

Обучение — по чистым точкам файла (после OutlierCleaner), как в
compare_patch_counts.py. RMSE считается и по точкам файла ("data"), и по
сетке отрисовки ("grid") — вторая сглажена и меньше зависит от шума.

ВАЖНО про метрики: чистильщик выбросов отбрасывает часть точек на склонах ям
(там максимальны производная и отклонение от медианы), поэтому RMSE по
"clean"-точкам оптимистичнее, чем по сетке: вторая покрывает всё кольцо
равномерно. В отчёте печатаются обе метрики.

Результат:
- phase_shift_rmse.png   — RMSE(фаза) для каждого N; вертикали — фазы, при
  которых центр патча попадает точно на дно ямы; внизу — сводные бары
  «фаза 0 / центр патча на яме / лучшая фаза свипа»;
- phase_shift_curves.png — невязка (аппроксимация − эталон) при фазе 0 и при
  лучшей фазе для каждого N + положения центров патчей.

Запуск: python compare_phase_shift.py
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")  # только сохранение в файл, без GUI
import matplotlib.pyplot as plt

from compare_patch_counts import load_and_clean, make_approximator, resolve_path


# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

CONFIG = {
    # --- данные (как в compare_patch_counts.py) ---
    "csv": "synthetic_data.csv",
    "section": 0,                 # исследуем ОДНО сечение
    "ideal_column": "radius_ideal_mm",

    # --- метрика и сетка отрисовки ---
    "grid_points": 1440,
    "metric_scope": "clean",      # "clean" (после очистки) | "all"

    # --- что перебираем ---
    "n_patches_list": [3, 4, 5, 6, 7, 8, 9, 10],
    "phase_step_deg": 2.0,        # шаг свипа фазы внутри сектора

    # --- параметры метода ---
    # Чистка: авторежим (пороги вычисляются по данным). Прежний ручной режим
    # оставлял точки на дне глубоких ям и тормозил оценку: см. compare_cleaner_auto.py.
    # Ручной вариант: {"mode": "manual", "threshold_deriv": 0.5,
    #                  "mad_k": 9.5, "z_threshold": 3.5}
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},
    "base": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
             "overlap_train": 15.0, "overlap_use": 5.0},

    # --- поиск «ям» (локальных минимумов эталона) ---
    "pit_window_deg": 12.0,       # окно поиска локального минимума
    "pit_prominence_mm": 0.05,    # минимальная глубина ямы

    # --- отрисовка ---
    "style": {
        "data_ms": 1.0,
        "data_alpha": 0.20,
        "zero_lw": 0.7,
        "fit_lw": 1.0,
        "phase0_lw": 0.9,
        "pit_lw": 0.8,
        "center_lw": 0.6,
    },
    "colors": ["tab:blue", "tab:orange", "tab:green", "tab:red",
               "tab:purple", "tab:brown", "tab:pink", "tab:gray"],
    "output_rmse": "phase_shift_rmse.png",
    "output_curves": "phase_shift_curves.png",
    "dpi": 120,
}


# ============================================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ============================================================================

def cyclic_dist(a, b):
    """Кратчайшее расстояние по дуге, °."""
    return np.abs((np.asarray(a, float) - np.asarray(b, float) + 180.0) % 360.0
                  - 180.0)


def rmse(a, b):
    """RMSE между двумя массивами."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def find_pits(deg, r, window_deg, prominence_mm):
    """
    Углы «ям» эталона — циклические локальные минимумы радиуса.

    Яма = минимум в окне ±window_deg, глубина которого относительно
    максимумов того же окна не меньше prominence_mm.
    Возвращает отсортированный список пар (угол, глубина).
    """
    deg = np.asarray(deg, float)
    r = np.asarray(r, float)
    order = np.argsort(deg % 360.0)
    deg, r = deg[order], r[order]

    n = len(r)
    step = 360.0 / n
    k = max(1, int(round(window_deg / step)))

    cand = np.flatnonzero((r <= np.roll(r, k)) & (r <= np.roll(r, -k)))

    pits = []
    for i in cand:
        idx = (i + np.arange(-k, k + 1)) % n
        j = int(idx[int(np.argmin(r[idx]))])           # самое дно в окне
        left = r[(j + np.arange(-k, 1)) % n].max()
        right = r[(j + np.arange(0, k + 1)) % n].max()
        prom = float(min(left, right) - r[j])
        if prom < prominence_mm:
            continue
        if any(cyclic_dist(deg[j], a) < window_deg for a, _ in pits):
            continue                                    # эту яму уже нашли
        pits.append((float(deg[j]), prom))

    pits.sort()
    return pits


def aligned_phase(pit_angle, n_patches):
    """Фаза, при которой центр одного из патчей попадает точно на pit_angle."""
    sector = 360.0 / n_patches
    return float((pit_angle - sector / 2.0) % sector)


def outlier_mask(section):
    """
    True для точек файла, отброшенных очисткой выбросов.

    Число выбросов в окрестности ямы показывает, насколько "clean"-метрика
    недооценивает ошибку в самой сложной зоне профиля.
    """
    a_all = section["angles_all"]
    is_out = np.ones(len(a_all), dtype=bool)
    idx = np.clip(np.searchsorted(a_all, section["angles"]),
                  0, len(a_all) - 1)
    keep = np.isclose(a_all[idx], section["angles"])
    is_out[idx[keep]] = False
    return is_out


# ============================================================================
# СВИП ФАЗЫ
# ============================================================================

def sweep_phase(section, base, n_patches, step_deg, angles_grid, ideal_grid,
                metric_scope="clean", extra_phases=()):
    """
    Прогон по фазам внутри одного сектора (период свипа = sector).

    base — параметры метода без n_patches/phase_deg.
    extra_phases — фазы, которые нужно посчитать точно (например «центр
    патча на дне ямы») даже если они не попали на равномерную сетку.

    Обучение — по чистым точкам файла. RMSE считается по точкам файла
    (metric_scope) и по сетке отрисовки.

    Возвращает dict с массивами: phases, rmse_data, rmse_grid,
    degrees, centers, fitted_grid.
    """
    sector = 360.0 / n_patches
    n_steps = max(4, int(round(sector / step_deg)))
    phases = np.unique(np.concatenate([
        np.linspace(0.0, sector, n_steps, endpoint=False),
        np.asarray(list(extra_phases), dtype=float) % sector,
    ]))

    if metric_scope == "all":
        a_m, r_m = section["angles_all"], section["radii_all"]
    else:
        a_m, r_m = section["angles"], section["radii"]
    ideal_m = np.interp(a_m, section["ideal_deg"], section["ideal_r"])

    out = {"phases": phases, "rmse_data": [], "rmse_grid": [],
           "degrees": [], "centers": [], "fitted_grid": []}

    for ph in phases:
        params = dict(base)
        params["n_patches"] = int(n_patches)
        params["phase_deg"] = float(ph)

        approx = make_approximator(params)
        approx.fit(section["angles"], section["radii"])   # все чистые точки

        fitted_grid = approx.eval(angles_grid)
        fitted_m = approx.eval(a_m)

        out["rmse_data"].append(rmse(fitted_m, ideal_m))
        out["rmse_grid"].append(rmse(fitted_grid, ideal_grid))
        out["degrees"].append(approx.get_degrees())
        out["centers"].append(np.asarray(approx.centers_, float))
        out["fitted_grid"].append(fitted_grid)

    for key in ("rmse_data", "rmse_grid"):
        out[key] = np.asarray(out[key], float)

    return out


# ============================================================================
# MAIN
# ============================================================================

def main():
    cfg = CONFIG
    csv_path = resolve_path(cfg["csv"])
    sid = int(cfg["section"])

    print("=" * 70)
    print("ОБЗОР ФАЗОВЫХ СМЕЩЕНИЙ СЕТКИ ПАТЧЕЙ (phase_deg)")
    print("=" * 70)
    print(f"Данные:   {csv_path.name}")
    print(f"Сечение:  {sid}")
    print(f"Набор N:  {cfg['n_patches_list']}")
    print(f"Шаг фазы: {cfg['phase_step_deg']}° (свип по одному сектору)")

    sections = load_and_clean(csv_path, cfg["cleaner"], cfg["ideal_column"])
    s = sections[sid]

    angles_grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    ideal_grid = np.interp(angles_grid, s["ideal_deg"], s["ideal_r"])

    if cfg["metric_scope"] == "all":
        a_m, r_m = s["angles_all"], s["radii_all"]
    else:
        a_m, r_m = s["angles"], s["radii"]
    ideal_m = np.interp(a_m, s["ideal_deg"], s["ideal_r"])
    data_delta = r_m - ideal_m

    print(f"\nСечение {sid} (h={s['height_mm']:.0f} мм): "
          f"выбросов {s['n_out']}/{s['n_total']}, чистых {len(s['angles'])}, "
          f"метрика {cfg['metric_scope']} по {len(a_m)} точкам")

    # --- где у эталона «ямы» (центры трещин) ---
    pits = find_pits(s["ideal_deg"], s["ideal_r"],
                     cfg["pit_window_deg"], cfg["pit_prominence_mm"])
    out_mask = outlier_mask(s)
    print(f"\nЯмы эталона (локальные минимумы, окно "
          f"±{cfg['pit_window_deg']:.0f}°, глубина ≥ "
          f"{cfg['pit_prominence_mm']:.2f} мм):")
    for pit_a, pit_prom in pits:
        near = cyclic_dist(s["angles_all"], pit_a) <= cfg["pit_window_deg"]
        print(f"  {pit_a:7.1f}°   глубина {pit_prom:+.3f} мм, выбросов "
              f"рядом {int(out_mask[near].sum())}/{int(near.sum())}")
    if not pits:
        print("  не найдено — фаза сможет повлиять только через шум")
    else:
        print("  (выбросы «рядом» — точки на склонах ямы, отброшенные "
              "очисткой: их отсутствие занижает RMSE по clean-точкам)")
    deepest = max(pits, key=lambda t: t[1]) if pits else None

    # --- свип фазы для каждого N ---
    # фазы «центр патча ровно на дне ямы» добавляем в сетку свипа,
    # чтобы посчитать их точно, а не по ближайшей точке равномерной сетки
    results = {}
    for n in cfg["n_patches_list"]:
        n = int(n)
        extra = [aligned_phase(pit_a, n) for pit_a, _ in pits]
        results[n] = sweep_phase(s, cfg["base"], n, cfg["phase_step_deg"],
                                 angles_grid, ideal_grid,
                                 cfg["metric_scope"], extra)
        r = results[n]
        bi = int(np.argmin(r["rmse_data"]))
        print(f"  N={n:>2}: sector={360.0 / n:5.2f}°, фаз посчитано "
              f"{len(r['phases'])}, лучшая {r['phases'][bi]:.2f}°")

    # --- отчёт по каждому N ---
    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТ ПО КАЖДОМУ N (RMSE по точкам файла)")
    print("=" * 70)
    for n, r in results.items():
        phases = r["phases"]
        rm_d, rm_g = r["rmse_data"], r["rmse_grid"]
        bi = int(np.argmin(rm_d))
        base0 = float(rm_d[0])
        best = float(rm_d[bi])
        gain = 100.0 * (base0 - best) / base0 if base0 > 0 else 0.0

        print(f"\nN={n}  sector={360.0 / n:.2f}°  half_sector={180.0 / n:.2f}°")
        print(f"  фаза 0°     : RMSE={base0:.5f} (сетка {rm_g[0]:.5f})")
        print(f"  лучшая фаза : RMSE={best:.5f} (сетка {rm_g[bi]:.5f}) "
              f"при фазе {phases[bi]:.2f}°, выигрыш {gain:+.1f}%")
        bg = int(np.argmin(rm_g))
        gain_g = 100.0 * (rm_g[0] - rm_g[bg]) / rm_g[0]
        print(f"  лучшая по сетке: RMSE={rm_g[bg]:.5f} при фазе "
              f"{phases[bg]:.2f}°, выигрыш {gain_g:+.1f}%  "
              f"(устойчивость: по сетке шум усредняется)")
        print(f"  deg @ фаза 0    : {r['degrees'][0]}")
        print(f"  deg @ лучшей фазе: {r['degrees'][bi]}")
        for pit_a, pit_prom in pits:
            ap = aligned_phase(pit_a, n)
            i = int(np.argmin(np.abs(phases - ap)))
            mark = "  <- лучшее" if rm_d[i] <= best + 1e-12 else ""
            print(f"  центр патча на яме {pit_a:6.1f}° (глубина "
                  f"{pit_prom:+.2f}) -> фаза {ap:6.2f}°: RMSE={rm_d[i]:.5f} "
                  f"(сетка {rm_g[i]:.5f}){mark}")

    # ==================== ОТРИСОВКА 1: RMSE(фаза) ====================
    style = cfg["style"]
    colors = cfg["colors"]
    ns = list(results.keys())
    n_cols = min(4, len(ns))
    n_rows_top = int(np.ceil(len(ns) / n_cols))

    fig = plt.figure(figsize=(4.8 * n_cols, 3.4 * n_rows_top + 3.2))
    gs = fig.add_gridspec(n_rows_top + 1, n_cols,
                          height_ratios=[3.0] * n_rows_top + [1.5])

    for i, n in enumerate(ns):
        ax = fig.add_subplot(gs[i // n_cols, i % n_cols])
        r = results[n]
        phases, rm_d, rm_g = r["phases"], r["rmse_data"], r["rmse_grid"]
        sector = 360.0 / n
        color = colors[i % len(colors)]

        # фазы, при которых центр патча стоит точно на дне ямы
        for pit_a, _ in pits:
            ap = aligned_phase(pit_a, n)
            ax.axvline(ap, color="black", ls="--", lw=style["pit_lw"],
                       alpha=0.30, zorder=0)
            ax.text(ap, 0.01, f"{pit_a:.0f}°", rotation=90, fontsize=6,
                    ha="right", va="bottom", color="black", alpha=0.65,
                    transform=ax.get_xaxis_transform())

        ax.plot(phases, rm_g, "--", lw=0.9, color=color, alpha=0.45,
                label="RMSE по сетке (сглажено)")
        ax.plot(phases, rm_d, "-o", lw=style["fit_lw"], ms=3.0, color=color,
                label="RMSE по точкам файла")
        ax.axhline(float(rm_d[0]), color="gray", ls=":", lw=style["zero_lw"],
                   alpha=0.9, label="фаза 0°")

        bi = int(np.argmin(rm_d))
        gain = 100.0 * (float(rm_d[0]) - float(rm_d[bi])) / float(rm_d[0])
        ax.plot(phases[bi], rm_d[bi], "*", ms=12, color="gold", mec="black",
                mew=0.6, zorder=5, label="лучшая фаза")

        ax.set_title(f"N={n}, sector={sector:.1f}°: лучшая {phases[bi]:.1f}°, "
                     f"выигрыш {gain:+.1f}%", fontsize=8.5)
        ax.set_xlim(0.0, sector)
        ax.set_xlabel("Фазовый сдвиг, °", fontsize=8)
        if i % n_cols == 0:
            ax.set_ylabel("RMSE, мм", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)
        if i == 0:
            ax.legend(fontsize=6.5, loc="upper right", framealpha=0.85,
                      borderpad=0.3, columnspacing=0.8, handlelength=2.0)

    for j in range(len(ns), n_rows_top * n_cols):
        fig.add_subplot(gs[j // n_cols, j % n_cols]).axis("off")

    # --- сводные бары: фаза 0 / центр на самой глубокой яме / лучшая фаза ---
    axb = fig.add_subplot(gs[n_rows_top, :])
    x = np.arange(len(ns))
    w = 0.26
    rm0, rmal, rmbe = [], [], []
    for n in ns:
        r = results[n]
        rm0.append(float(r["rmse_data"][0]))
        rmbe.append(float(np.min(r["rmse_data"])))
        if deepest is not None:
            ap = aligned_phase(deepest[0], n)
            idx = int(np.argmin(np.abs(r["phases"] - ap)))
            rmal.append(float(r["rmse_data"][idx]))
        else:
            rmal.append(np.nan)

    axb.bar(x - w, rm0, w, color="0.80", edgecolor="black", lw=0.4,
            label="фаза 0°")
    axb.bar(x, rmal, w, color="tab:cyan", edgecolor="black", lw=0.4,
            label=(f"центр патча на самой глубокой яме {deepest[0]:.0f}°"
                   if deepest else "ямы не найдены"))
    axb.bar(x + w, rmbe, w, color="steelblue", edgecolor="black", lw=0.4,
            label="лучшая фаза свипа")
    for xi, (a0, ab) in enumerate(zip(rm0, rmbe)):
        axb.text(xi + w, ab, f"{(a0 - ab) / a0 * 100:+.1f}%", ha="center",
                 va="bottom", fontsize=7)
    axb.set_xticks(x)
    axb.set_xticklabels([f"N={n}\n{360.0 / n:.0f}°" for n in ns], fontsize=8)
    axb.set_xlabel("Число патчей / размер сектора", fontsize=8)
    axb.set_ylabel("RMSE, мм", fontsize=8)
    axb.set_title("Сводка: RMSE по точкам файла (ниже — лучше); "
                  "процент — выигрыш лучшей фазы относительно фазы 0°",
                  fontsize=9)
    axb.legend(fontsize=7, ncol=3, loc="upper right", framealpha=0.85)
    axb.grid(True, axis="y", alpha=0.3)

    fig.suptitle(
        f"Фазовый сдвиг сетки патчей — сечение {sid} "
        f"(h={s['height_mm']:.0f} мм), чистых точек {len(s['angles'])}\n"
        f"вертикали — фазы, при которых центр патча стоит точно на дне ямы "
        f"(подписан угол ямы); период свипа = sector = 360/N",
        fontsize=11, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out1 = resolve_path(cfg["output_rmse"])
    fig.savefig(out1, dpi=cfg["dpi"], bbox_inches="tight")
    print(f"\nГрафик RMSE(фаза) сохранён: {out1}")

    # ============ ОТРИСОВКА 2: НЕВЯЗКА (фаза 0 против лучшей) ============
    fig2, axes2 = plt.subplots(n_rows_top, n_cols,
                               figsize=(4.8 * n_cols, 3.3 * n_rows_top),
                               sharex=True, sharey=True)
    axes2 = np.atleast_1d(axes2).ravel()

    # общий масштаб по вертикали: немного шире, чем разброс данных
    ylim = float(np.percentile(np.abs(data_delta), 99.5))
    for res in results.values():
        for arr in res["fitted_grid"]:
            ylim = max(ylim, float(np.percentile(np.abs(arr - ideal_grid), 99.5)))
    ylim = max(ylim * 1.15, 0.05)

    for i, n in enumerate(ns):
        ax = axes2[i]
        r = results[n]
        color = colors[i % len(colors)]
        rm_d = r["rmse_data"]
        bi = int(np.argmin(rm_d))

        ax.plot(a_m, data_delta, ".", color="gray",
                markersize=style["data_ms"], alpha=style["data_alpha"],
                zorder=0, label="данные − эталон")
        ax.plot(angles_grid, r["fitted_grid"][0] - ideal_grid, "--",
                lw=style["phase0_lw"], color="gray", alpha=0.95,
                label=f"фаза 0° (RMSE={rm_d[0]:.4f})")
        ax.plot(angles_grid, r["fitted_grid"][bi] - ideal_grid, "-",
                lw=style["fit_lw"] + 0.4, color=color, alpha=0.95,
                label=f"фаза {r['phases'][bi]:.1f}° (RMSE={rm_d[bi]:.4f})")

        # центры патчей при лучшей фазе
        for c in r["centers"][bi]:
            ax.axvline(float(c), color=color, lw=style["center_lw"],
                       alpha=0.35, zorder=0)
        # ямы эталона
        for pit_a, _ in pits:
            ax.axvline(pit_a, color="black", ls=":", lw=style["pit_lw"],
                       alpha=0.55, zorder=0)
        ax.axhline(0.0, color="black", lw=style["zero_lw"], alpha=0.5)

        ax.set_xlim(0.0, 360.0)
        ax.set_ylim(-ylim, ylim)
        ax.set_title(f"N={n}: фаза 0° против лучшей фазы "
                     f"{r['phases'][bi]:.1f}°", fontsize=9)
        ax.set_xlabel("Угол, °", fontsize=8)
        if i % n_cols == 0:
            ax.set_ylabel("Δr = аппроксимация − эталон, мм", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=6.5, loc="upper right", ncol=2, framealpha=0.85,
                  borderpad=0.3, columnspacing=0.8, handlelength=2.4)

    for j in range(len(ns), n_rows_top * n_cols):
        axes2[j].axis("off")

    fig2.suptitle(
        f"Невязка к эталону: фаза 0° против лучшей фазы — сечение {sid} "
        f"(h={s['height_mm']:.0f} мм)\n"
        f"цветные вертикали — центры патчей лучшей фазы, чёрный пунктир — ямы "
        f"эталона; чем ближе кривая к нулю в окрестности ямы, тем лучше "
        f"описана трещина",
        fontsize=11, y=0.995)
    fig2.tight_layout(rect=(0, 0, 1, 0.94))
    out2 = resolve_path(cfg["output_curves"])
    fig2.savefig(out2, dpi=cfg["dpi"], bbox_inches="tight")
    print(f"График невязок сохранён: {out2}")

    plt.close("all")


if __name__ == "__main__":
    main()
