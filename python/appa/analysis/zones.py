"""
defect_map.py

«Карта дефектности» кольцевого профиля: где поверхность гладкая, а где есть
трещина/яма. Модуль общий для двух скриптов:

  explore_baseline_defects.py — показывает работу median_filter_wrap и ход
                                исследования «производные как признак дефекта»;
  explore_star_layout.py     — выбирает раскладку патчей так, чтобы границы
                                (узлы) попадали на гладкие участки.

Понятия (простыми словами):
  baseline — локальный робастный уровень профиля: скользящая медиана по кольцу
             (median_filter_wrap). Следит за формой (эллипс, конусность, волна),
             но не «проваливается» в одиночные всплески-выбросы.
  res      — остаток r − baseline: шум и одиночные всплески;
  d1       — |первая разность baseline|: наклон поверхности;
  d2       — |вторая разность baseline|: кривизна поверхности;
  band     — |baseline − широкая медиана|: «полоса» между двумя масштабами.
             Измерено на synthetic_data.csv: точечные производные d1/d2 на шаге
             0.06° тонут в шуме и трещину не находят, а band находит все трещины
             без ложных зон — он сравнивает два масштаба, а не два отсчёта.
  Каждый индикатор делится на свою робастную sigma, поэтому он безразмерный и не
  зависит от диаметра, шага по углу и уровня шума. Единица измерения — «MAD-ы».

Истинные зоны трещин берутся не из догадок, а из таблицы трещин генератора
(synthetic_data.csv сделан generate_data_crack_many.py). Таблица читается здесь
через ast: импортировать генератор нельзя — у него нет __main__-guard, и импорт
заново сгенерировал бы CSV.
"""

import ast
from pathlib import Path

import numpy as np

from ..core.outlier_cleaner import angular_step, median_filter_wrap, robust_sigma, window_points
from ..paths import PY_ROOT


GENERATOR_FILE = "generate_data_crack_many.py"
GENERATOR_PATH = PY_ROOT / "generator" / GENERATOR_FILE


# ============================================================================
# ЧТЕНИЕ ТАБЛИЦЫ ТРЕЩИН ИЗ ГЕНЕРАТОРА (без импорта модуля)
# ============================================================================

def _generator_literals(gen_path=None):
    """
    Литеральные константы генератора: CRACKS, TOTAL_HEIGHT, N_SECTIONS, ...

    Читаем исходник через ast и забираем присваивания, которые можно вычислить
    как литерал. Выражения (TOTAL_HEIGHT = (N_SECTIONS - 1) * HEIGHT_STEP)
    пропускаем — их досчитываем в load_crack_table().
    """
    path = Path(gen_path) if gen_path else GENERATOR_PATH
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], "id", None)
        if name is None:
            continue
        try:
            out[name] = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
    return out


def load_crack_table(gen_path=None):
    """
    Таблица трещин генератора.

    Возвращает dict: {'cracks': [...], 'total_height_mm': float,
                      'profile': 'gauss'|'triangle', 'source': путь}
    """
    path = Path(gen_path) if gen_path else GENERATOR_PATH
    lit = _generator_literals(path)
    total = lit.get("TOTAL_HEIGHT")
    if total is None:                      # ровно как в генераторе
        total = (lit["N_SECTIONS"] - 1) * lit["HEIGHT_STEP"]
    return {
        "cracks": lit["CRACKS"],
        "total_height_mm": float(total),
        "profile": lit.get("CRACK_PROFILE", "gauss"),
        "source": str(path),
    }


def crack_delta_deg(angles_deg, height_mm, crack, total_height_mm, profile="gauss"):
    """
    Глубина одной трещины (мм, отрицательная) в точках angles_deg.

    Формула повторена 1:1 из generate_data_crack_many.crack_profile().
    """
    t = height_mm / total_height_mm if total_height_mm > 0 else 0.0
    t = float(np.clip(t, 0.0, 1.0))

    angle_c = crack["angle_bottom"] + (crack["angle_top"] - crack["angle_bottom"]) * t
    width = crack["width_bottom"] + (crack["width_top"] - crack["width_bottom"]) * t
    depth = crack["depth_bottom"] + (crack["depth_top"] - crack["depth_bottom"]) * t

    a = np.asarray(angles_deg, dtype=float)
    d = np.abs((a - angle_c + 180.0) % 360.0 - 180.0)

    if profile == "gauss":
        sigma = (width / 2.0) / 2.5
        return -depth * np.exp(-(d ** 2) / (2.0 * sigma ** 2))

    half = width / 2.0
    return np.where(d < half, -depth * (1.0 - d / half), 0.0)


def crack_delta_all(angles_deg, height_mm, table):
    """Суммарный профиль всех трещин на данной высоте, мм."""
    a = np.asarray(angles_deg, dtype=float)
    delta = np.zeros_like(a)
    for crack in table["cracks"]:
        delta += crack_delta_deg(a, height_mm, crack, table["total_height_mm"],
                                 table["profile"])
    return delta


