"""
rejected_node_on_pit.py — ОТКЛОНЁННАЯ ГИПОТЕЗА, оставлена для истории метода.

ЗАЧЕМ ФАЙЛ ЖИВЁТ ЗДЕСЬ: метод полезно помнить, от чего отталкивались и какие
гипотезы оказались тупиковыми (red flags). Ниже — что проверялось и почему это
не пошло; код рабочий, его можно перезапустить и убедиться самому.

ГИПОТЕЗА: ставить узлы (стыки патчей) на ДНО ям вместо «подальше от ям».
Мотив: если стык приходится на дно ямы, полиному не надо выгибаться через яму,
уходят осцилляции (Рунге) на берегах, RMSE падает.

ПРОВЕРЯЛИСЬ два фактора раздельно:
  (1) ПОЛОЖЕНИЕ узла: chosen (margin-first, как в раскладке звездой) vs
      best-RMSE vs node-on-pit;
  (2) ОКНО обучения: overlap_train = 15° (как в пайплайне) vs 0° (полином не
      видит «чужой» берег ямы).
Метрики: RMSE по сетке (эталон), выравнивание узла на дно ямы (град), локальная
ошибка ±6° вокруг дна каждой ямы (мм), ошибка «на берегах» 6..16° (мм).

РЕЗУЛЬТАТ (подробности — CONTEXT §14, отвергнутая гипотеза):
  * локально работает: сечение 0, N=8, phase 0 — RMSE 0.0311 и дефицит глубины
    ямы -23% (то есть яма даже слегка недоописана, но стык её «не ломает»);
  * в сумме ПРОИГРЫВАЕТ выбранной раскладке на -17%:
      - дно ям ДРЕЙФУЕТ на 15-20° между сечениями, а сетка узлов равномерная;
      - overlap_train = 15° означает, что яму всё равно видят ОБА соседних
        полинома — изгиб дублируется, а не исчезает;
      - узел ставит яму на ~63% полуширины окна обучения, где число Лебега
        полинома хуже -> шум в коэффициентах;
      - overlap_train = 0 (предел «каждая яма целиком в своём патче») ломает
        сшивку: RMSE вырастает в 4-7 раз.
ВЫВОД, который остался в методе: яма должна быть ближе к ЦЕНТРУ патча, а не к
узлу; и фичеру ям (оконный гаусс) фаза нужна не для «попадания в дно», а для
ухода окна от зоны сшивки (см. CONTEXT §24-25).

Запуск: <python> research/rejected_node_on_pit.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import time

import numpy as np

from appa.analysis.layout import (fit_layout, layout_margins,
                                  section_crack_zones, union_zones)
from appa.core.geometry import node_angles
from appa.io.dataset import attach_ideal_grid, load_sections
from appa.paths import resolve_path

# конфиг такой же, как в studies/explore_star_layout.py (только нужные ключи)
cfg = {
    "csv": "synthetic_data.csv",
    "sections": [0, 2, 5, 9],
    "all_sections": list(range(10)),
    "ideal_column": "radius_ideal_mm",
    "detector": {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
                 "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0,
                 "truth_depth_frac": 0.05},
    "guard_deg": 3.0,
    "comfort_margin_deg": 5.0,
    "zone_grid_step_deg": 0.01,
    "model": {"deg_min": 4, "deg_max": 14, "amplitude_scale": 180.0,
              "overlap_train": 15.0, "overlap_use": 5.0, "deg_elbow_tol": 0.05},
    "grid_points": 1440,
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},
}
sections = load_sections(resolve_path(cfg["csv"]), cfg["ideal_column"],
                         cfg["cleaner"])
grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
attach_ideal_grid(sections, grid)

zones_by_section = section_crack_zones(cfg, sections, cfg["all_sections"])
union = union_zones(cfg, zones_by_section)
sids = cfg["sections"]

def circ_off(a, c):
    return (np.asarray(a) - c + 180.0) % 360.0 - 180.0

def pits(sid):
    """Дно каждой ямы: argmin эталона внутри найденной зоны."""
    s = sections[sid]
    med = float(np.median(s["ideal"]))
    out = []
    for z0, z1 in zones_by_section[sid]:
        c = 0.5 * (z0 + z1)
        half = 0.5 * (z1 - z0)
        m = np.abs(circ_off(s["angles"], c)) <= half
        if not m.any():
            continue
        k = int(np.argmin(s["ideal"][m]))
        out.append({"angle": float(s["angles"][m][k]), "zone_center": c,
                    "depth": med - float(s["ideal"][m][k])})
    return out

PITS = {sid: pits(sid) for sid in sids}
print("Дно ям по сечениям (дно / центр зоны / глубина, мм):")
for sid in sids:
    print(f"  сечение {sid}: " + "; ".join(
        f"{p['angle']:.1f}° (зона {p['zone_center']:.1f}°, {p['depth']:.2f} мм)"
        for p in PITS[sid]))

def eval_layout(n, phase, model_cfg):
    """RMSE по сетке + локальные ошибки у дна ям и на берегах."""
    rmses, near6, banks16, align = [], [], [], []
    nd = node_angles(n, phase)
    for sid in sids:
        s = sections[sid]
        _, y = fit_layout(s, grid, model_cfg, n, phase)
        err = y - s["ideal_grid"]
        rmses.append(float(np.sqrt(np.mean(err ** 2))))
        for p in PITS[sid]:
            align.append(float(np.min(np.abs(circ_off(p["angle"], nd)))))
            dx = circ_off(grid, p["angle"])
            near6.append(float(np.max(np.abs(err[np.abs(dx) <= 6.0]))))
            bank = (np.abs(dx) > 6.0) & (np.abs(dx) <= 16.0)
            banks16.append(float(np.max(np.abs(err[bank]))))
    return {"rmse": float(np.mean(rmses)), "near6": float(np.max(near6)),
            "bank16": float(np.max(banks16)), "align": float(np.mean(align)),
            "align_max": float(np.max(align)), "per_section": rmses}

def scan(n, model_cfg, step=0.5):
    sector = 360.0 / n
    rows = []
    for ph in np.arange(0.0, sector, step):
        r = eval_layout(n, ph, model_cfg)
        nodes, margins = layout_margins(n, ph, union, cfg["guard_deg"])
        r.update({"n": n, "phase": float(ph), "margin": float(np.min(margins)),
                  "in_zone": int(np.sum(margins < 0))})
        rows.append(r)
    return rows

t0 = time.perf_counter()
for n in (6, 7, 8, 9):
    rows = scan(n, cfg["model"])
    by_margin = max(rows, key=lambda r: (r["margin"], -r["rmse"]))
    by_rmse = min(rows, key=lambda r: r["rmse"])
    by_align = min(rows, key=lambda r: (r["align"], r["rmse"]))
    print(f"\n=== N={n} (перебор {len(rows)} фаз, шаг 0.5°) ===")
    print("вариант                фаза,°  отступ_мин  в_зоне  RMSE,мм  макс±6°  "
          "берега16°  выравн_на_дно,°")
    for name, r in (("chosen (отступ max)", by_margin),
                    ("min RMSE", by_rmse),
                    ("узел на дно ямы", by_align)):
        print(f"{name:<22} {r['phase']:>6.2f}  {r['margin']:>10.2f}  "
              f"{r['in_zone']:>6}  {r['rmse']:.4f}  {r['near6']:.4f}  "
              f"{r['bank16']:>9.4f}  {r['align']:>14.2f}")
    print("  топ-5 по RMSE: " + " | ".join(
        f"{r['phase']:.2f}:{r['rmse']:.4f}(выр {r['align']:.1f})"
        for r in sorted(rows, key=lambda r: r["rmse"])[:5]))
    print("  топ-5 по выравниванию: " + " | ".join(
        f"{r['phase']:.2f}:выр {r['align']:.2f} макс {r['align_max']:.2f} "
        f"RMSE {r['rmse']:.4f}" for r in sorted(rows, key=lambda r: r["align"])[:5]))

print(f"\n(перебор занял {time.perf_counter() - t0:.1f} с)")

print("\n=== А/Б: N=7 — фаза и роль overlap_train ===")
m0 = dict(cfg["model"])
m_no = dict(cfg["model"])
m_no["overlap_train"] = 0.0
cases = [("фаза 24.75° (текущая, узел 18.3° от дна)", 24.75, m0),
         ("фаза 6.33°  (узел НА дне 315°)", 6.33, m0),
         ("фаза 6.33°  + overlap_train=0", 6.33, m_no),
         ("фаза 24.75° + overlap_train=0", 24.75, m_no)]
for name, ph, mc in cases:
    r = eval_layout(7, ph, mc)
    nd = ", ".join(f"{a:.1f}" for a in sorted(node_angles(7, ph)))
    print(f"{name:<40} RMSE {r['rmse']:.4f}  макс±6° {r['near6']:.4f}  "
          f"берега16° {r['bank16']:.4f}")
    print(f"      узлы: {nd}")
    print("      RMSE по сечениям " + ", ".join(f"{sid}:{v:.4f}"
                                               for sid, v in zip(sids, r["per_section"])))

print("\n=== В: N=8 — узлы ровно на дно ям (90° и 315°) ===")
for name, ph in (("фаза 0°  (узлы на дне 90/315)", 0.0),
                 ("фаза 22.5° (узел в середине ямы)", 22.5)):
    r = eval_layout(8, ph, m0)
    nd = ", ".join(f"{a:.1f}" for a in sorted(node_angles(8, ph)))
    print(f"{name:<33} RMSE {r['rmse']:.4f}  макс±6° {r['near6']:.4f}  "
          f"берега16° {r['bank16']:.4f}  выравн {r['align']:.2f}")
    print(f"      узлы: {nd}")

print("\n=== Г: N=9 ===")
for name, ph in (("фаза 0°", 0.0), ("фаза 355° (узел ~315)", 355.0),
                 ("фаза 20°", 20.0)):
    r = eval_layout(9, ph, m0)
    print(f"{name:<26} RMSE {r['rmse']:.4f}  макс±6° {r['near6']:.4f}  "
          f"берега16° {r['bank16']:.4f}  выравн {r['align']:.2f}")

print("\n=== Д: разрез по сечениям (почему «узел на дно» помогает одному и вредит остальным) ===")
print("Дно ямы 3 плывёт по высоте: 314.9°(s0) -> 311.6/306.5°(s2) -> "
      "306.5/299.7°(s5) -> 299.8°(s9); у ям 1 и 2 дрейф тоже ~+20°.")
for n, phases in ((8, (0.0, 22.5, 35.5)), (9, (0.0, 20.0, 355.0))):
    nodes_of = {ph: sorted(node_angles(n, ph)) for ph in phases}
    print(f"\nN={n}")
    print("  фаза,° | выравн.средн | " + " | ".join(f"сеч {sid}" for sid in sids))
    for ph in phases:
        per, aligns = [], []
        nd = np.array(nodes_of[ph])
        for k, sid in enumerate(sids):
            r = eval_layout(n, ph, dict(cfg["model"]))
            per.append(r["per_section"][k])
            aligns += [float(np.min(np.abs(circ_off(p["angle"], nd))))
                       for p in PITS[sid]]
        print(f"  {ph:>6.1f} | {np.mean(aligns):>12.2f} | " +
              " | ".join(f"{v:.4f}" for v in per))

print("\n=== Е: сохраняется ли ГЛУБИНА ямы, когда стык стоит на её дне (сечение 0) ===")
s0 = sections[0]
for ph in (24.75, 6.33):
    _, y = fit_layout(s0, grid, dict(cfg["model"]), 7, ph)
    dx = circ_off(grid, 314.9)
    m = np.abs(dx) <= 10.0
    ideal_min = float(s0["ideal_grid"][m].min())
    node_val = float(np.interp(314.9, grid, y))
    print(f"N=7 фаза {ph:>5.2f}: min модели у ямы {y[m].min():.4f} мм, "
          f"эталон {ideal_min:.4f} мм, недобор {y[m].min() - ideal_min:+.4f} мм; "
          f"значение ровно на узле 314.9° (если узел там): {node_val:.4f} мм")
print("Ожидание гипотезы: с узлом на дне полином не выгибается -> недобор "
      "меньше. Факт: узел на дне = среднее двух полиномов в точке минимума.")
