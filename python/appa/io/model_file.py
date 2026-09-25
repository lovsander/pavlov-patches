"""
appa/io/model_file.py

Сериализация модели (PatchApproximator / PitPatchApproximator) в документ
описания сечения — формат .appa.json (v2.0).

ПОЧЕМУ ПЕРЕИМЕНОВАНО из pmodel (2026-09-24, CONTEXT §27): слово pmodel не
коррелировало с именем метода (APPA / пакет appa). Старые документы
(format="pmodel", version="1.0") ЧИТАЮТСЯ прежним кодом через слой
совместимости в load_model/validate_model.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


FORMAT_NAME = "appa"
FORMAT_VERSION = "2.0"

# формат-предшественник (до переименования): читаем, но не пишем
LEGACY_FORMAT_NAME = "pmodel"
LEGACY_VERSIONS = ("1.0",)


def _appa_version():
    """Версия пакета appa — в документе видно, чем он записан (без цикла импортов)."""
    from .. import __version__
    return str(__version__)


# ============ SAVE ============

def save_model(approx, filepath, meta=None):
    """
    Сохранить обученную модель в документ .appa.json.

    approx : PatchApproximator / PitPatchApproximator (уже fitted)
    filepath : путь к файлу
    meta : опциональный dict с section_id, height_mm, source, description
    """
    if not approx.is_fitted_:
        raise RuntimeError("Модель не обучена — вызовите fit()")

    meta = meta or {}

    data = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "method": type(approx).__name__,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "software": {
            "language": "python",
            "appa_version": _appa_version(),
        },
        "meta": {
            "section_id": meta.get("section_id", 0),
            "height_mm": meta.get("height_mm", 0.0),
            "source": meta.get("source", "unknown"),
            "description": meta.get("description", ""),
        },
        "global": {
            "units": {"angle": "degree", "length": "mm"},
            "n_patches": int(approx.n_patches),
            "half_sector_deg": float(approx.half_sector_),
            "phase_deg": float(getattr(approx, "phase_deg", 0.0)),
            "half_train_deg": float(approx.half_sector_ + approx.overlap_train),
            "half_use_deg": float(approx.half_sector_ + approx.overlap_use),
            "overlap_train_deg": float(approx.overlap_train),
            "overlap_use_deg": float(approx.overlap_use),
            "deg_min": int(approx.deg_min),
            "deg_max": int(approx.deg_max),
            # канон координат коэффициентов: "normalized" -> x / half_train ∈ [-1,1]
            "coord_mode": str(getattr(approx, "coord_mode", "normalized")),
            # политика степени: RMSE-«локоть» на обучающем окне
            "deg_elbow_tol": float(getattr(approx, "deg_elbow_tol", 0.05)),
            # историческая амплитудная шкала, на выбор степени не влияет
            "amplitude_scale": float(approx.amplitude_scale),
        },
        "patches": [],
        "statistics": approx.statistics_ if hasattr(approx, "statistics_") else {},
    }

    for p in approx.patches_:
        patch = {
            "center_deg": float(p["center"]),
            "degree": int(p["degree"]),
            "n_points": int(p.get("n_points", 0)),
            "coefs": [float(c) for c in p["coefs"]],
        }
        if "metrics" in p:
            patch["metrics"] = {k: float(v) for k, v in p["metrics"].items()}
        if "stats" in p:
            patch["stats"] = {k: float(v) for k, v in p["stats"].items()}
        data["patches"].append(patch)

    filepath = Path(filepath)
    with filepath.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath


# ============ LOAD ============

def load_model(filepath):
    """
    Загрузить модель из документа .appa.json (или старого .pmodel.json v1.0).
    Возвращает модель (fitted), готовую к eval().
    """
    from ..core.patch_approximator import PatchApproximator

    filepath = Path(filepath)
    with filepath.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Проверка формата. Документ-предшественник (pmodel v1.0) читается: структура
    # та же, отличается только имя формата и версия (и, как правило, coord_mode
    # отсутствует -> коэффициенты в сырых градусах, см. ниже).
    fmt = str(data.get("format", ""))
    ver = str(data.get("version", ""))
    if fmt == FORMAT_NAME:
        if ver != FORMAT_VERSION:
            raise ValueError(f"Неподдерживаемая версия: {ver!r}")
    elif fmt == LEGACY_FORMAT_NAME and ver in LEGACY_VERSIONS:
        data["format"] = FORMAT_NAME
        data["version"] = FORMAT_VERSION
    else:
        raise ValueError(f"Не документ APPA: format={fmt!r}, version={ver!r}")

    g = data["global"]

    approx = PatchApproximator(
        n_patches=int(g["n_patches"]),
        deg_min=int(g["deg_min"]),
        deg_max=int(g["deg_max"]),
        amplitude_scale=float(g["amplitude_scale"]),
        overlap_train=float(g["overlap_train_deg"]),
        overlap_use=float(g["overlap_use_deg"]),
        phase_deg=float(g.get("phase_deg", 0.0)),
        # старые файлы без поля допуска читаются как 0.05
        deg_elbow_tol=float(g.get("deg_elbow_tol", 0.05)),
        # старые файлы писали коэффициенты в СЫРЫХ градусах (до канона [-1,1]);
        # читаем так же, иначе модель считалась бы неверно
        coord_mode=str(g.get("coord_mode", "raw")),
    )

    # Восстанавливаем состояние
    approx.half_sector_ = float(g["half_sector_deg"])
    approx.centers_ = [p["center_deg"] for p in data["patches"]]
    approx.patches_ = []
    approx.degrees_ = []

    for p in data["patches"]:
        patch = {
            "center": float(p["center_deg"]),
            "degree": int(p["degree"]),
            "n_points": int(p.get("n_points", 0)),
            "coefs": [float(c) for c in p["coefs"]],
            "half_sector": float(g["half_sector_deg"]),
            "half_train": float(g["half_train_deg"]),
            "half_use": float(g["half_use_deg"]),
        }
        if "metrics" in p:
            patch["metrics"] = {k: float(v) for k, v in p["metrics"].items()}
        if "stats" in p:
            patch["stats"] = {k: float(v) for k, v in p["stats"].items()}
        approx.patches_.append(patch)
        approx.degrees_.append(patch["degree"])

    import numpy as np
    approx.degrees_ = np.array(approx.degrees_)
    approx.statistics_ = data.get("statistics", {})
    approx.is_fitted_ = True
    approx.meta_ = data.get("meta", {})

    return approx


# ============ VALIDATE ============

def validate_model(filepath):
    """
    Проверка структуры файла. Возвращает (ok, errors).
    Без JSON Schema — базовые проверки.
    """
    errors = []
    try:
        with Path(filepath).open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"JSON parse error: {e}"]

    # Обязательные поля
    for key in ("format", "version", "global", "patches"):
        if key not in data:
            errors.append(f"Missing field: {key}")

    if str(data.get("format", "")) != FORMAT_NAME and not (
            str(data.get("format", "")) == LEGACY_FORMAT_NAME
            and str(data.get("version", "")) in LEGACY_VERSIONS):
        errors.append(f"Wrong format: {data.get('format')} v{data.get('version')}")

    if "global" in data:
        g = data["global"]
        for key in ("n_patches", "half_sector_deg", "deg_min", "deg_max"):
            if key not in g:
                errors.append(f"global.{key} missing")

        # канон координат: поле необязательное (старые файлы его не писали),
        # но если есть — значение должно быть известным
        mode = g.get("coord_mode")
        if mode is not None and mode not in ("normalized", "raw"):
            errors.append(f"global.coord_mode неизвестен: {mode!r}")

        if "patches" in data and "n_patches" in g:
            n = int(g["n_patches"])
            if len(data["patches"]) != n:
                errors.append(f"patches count {len(data['patches'])} != n_patches {n}")

        # Проверка центров
        if "patches" in data and "half_sector_deg" in g and "n_patches" in g:
            hs = float(g["half_sector_deg"])
            np_ = int(g["n_patches"])
            phase = float(g.get("phase_deg", 0.0))
            step = 360.0 / np_
            for i, p in enumerate(data["patches"]):
                expected = (i * step + hs + phase) % 360.0
                actual = float(p.get("center_deg", -1))
                if abs(actual - expected) > 1e-6:
                    errors.append(
                        f"patch[{i}].center_deg={actual} != expected {expected}"
                    )

    # Проверка патчей
    for i, p in enumerate(data.get("patches", [])):
        if "center_deg" not in p:
            errors.append(f"patch[{i}]: missing center_deg")
        if "degree" not in p:
            errors.append(f"patch[{i}]: missing degree")
        if "coefs" not in p:
            errors.append(f"patch[{i}]: missing coefs")
            continue
        deg = int(p["degree"])
        n_coefs = len(p["coefs"])
        if n_coefs != deg + 1:
            errors.append(
                f"patch[{i}]: coefs len {n_coefs} != degree+1 {deg+1}"
            )

        # Проверка политики степени.
        # Новая политика (RMSE-«локоть») проверяется по сохранённым метрикам:
        # выбранная степень должна быть допустимой, чётной и её RMSE не хуже
        # лучшего RMSE более чем на допуск.
        # Старые файлы (без rmse_best_mm) проверяются по историческому правилу
        # «degree из amplitude_norm * amplitude_scale».
        if "metrics" in p and "global" in data:
            g = data["global"]
            dmin = int(g["deg_min"])
            dmax = int(g["deg_max"])
            if deg % 2 != 0 or not (dmin <= deg <= dmax):
                errors.append(
                    f"patch[{i}]: degree {deg} вне политики "
                    f"(чётная {dmin}..{dmax})"
                )
            m = p["metrics"]
            if "rmse_best_mm" in m:
                tol = float(g.get("deg_elbow_tol", 0.05))
                limit = float(m["rmse_best_mm"]) * (1.0 + tol)
                if float(m.get("rmse_selected_mm", limit)) > limit * (1.0 + 1e-9):
                    errors.append(
                        f"patch[{i}]: degree {deg} с RMSE "
                        f"{m.get('rmse_selected_mm')} хуже допуска "
                        f"{limit:.6f} (best={m['rmse_best_mm']}, tol={tol})"
                    )
            elif "amplitude_norm" in m:
                amp_norm = float(m["amplitude_norm"])
                scale = float(g.get("amplitude_scale", 180.0))
                expected_deg = int(round(amp_norm * scale))
                if expected_deg % 2 != 0:
                    expected_deg += 1
                expected_deg = max(dmin, min(dmax, expected_deg))
                if expected_deg != deg:
                    errors.append(
                        f"patch[{i}]: degree {deg} != expected {expected_deg} "
                        f"(legacy amp_norm={amp_norm:.4f}, scale={scale})"
                    )

    return len(errors) == 0, errors


# ============ SUMMARY ============

def summary(filepath):
    """Краткий отчёт по модели в консоль."""
    with Path(filepath).open("r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"=== {filepath} ===")
    print(f"format:   {data['format']} v{data['version']}")
    print(f"method:   {data['method']}")
    print(f"created:  {data['created']}")

    meta = data.get("meta", {})
    print(f"section:  {meta.get('section_id')}, h={meta.get('height_mm')} mm")

    g = data["global"]
    print(f"n_patches: {g['n_patches']}")
    print(f"deg_min/max: {g['deg_min']}/{g['deg_max']}")
    print(f"deg_elbow_tol: {g.get('deg_elbow_tol', 0.05)} (политика: RMSE-«локоть»)")
    print(f"amplitude_scale: {g['amplitude_scale']} (legacy, степень не выбирает)")
    print(f"phase_deg: {g.get('phase_deg', 0.0)}")
    print(f"coord_mode: {g.get('coord_mode', 'raw')} "
          f"(канон: normalized = x/half_train ∈ [-1,1])")

    print("\nPatches:")
    print(f"{'#':>3} {'center':>8} {'deg':>4} {'n_pts':>6} "
          f"{'amp_mm':>8} {'amp_norm':>10} {'rmse':>10}")
    for i, p in enumerate(data["patches"]):
        m = p.get("metrics", {})
        s = p.get("stats", {})
        print(f"{i:>3} {p['center_deg']:>8.1f} {p['degree']:>4} "
              f"{p.get('n_points', 0):>6} "
              f"{m.get('amplitude_mm', 0):>8.3f} "
              f"{m.get('amplitude_norm', 0):>10.5f} "
              f"{s.get('rmse_mm', 0):>10.5f}")

    stats = data.get("statistics", {})
    if stats:
        print(f"\nGlobal RMSE: {stats.get('rmse_global_mm', 0):.5f} mm")
        print(f"Total points: {stats.get('n_points_total', 0)}")
        print(f"Outliers removed: {stats.get('n_outliers_removed', 0)}")
