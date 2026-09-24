"""
appa.report.pit_window_report — таблицы «окно фичера vs фаза» для решения.
"""

"""нужен numpy для средних в отчёте"""
import numpy as np


WINDOWS = (3.2, 2.5, 2.0)


def report_geometry(cfg, rows, per_section):
    print("=" * 100)
    print("ГЕОМЕТРИЯ: окно фичера против зоны сшивки патчей (без подгонок)")
    print("=" * 100)
    ou = cfg["model"]["overlap_use"]
    print(f"Звезда N = {cfg['n_patches']}; зона сшивки — ±{ou:g}° вокруг шва; "
          f"sigma = {cfg['sigma_deg']:g}° (окна 3.2σ = ±9.6°, 2.5σ = ±7.5°, "
          f"2.0σ = ±6.0°)")
    print("Запас ямы до сшивки = расстояние до ближайшего шва - 5° - полуокно; "
          "«-» = окно заезжает в сшивку")
    print(f"\n  {'сеч':>4} {'яма,°':>8} {'до шва,°':>9} "
          + " ".join(f"{f'м.{w:g}σ':>9}" for w in WINDOWS)
          + f" {'своя ф.':>9} {'«под ямы»':>10} {'фаза':>7}")
    for r in rows:
        shared = [r["dist_shared"] - ou - w * cfg["sigma_deg"] for w in WINDOWS]
        print(f"  {r['section']:>4} {r['pit']:>8.2f} {r['dist_shared']:>9.2f} "
              + " ".join(f"{v:>9.2f}" for v in shared)
              + f" {r['m_own']:>9.2f} {r['m_best']:>10.2f} "
              f"{r['phase_best']:>7.2f}")

    print("\nСуммарное перекрытие окон ям с зоной сшивки по вариантам, °:")
    print(f"  {'сеч':>4} {'общая/3.2σ':>12} {'общая/2.5σ':>12} "
          f"{'своя/3.2σ':>11} {'«под ямы»/3.2σ':>15} {'безоп. фаза':>12}")
    for sid in sorted(per_section):
        s = per_section[sid]
        print(f"  {sid:>4} {s['shared'][3.2]['sum_overlap']:>12.2f} "
              f"{s['shared'][2.5]['sum_overlap']:>12.2f} "
              f"{s['own'][3.2]['sum_overlap']:>11.2f} "
              f"{s['best'][3.2]['sum_overlap']:>15.2f} "
              f"{str(s['best_safe']):>12}")
    tot = {
        "shared32": sum(per_section[s]["shared"][3.2]["sum_overlap"]
                        for s in per_section),
        "shared25": sum(per_section[s]["shared"][2.5]["sum_overlap"]
                        for s in per_section),
        "own32": sum(per_section[s]["own"][3.2]["sum_overlap"]
                     for s in per_section),
        "best32": sum(per_section[s]["best"][3.2]["sum_overlap"]
                      for s in per_section),
    }
    print(f"\n  ИТОГО по {len(per_section)} сечениям: общая/3.2σ "
          f"{tot['shared32']:.1f}° | общая/2.5σ {tot['shared25']:.1f}° | "
          f"своя/3.2σ {tot['own32']:.1f}° | «под ямы»/3.2σ {tot['best32']:.1f}°")
    n_bad = sum(1 for r in rows if r["m_shared"] < 0)
    print(f"  Ям с перекрытием при общей фазе: {n_bad} из {len(rows)}; "
          f"с окном 2.5σ: "
          f"{sum(1 for r in rows if r['dist_shared'] - ou - 7.5 < 0)}; "
          f"с окном 2.0σ: "
          f"{sum(1 for r in rows if r['dist_shared'] - ou - 6.0 < 0)}; "
          f"при фазе «под ямы» (окно 3.2σ): "
          f"{sum(1 for r in rows if r['m_best'] < 0)}")


def report_fits(cfg, rows_fits, variants, names):
    """Точность вариантов: RMSE и ошибка у ям (по сечениям и средние)."""
    order = list(variants)
    print("\nТочность подгонок (RMSE по сетке / ошибка в окне ямы), мм:")
    print(f"  {'сечение':>7} " + " ".join(f"{names[k][:20]:>22}" for k in order))
    for sid in cfg["sections"]:
        m = rows_fits[sid]["metrics"]
        cells = " ".join(f"{m[k]['rmse']:>10.4f} / {m[k]['peak_at_pit']:>9.4f}"
                         for k in order)
        print(f"  {sid:>7} {cells}")
    means = {}
    for k in order:
        rm = [rows_fits[s]["metrics"][k]["rmse"] for s in cfg["sections"]]
        pk = [rows_fits[s]["metrics"][k]["peak_at_pit"] for s in cfg["sections"]]
        means[k] = (float(np.mean(rm)), float(np.mean(pk)))
    cells = " ".join(f"{means[k][0]:>10.4f} / {means[k][1]:>9.4f}" for k in order)
    print(f"  {'среднее':>7} {cells}")

    print("\n«Дележ амплитуды»: max |вклад ям| внутри зоны сшивки, мм "
          "(0 = чисто, окна ям не дотягиваются до швов):")
    print(f"  {'сечение':>7} " + " ".join(f"{names[k][:20]:>22}" for k in order))
    for sid in cfg["sections"]:
        m = rows_fits[sid]["seam"]
        cells = " ".join(f"{m[k]:>22.4f}" for k in order)
        print(f"  {sid:>7} {cells}")
    cells = " ".join(f"{np.mean([rows_fits[s]['seam'][k] for s in cfg['sections']]):>22.4f}"
                     for k in order)
    print(f"  {'среднее':>7} {cells}")
