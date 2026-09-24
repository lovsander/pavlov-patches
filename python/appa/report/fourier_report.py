"""
appa.report.fourier_report — текстовый отчёт «Фурье + фичер ям против патчей».
"""

VARIANT_ORDER = ["fourier4", "fourier6", "joint", "masked", "poly", "patches"]

VARIANT_NAMES = {
    "fourier4": "Фурье-4 (без ям)",
    "fourier6": "Фурье-6 (без ям)",
    "joint": "Фурье-6 + ямы, общая подгонка",
    "masked": "Фурье-6 (без ям) + ямы фичером",
    "poly": "патчи-поли (наш метод, без ям)",
    "patches": "патчи + ямы (наш метод)",
}


def report_config(cfg, sections, zones_by_section):
    print("=" * 100)
    print("ФУРЬЕ МАЛОЙ СТЕПЕНИ + ФИЧЕР ЯМ против ПОЛИ-ПАТЧЕЙ")
    print("=" * 100)
    win = cfg["pit_window_sigma"] * cfg["sigma_deg"]
    print(f"Сечения: {cfg['sections']}; гармоник: {cfg['fourier_orders']}; "
          f"фичер: sigma = {cfg['sigma_deg']:g}°, окно ±{win:.1f}° "
          f"(ядро ±{cfg['pit_core_sigma'] * cfg['sigma_deg']:.1f}°)")
    print(f"Наш метод: N = {cfg['n_patches']} патчей, phase = "
          f"{cfg['phase_deg']:g}° (та же звезда, что в остальных исследованиях)")
    print("\nЯмы (центры зон-трещин из детектора):")
    for sid in cfg["sections"]:
        zz = zones_by_section[sid]
        print(f"  сечение {sid:>2}: "
              + ", ".join(f"{0.5 * (a + b):.2f}°" for a, b in zz))


def report_sweep(cfg, sweep, ref):
    """Печать развёртки по числу гармоник + сравнение с нашими значениями."""
    print("\nРазвёртка по числу гармоник (средние по сечениям, мм):")
    print(f"  {'K гарм.':>8} {'Фурье':>9} {'+ямы общая':>11} {'+ямы слепой':>12} "
          f"{'у ям: Фурье':>12} {'+общая':>8} {'+слепой':>9} {'коэф.':>6}")
    for order, res in sweep.items():
        n_coef = 2 * order + 1
        print(f"  {order:>8} {res['fourier'][0]:>9.4f} {res['joint'][0]:>11.4f} "
              f"{res['masked'][0]:>12.4f} {res['fourier'][1]:>12.4f} "
              f"{res['joint'][1]:>8.4f} {res['masked'][1]:>9.4f} {n_coef:>6}")
    print(f"  наши значения: патчи-поли {ref['poly'][0]:.4f} "
          f"(у ям {ref['poly'][1]:.4f}; {ref['poly'][2]:.0f} коэф.), "
          f"патчи+ямы {ref['patches'][0]:.4f} (у ям {ref['patches'][1]:.4f}; "
          f"{ref['patches'][2]:.0f} коэф. + амплитуды ям)")
    best = min(sweep.items(), key=lambda kv: kv[1]["masked"][0])
    print(f"  лучший «Фурье + фичер» (K = {best[0]}, "
          f"{2 * best[0] + 1} коэффициентов): RMSE "
          f"{best[1]['masked'][0]:.4f} мм — "
          f"{100.0 * (best[1]['masked'][0] / ref['patches'][0] - 1.0):+.0f}% "
          f"к патчам+ямы")


def report_table(cfg, rows, drift):
    """Таблицы: RMSE/пик у ям по вариантам + дрейф Фурье-коэффициентов."""
    order = [v for v in VARIANT_ORDER if v in rows[cfg["sections"][0]]["metrics"]]
    print("\nRMSE по сетке против эталона, мм:")
    print(f"  {'сечение':>7} " + " ".join(f"{VARIANT_NAMES[v][:22]:>22}" for v in order))
    for sid in cfg["sections"]:
        m = rows[sid]["metrics"]
        print(f"  {sid:>7} " + " ".join(f"{m[v]['rmse']:>22.4f}" for v in order))

    print("\nХудшая ошибка в окне ямы (у ям), мм:")
    print(f"  {'сечение':>7} " + " ".join(f"{VARIANT_NAMES[v][:22]:>22}" for v in order))
    for sid in cfg["sections"]:
        m = rows[sid]["metrics"]
        print(f"  {sid:>7} "
              + " ".join(f"{m[v]['peak_at_pit']:>22.4f}" for v in order))

    print("\nНасколько база «поехала» из-за ям (вне окон ям), мм и %:")
    for sid in cfg["sections"]:
        d = drift[sid]
        print(f"  сечение {sid:>2}: Фурье-6 общая подгонка vs чистое Фурье — "
              f"{d['joint'][0]:.4f} мм ({100.0 * d['joint'][1]:.1f}% по "
              f"коэффициентам); патчи+ямы vs патчи-поли — "
              f"{d['patches'][0]:.4f} мм")


def report_verdict(cfg, rows):
    """Средние по сечениям + вывод: нужен ли метод патчей рядом с Фурье."""
    m = {}
    for v in VARIANT_ORDER:
        vals = [rows[s]["metrics"][v]["rmse"] for s in cfg["sections"]
                if v in rows[s]["metrics"]]
        pk = [rows[s]["metrics"][v]["peak_at_pit"] for s in cfg["sections"]
              if v in rows[s]["metrics"]]
        if vals:
            m[v] = (float(sum(vals) / len(vals)), float(sum(pk) / len(pk)))
    print()
    print("=" * 100)
    print("ИТОГ (средние по сечениям)")
    print("=" * 100)
    for v, (rmse, peak) in sorted(m.items(), key=lambda kv: kv[1][0]):
        print(f"  {VARIANT_NAMES[v]:<35} RMSE {rmse:.4f} мм | у ям {peak:.4f} мм")
    if "masked" in m and "fourier6" in m:
        gain = 100.0 * (1.0 - m["masked"][0] / m["fourier6"][0])
        print(f"\n  Фичер ям поверх «слепого» Фурье-6: {gain:+.1f}% по RMSE "
              f"(у ям {m['fourier6'][1]:.3f} -> {m['masked'][1]:.3f} мм)")
    if "masked" in m and "patches" in m:
        d = 100.0 * (m["masked"][0] / m["patches"][0] - 1.0)
        print(f"  Фурье(без ям)+фичер против патчей+фичер: {d:+.1f}% по RMSE")