def truth_zone_mask(angles_deg, height_mm, table, depth_frac=0.05):
    """
    Истинные зоны трещин: где трещина глубже, чем depth_frac от максимальной
    глубины на этом сечении. depth_frac=0.05 даёт зону примерно по номинальной
    ширине из таблицы трещин.
    """
    a = np.asarray(angles_deg, dtype=float)
    delta = crack_delta_all(a, height_mm, table)
    depth = float(-np.min(delta)) if np.any(delta < 0) else 0.0
    if depth <= 0:
        return np.zeros(len(a), dtype=bool)
    return delta < -depth_frac * depth


def crack_depths_mm(height_mm, table):
    """Глубина каждой трещины (мм, положительная) на данной высоте."""
    out = []
    for crack in table["cracks"]:
        t = height_mm / table["total_height_mm"] if table["total_height_mm"] > 0 else 0.0
        t = float(np.clip(t, 0.0, 1.0))
        out.append(crack["depth_bottom"] + (crack["depth_top"] - crack["depth_bottom"]) * t)
    return np.array(out, dtype=float)

# ============================================================================
# ИНДИКАТОРЫ ДЕФЕКТНОСТИ
# ============================================================================

def wrap_diff(x):
    """Первая разность по КОЛЬЦУ (последняя точка -> первая)."""
    x = np.asarray(x, dtype=float)
    return np.diff(np.concatenate([x, x[:1]]))


