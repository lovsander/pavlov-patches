"""
make_conformance.py

Сгенерировать КОНФОРМАНС-ВЕКТОРЫ — «золотые» пары «вход → ожидаемый выход» для
проверки любого порта (CONTEXT §27). Векторы строит референс на Python, а
проверяет их C++-утилита pappa_conformance (см. cpp/conformance.cpp и
spec/conformance/README.md).

ПОЧЕМУ вход синтетический, а не synthetic_data.csv: вектор должен быть маленьким,
читаемым и воспроизводимым без вспомогательных файлов — тогда его можно
закоммитить и использовать в любом языке. Профиль задан аналитически (основа +
две ямы + детерминированная рябь).

ТРИ ВИДА ВЕКТОРОВ = ТРИ СТУПЕНИ ПАЙПЛАЙНА (проверяются по отдельности, чтобы
падение сразу говорило, ГДЕ расхождение):
  model    — обучение модели: степени, коэффициенты, термины фичера, контур;
  detector — поиск ям (band): зоны и центры;
  cleaner  — авто-очистка выбросов: сколько и какие точки отброшены.

Запуск: <python> make_conformance.py [--out spec/conformance/vectors]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

from pappa.analysis.zones import detect_zones, indicator_curve
from pappa.core.outlier_cleaner import AutoOutlierCleaner
from pappa.core.pit_feature import MODEL_DEFAULTS, PIT_DEFAULTS, build_model
from pappa.paths import REPO_ROOT

FORMAT = "pappa-conformance"
VERSION = "1.0"

# Допуски для портов. Коэффициенты сравниваются как у чисел с плавающей точкой:
# |Δc| <= max(coefs_abs_floor, coefs_rel * |c_ожид|) — разные корректные
# МНК-решатели (numpy lstsq/SVD и QR Хаусхолдера) дают на расширенном ямном
# базисе расхождение ~1e-9, и абсолютный порог 1e-9 ловил бы не ошибку порта,
# а разницу алгоритмов. Критерий, который действительно важен, — контур
# (curve_mm); детектор и очистка — доля точек.
TOLERANCE = {"coefs_rel": 1e-9, "coefs_abs_floor": 1e-8,
             "curve_mm": 1e-6, "frac": 0.02}

MODEL_CFG = dict(MODEL_DEFAULTS)


def profile(angles, with_pits=True, ripple=0.01):
    """Аналитический профиль: основа + две ямы (90° и 210°) + детерминированная рябь."""
    a = np.deg2rad(angles)
    r = 15.0 + 0.4 * np.sin(2.0 * a) + 0.2 * np.cos(3.0 * a)
    if with_pits:
        r = (r - 1.1 * np.exp(-((angles - 90.0) / 2.5) ** 2)
             - 0.8 * np.exp(-((angles - 210.0) / 2.0) ** 2))
    return r + ripple * np.sin(np.deg2rad(37.0 * angles))


def vector_model(name, angles, radii, pits, curve_step=0.5):
    """Вектор «обучение модели»: ожидаемые степени, коэффициенты, термины, контур."""
    model = build_model(MODEL_CFG, pits=pits or None)
    model.fit(angles, radii)

    grid = np.arange(0.0, 360.0, curve_step)
    coefs = [[float(c) for c in p["coefs"]] for p in model.patches_]
    # у чистой полиномиальной модели ключей фичера нет вообще — .get
    terms = [{"dx_deg": [float(d) for d in p.get("pit_offsets", [])],
              "amp": [float(v) for v in p.get("pit_coefs", [])]}
             for p in model.patches_]
    cfg = {k: MODEL_CFG[k] for k in ("n_patches", "phase_deg", "deg_min",
                                     "deg_max", "overlap_train", "overlap_use",
                                     "deg_elbow_tol")}
    cfg["coord_mode"] = "normalized"
    cfg["pits_deg"] = [float(p) for p in (pits or [])]
    if pits:
        cfg.update({k: PIT_DEFAULTS[k] for k in PIT_DEFAULTS})

    return {
        "format": FORMAT, "version": VERSION, "kind": "model", "name": name,
        "description": ("фичер ям выключен" if not pits else
                        "фичер ям включён, центры ям заданы вектором"),
        "tolerance": TOLERANCE,
        "config": cfg,
        "input": {"angles_deg": [float(a) for a in angles],
                  "radii_mm": [float(r) for r in radii]},
        "expected": {
            "degrees": [int(d) for d in model.degrees_],
            "coefs": coefs,
            "pit_terms": terms,
            "curve": {"angles_deg": [float(a) for a in grid],
                      "radii_mm": [float(v) for v in model.eval(grid)]},
        },
    }


def vector_detector(name, angles, radii, cfg=None):
    """Вектор «детектор ям»: ожидаемые зоны и центры."""
    det = {"kind": "band", "window_deg": 1.0, "wide_deg": 10.0,
           "smooth_deg": 2.0, "k": 5.5, "min_zone_deg": 2.0}
    if cfg:
        det.update(cfg)
    band = indicator_curve(angles, radii, det["kind"], window_deg=det["window_deg"],
                           envelope_deg=0.5, smooth_deg=det["smooth_deg"],
                           wide_deg=det["wide_deg"])
    zones = detect_zones(angles, band, det["k"], det["min_zone_deg"])
    return {
        "format": FORMAT, "version": VERSION, "kind": "detector", "name": name,
        "description": "поиск ям: индикатор band и зоны по порогу",
        "tolerance": TOLERANCE,
        "config": det,
        "input": {"angles_deg": [float(a) for a in angles],
                  "radii_mm": [float(r) for r in radii]},
        "expected": {
            "zones_deg": [[float(a), float(b)] for a, b in zones],
            "pits_deg": [float(0.5 * (a + b)) for a, b in zones],
        },
    }


def vector_cleaner(name, angles, radii, cfg=None):
    """Вектор «авто-очистка»: ожидаемые номера отброшенных точек."""
    params = {"baseline_deg": 1.0, "iqr_k": 3.0}
    if cfg:
        params.update(cfg)
    cleaner = AutoOutlierCleaner(**params)
    mask = cleaner.clean(angles, radii)
    idx = [int(i) for i in np.flatnonzero(mask)]
    return {
        "format": FORMAT, "version": VERSION, "kind": "cleaner", "name": name,
        "description": "авто-iqr: остатки к локальному медианному уровню, усы Тьюки",
        "tolerance": TOLERANCE,
        "config": params,
        "input": {"angles_deg": [float(a) for a in angles],
                  "radii_mm": [float(r) for r in radii]},
        "expected": {"n_outliers": len(idx), "mask_true_indices": idx,
                     "n_points": int(len(radii))},
    }


def build_vectors():
    """Собрать все векторы (имена фиксированы — их видят порты)."""
    angles = np.arange(0.0, 360.0, 1.0)                 # шаг 1° — маленький файл
    radii_plain = profile(angles, with_pits=False, ripple=0.004)
    radii_pits = profile(angles, with_pits=True)
    pits_known = [90.0, 210.0]                          # центры, видимые детектору

    # очистка: тот же профиль + детерминированные всплески (каждый 97-й)
    radii_spiky = radii_plain.copy()
    radii_spiky[np.arange(5, len(radii_plain), 97)] += 0.9

    vectors = [
        vector_model("model_patches_only", angles, radii_plain, pits=None),
        vector_model("model_with_pits", angles, radii_pits, pits=pits_known),
        vector_detector("detector_band_two_pits", angles, radii_pits),
        vector_cleaner("cleaner_iqr_spikes", angles, radii_spiky),
    ]
    return vectors


def main():
    ap = argparse.ArgumentParser(description="Сгенерировать конформанс-векторы")
    ap.add_argument("--out", default=str(REPO_ROOT / "spec" / "conformance" / "vectors"),
                    help="каталог для векторов")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    vectors = build_vectors()
    for i, vec in enumerate(vectors, start=1):
        path = out_dir / f"vector_{i:02d}_{vec['kind']}_{vec['name']}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(vec, f, indent=1, ensure_ascii=False)
        print(f"записан {path.name}: {vec['kind']}, точек {len(vec['input']['radii_mm'])}")

    print(f"\nВекторов: {len(vectors)} в {out_dir}")
    print("Проверка портов: cpp pappa_conformance (см. cpp/conformance.cpp)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

