# вырезано из _src_per_section_phase.py (рефакторинг, см. CONTEXT.md §21)

import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..analysis.layout import fit_layout, layout_margins, section_crack_zones, union_zones, zone_margin_deg
from ..core.geometry import node_angles, patch_centers
from ..io.dataset import attach_ideal_grid, load_sections
from ..paths import resolve_path
from ..analysis.per_section_phase import phase_for_pit_centers, pit_center_stats, section_rmse

def report_zones(cfg, sections, zones_by_section):
    print("=" * 100)
    print("PER-SECTION ФАЗА: у каждого сечения свои швы, объединение зон НЕ используется")
    print("=" * 100)
    print("Зоны-трещины по детектору band (k = "
          f"{cfg['detector']['k']:g} MAD): узел должен быть не ближе "
          f"{cfg['guard_deg']:g}° к ним.")
    for sid in cfg["all_sections"]:
        zz = zones_by_section[sid]
        print(f"  сечение {sid:>2} (h={sections[sid]['height_mm']:>5.0f} мм): "
              + (", ".join(f"{0.5 * (a + b):.2f}° (ш. {b - a:.1f}°)" for a, b in zz)
                 or "нет"))


def report_compare(cfg, sections, zones_by_section, per_section_rows,
                   shared_rows, shared_margins, grid):
    print()
    print("=" * 100)
    print("1) СВОЯ ФАЗА ПРОТИВ ОБЩЕЙ (на одних и тех же N)")
    print("=" * 100)
    secs = cfg["sections"]

    print("Общая фаза (объединение зон всех высот) — то, что делал "
          "explore_star_layout:")
    print(f"  {'N':>3} {'фаза,°':>8} {'отступ по объ-ю,°':>18} {'безопасна':>10} "
          f"{'RMSE средняя':>13}")
    for n in cfg["n_patches_compare"]:
        r = shared_rows[n]
        print(f"  {n:>3} {r['phase']:>8.2f} {r['margin']:>+18.2f} "
              f"{('да' if r['safe'] else 'НЕТ'):>10} {r['rmse']:>13.4f}")

    print("\nОтступ шва ПО КАЖДОМУ сечению при общей фазе "
          "(< 0 — шов на трещине, общая раскладка небезопасна):")
    print(f"  {'N':>3} " + " ".join(f"{'с' + str(s):>8}" for s in secs))
    for n in cfg["n_patches_compare"]:
        print(f"  {n:>3} " + " ".join(f"{shared_margins[n][s]:>+8.2f}" for s in secs))

    print("\nСвоя фаза для каждого сечения (в зонах — только это сечение):")
    for n in cfg["n_patches_compare"]:
        print(f"\n  N = {n} (сектор {360.0 / n:.2f}°):")
        print(f"    {'сечение':>7} {'фаза,°':>8} {'отступ,°':>9} {'безоп.':>7} "
              f"{'RMSE':>8} {'фаза(общ),°':>12} {'отступ(общ),°':>14} "
              f"{'RMSE(общ)':>10}")
        for sid in secs:
            r = per_section_rows[n][sid]
            rmse_shared = section_rmse(cfg, sections[sid], grid, n,
                                       shared_rows[n]["phase"])
            print(f"    {sid:>7} {r['phase']:>8.2f} {r['margin']:>+9.2f} "
                  f"{('да' if r['safe'] else 'НЕТ'):>7} {r['rmse']:>8.4f} "
                  f"{shared_rows[n]['phase']:>12.2f} "
                  f"{shared_margins[n][sid]:>+14.2f} {rmse_shared:>10.4f}")

    print("\nЦена «единой фазы на всё тело»:")
    print(f"  {'N':>3} {'своя (комфорт)':>14} {'своя (любая безоп.)':>19} "
          f"{'общая':>8} {'своя vs общая':>13} {'небезоп. сечений: общая':>23} "
          f"{'своя':>6}")
    for n in cfg["n_patches_compare"]:
        own = float(np.mean([per_section_rows[n][s]["rmse"] for s in secs]))
        own_free = float(np.mean([per_section_rows[n][s]["rmse_safe_free"]
                                  for s in secs]))
        shared = shared_rows[n]["rmse"]
        bad_shared = int(sum(1 for s in secs if shared_margins[n][s] < 0))
        bad_own = int(sum(1 for s in secs if per_section_rows[n][s]["margin"] < 0))
        print(f"  {n:>3} {own:>14.4f} {own_free:>19.4f} {shared:>8.4f} "
              f"{100.0 * (1.0 - own_free / shared):>+12.1f}% "
              f"{bad_shared:>23} {bad_own:>6}")
    print("«своя (любая безоп.)» — лучшая RMSE среди безопасных фаз без порога "
          "комфорта: именно её\nнадо сравнивать с общей, если общая в каком-то "
          "сечении небезопасна (тогда её RMSE —\nчисло с нарушением правила, "
          "а не достижимая безопасная точность).")