def smooth_wrap(x, window):
    """Скользящее среднее по кольцу (окно в точках, приводится к нечётному)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    w = max(3, int(round(window)) | 1)
    if n < 3 or w > n:
        w = n if n % 2 == 1 else max(1, n - 1)
    if w < 3:
        return x.copy()
    h = w // 2
    ext = np.concatenate([x[-h:], x, x[:h]])
    return np.convolve(ext, np.ones(w) / w, mode="valid")


def ring_normalize(values, eps=1e-12):
    """Деление на собственную робастную sigma -> безразмерная шкала («MAD-ы»)."""
    v = np.asarray(values, dtype=float)
    s = robust_sigma(v)
    return v / s if s > eps else np.zeros_like(v)


def defect_maps(angles, radii, baseline_deg=1.0, envelope_deg=0.5,
                wide_deg=10.0, smooth_deg=2.0):
    """
    Локальный уровень профиля и индикаторы дефектности (все — в MAD).

    baseline — узкая медиана (окно baseline_deg): следит за рельефом,
               включая трещину;
    wide     — широкая медиана (окно wide_deg): трещину для неё «размывает»;
    res      — |r − baseline|: шум и одиночные всплески;
    band     — |baseline − wide|: «полоса» между узким и широким уровнем.

    Результат исследования (см. explore_baseline_defects.py): точечные производные
    d1/d2 на этих данных упираются в шум (шум между соседними отсчётами при шаге
    0.06° много больше наклона трещины), а band находит ВСЕ трещины без ложных
    зон — он сравнивает два масштаба, а не два соседних отсчёта.

    Все индикаторы сглаживаются (окно smooth_deg) и делятся на свою робастную
    sigma, поэтому они безразмерные и порог k задаётся в «MAD-ах».

    Возвращает dict:
      baseline, wide, res (мм), sigma_res_mm,
      env_norm  — огибающая |r − baseline|;
      d1_norm, d2_norm — точечные производные узкого уровня (СГЛАЖЕННЫЕ, иначе шум);
      d1_raw_norm, d2_raw_norm — те же производные без сглаживания (для сравнения);
      band_norm — полоса |baseline − wide|;
      window_points / window_deg — фактическое окно узкой медианы.
    """
    a = np.asarray(angles, dtype=float)
    r = np.asarray(radii, dtype=float)

    w = window_points(a, baseline_deg)
    baseline = median_filter_wrap(r, w)
    wide = median_filter_wrap(r, window_points(a, wide_deg))

    res = np.abs(r - baseline)
    env = smooth_wrap(res, window_points(a, envelope_deg))

    d1_raw = np.abs(wrap_diff(baseline))
    d2_raw = np.abs(wrap_diff(wrap_diff(baseline)))
    sw = window_points(a, smooth_deg)
    d1 = smooth_wrap(d1_raw, sw)
    d2 = smooth_wrap(d2_raw, sw)

    band = smooth_wrap(np.abs(baseline - wide), sw)

    def norm(x):
        s = robust_sigma(x)
        x = np.asarray(x, dtype=float)
        return x / s if s > 1e-12 else np.zeros_like(x)

    return {
        "baseline": baseline,
        "wide": wide,
        "res": res,
        "env_norm": norm(env),
        "d1_norm": norm(d1),
        "d2_norm": norm(d2),
        "d1_raw_norm": norm(d1_raw),
        "d2_raw_norm": norm(d2_raw),
        "band_norm": norm(band),
        "sigma_res_mm": robust_sigma(r - baseline),
        "window_points": int(w),
        "window_deg": float(w * angular_step(a)),
    }


def indicator_curve(angles, radii, kind, window_deg=1.0, envelope_deg=0.5,
                    smooth_deg=2.0, wide_deg=10.0):
    """
    Один индикатор дефектности на упорядоченной по углу сетке (в MAD-ах).

    kind: "band"   — |узкая медиана − широкая медиана| (рекомендуемый);
          "env"    — огибающая |r − узкая медиана|;
          "d1"     — |Δ узкая медиана| (сглаженная);
          "d2"     — |Δ² узкая медиана| (сглаженная);
          "d1_raw" — то же без сглаживания (шумно, для сравнения);
          "d2_raw" — то же без сглаживания.
    """
    field = {"band": "band_norm", "env": "env_norm", "d1": "d1_norm",
             "d2": "d2_norm", "d1_raw": "d1_raw_norm", "d2_raw": "d2_raw_norm"}
    if kind not in field:
        raise ValueError(f"неизвестный индикатор дефектности: {kind!r}")

    maps = defect_maps(angles, radii, baseline_deg=window_deg,
                       envelope_deg=envelope_deg, wide_deg=wide_deg,
                       smooth_deg=smooth_deg)
    return maps[field[kind]]


# ============================================================================
# ЗОНЫ И ИХ ОЦЕНКА
# ============================================================================

def mask_to_zones(angles, mask, min_len_deg=0.5):
    """
    Непрерывные зоны (интервалы углов) по маске на упорядоченной по углу сетке.

    Зона, доходящая до 360° и начинающаяся с 0°, склеивается в одну (кольцо).
    """
    a = np.asarray(angles, dtype=float)
    m = np.asarray(mask, dtype=bool)
    order = np.argsort(a)
    a, m = a[order], m[order]
    n = len(a)
    if n == 0 or not np.any(m):
        return []

    step = float(np.median(np.diff(a))) if n > 1 else 1.0

    zones = []
    i = 0
    while i < n:
        if not m[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and m[j + 1]:
            j += 1
        zones.append([float(a[i] - step / 2), float(a[j] + step / 2)])
        i = j + 1

    if len(zones) > 1 and m[0] and m[-1]:      # кольцо: первая и последняя — одна
        first = zones.pop(0)
        last = zones.pop(-1)
        zones.insert(0, [last[0] - 360.0, first[1]])

    return [z for z in zones if z[1] - z[0] >= min_len_deg]


def overlap_deg(z1, z2):
    """Перекрытие двух угловых интервалов, ° (без учёта кольца)."""
    return max(0.0, min(z1[1], z2[1]) - max(z1[0], z2[0]))


def score_zones(detected, truth, min_overlap=0.2):
    """
    Честная оценка ЗОН (а не точек):
      * обнаруженная зона — совпавшая (tp_zones), если не меньше min_overlap её
        длины лежит внутри какой-нибудь истинной зоны, иначе ложная (fp);
      * истинная зона — найденная (tp), если её перекрывает хоть одна
        обнаруженная зона, иначе пропущенная (fn).

    precision = tp_zones / (tp_zones + fp), recall = tp / len(truth).
    Возвращает также tp_zones — сколько обнаруженных зон «попали» (их может быть
    больше, чем трещин, если одна трещина дала две зоны — тогда fp остаётся 0).
    """
    tp_zones = fp = 0
    covered = [False] * len(truth)

    for dz in detected:
        length = dz[1] - dz[0]
        if length <= 0:
            continue
        best = 0.0
        for ti, tz in enumerate(truth):
            ov = overlap_deg(dz, tz)
            if ov > 0:
                best = max(best, ov)
                if ov / length >= min_overlap:
                    covered[ti] = True
        if best / length >= min_overlap:
            tp_zones += 1
        else:
            fp += 1

    tp = int(sum(1 for c in covered if c))
    fn = len(truth) - tp
    precision = tp_zones / (tp_zones + fp) if tp_zones + fp else 0.0
    recall = tp / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "detected": len(detected), "truth": len(truth),
        "tp": tp, "tp_zones": tp_zones, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
    }


def detect_zones(angles, values_norm, k, min_len_deg=0.5):
    """Зоны, где безразмерный индикатор превышает порог k."""
    return mask_to_zones(angles, np.asarray(values_norm) > k, min_len_deg)


if __name__ == "__main__":
    # Быстрая самопроверка модуля (без графики): таблица трещин и зоны.
    table = load_crack_table()
    print(f"Таблица трещин: {table['source']}")
    print(f"  трещин: {len(table['cracks'])}, полная высота: "
          f"{table['total_height_mm']:g} мм, профиль: {table['profile']}")
    grid = np.arange(0.0, 360.0, 0.06)
    for h in (0.0, 22.5, 45.0):
        depths = crack_depths_mm(h, table)
        zones = mask_to_zones(grid, truth_zone_mask(grid, h, table, 0.05), 0.1)
        print(f"  h={h:5.1f} мм: глубины {np.round(depths, 2)} мм, "
              f"истинных зон {len(zones)}: "
              + ", ".join(f"{z[0]:.1f}..{z[1]:.1f}°" for z in zones))