def report_pits(cfg, sections, grid, zones_by_section, own_all, shared_rows,
                n_report):
    print()
    print("=" * 100)
    print("2) ВОПРОС: яма в ЦЕНТРАЛЬНОЙ ПОЛОВИНЕ патча во всех сечениях?")
    print("=" * 100)
    sector = 360.0 / n_report
    limit = sector * cfg["pit_center_frac"]
    print(f"Центральная половина патча = |смещение центра ямы от центра патча| "
          f"<= сектор x {cfg['pit_center_frac']:g} = {limit:.2f}° "
          f"(сектор при N={n_report}: {sector:.2f}°)")
    print(f"\n  {'сеч':>4} {'ям':>4} {'своя фаза: в центре':>20} "
          f"{'общая фаза: в центре':>21} {'центрирование по ямам':>22} "
          f"смещения, ° (своя фаза)")
    tot = {"own": 0, "shared": 0, "center": 0, "pits": 0}
    for sid in cfg["all_sections"]:
        zz = zones_by_section[sid]
        ph_own = own_all[n_report][sid]["phase"]
        ph_sh = shared_rows[n_report]["phase"]
        ph_ct, _ = phase_for_pit_centers(cfg, n_report, zz)
        own = pit_center_stats(cfg, zones_by_section, n_report, ph_own, [sid])
        sh = pit_center_stats(cfg, zones_by_section, n_report, ph_sh, [sid])
        ct = pit_center_stats(cfg, zones_by_section, n_report, ph_ct, [sid])
        o, s, c = (own["per_section"][sid], sh["per_section"][sid],
                   ct["per_section"][sid])
        tot["own"] += o["n_center"]
        tot["shared"] += s["n_center"]
        tot["center"] += c["n_center"]
        tot["pits"] += o["n_pits"]
        print(f"  {sid:>4} {o['n_pits']:>4} {o['n_center']:>20} "
              f"{s['n_center']:>21} {c['n_center']:>22} "
              + ", ".join(f"{v:.1f}" for v in sorted(o["offsets"])))
    print(f"  ИТОГО из {tot['pits']} ям в центральной половине: своя фаза "
          f"{tot['own']}, общая фаза {tot['shared']}, "
          f"центрирование по ямам {tot['center']}")

    print("\nПрицельное центрирование ям (фаза = минимум суммы |смещение|): "
          "во что оно обходится по швам и точности")
    print(f"  {'сеч':>4} {'фаза,°':>8} {'отступ шва,°':>13} {'швов в зоне':>12} "
          f"{'RMSE, мм':>9} {'RMSE при своей фазе, мм':>24}")
    for sid in cfg["sections"]:
        zz = zones_by_section[sid]
        ph_ct, _ = phase_for_pit_centers(cfg, n_report, zz)
        _, mm = layout_margins(n_report, ph_ct, zz, cfg["guard_deg"])
        rmse_ct = section_rmse(cfg, sections[sid], grid, n_report, ph_ct)
        print(f"  {sid:>4} {ph_ct:>8.2f} {float(np.min(mm)):>+13.2f} "
              f"{int(np.sum(mm < 0)):>12} {rmse_ct:>9.4f} "
              f"{own_all[n_report][sid]['rmse']:>24.4f}")
    print("Вывод по вопросу: «все ямы ровно в центре патча» — НЕ автоматическое "
          "следствие\nper-section фазы. Фаза ищется по безопасности швов, и она "
          "приводит ямы близко к\nцентрам (смещения порядка 2-13° при лимите "
          f"{limit:.1f}°), но не гарантирует центральность\nдля всех ям. "
          "Гарантия появляется только если центрирование ям сделать ОТДЕЛЬНЫМ\n"
          "критерием (последняя таблица показывает: тогда швы можно сдвинуть "
          "в трещину).")
