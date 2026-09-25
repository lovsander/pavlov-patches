# вырезано из studies/verify_port.py (правило слоёв §21: расчёт — в analysis)
"""
pappa.analysis.port_study — числовая сверка порта с референсом.

Зачем отдельный модуль: числа сверки нужны и скрипту проверки
(studies/verify_port.py, код возврата для CI), и рисунку (pappa/viz/port_figs.py).
По правилу слоёв §21 считать должен analysis, печатать — report, рисовать — viz,
а скрипт оставаться тонким (CONFIG + main()).

Что сравнивается по каждому сечению:
  * контур: max|Δr| между документами Python и порта по общей сетке углов
    (допуск tol_mm, по умолчанию 1e-6 мм — CONTEXT §27);
  * степени патчей: при одних данных и одной политике они ОБЯЗАНЫ совпасть,
    поэтому расхождение степеней — ошибка даже при малой |Δ|;
  * число терминов фичера ям в базисе (подсказка, откуда расхождение);
  * если в исходном CSV есть эталонная колонка — RMSE каждого порта к эталону.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ..io.dataset import ring_interp
from ..io.sample_store import load_sample
from ..paths import REPO_ROOT, SAMPLES_DIR, resolve_path


def resolve_dir(spec):
    """
    Путь к папке образца. Принимаем: абсолютный путь, путь от текущего каталога,
    от корня python/ (как resolve_path) или от корня репозитория — чтобы можно
    было писать и `samples/x`, и `python/../samples/x`, и `C:\\...\\samples\\x`.
    """
    if not spec:
        return None
    p = Path(spec)
    for candidate in (p, resolve_path(spec), REPO_ROOT / spec, SAMPLES_DIR / spec):
        if candidate.is_dir():
            return candidate
    return p            # не существует — вернём как есть, вызывающий сообщит


def pits_count(model):
    """Число терминов фичера ям в базисе модели."""
    return int(sum(len(p.get("pit_offsets", [])) for p in model.patches_))


def ideals_for(csv_path, ideal_column, grid):
    """Эталон по сечениям на общей сетке (если CSV и колонка есть)."""
    if not csv_path or not Path(csv_path).exists():
        return {}
    try:
        data = pd.read_csv(csv_path)
    except Exception:
        return {}
    if ideal_column not in data.columns:
        return {}
    out = {}
    for sid in sorted(data["section_id"].unique()):
        sec = data[data["section_id"] == sid].sort_values("angle_deg")
        out[int(sid)] = ring_interp(sec["angle_deg"].to_numpy(dtype=float),
                                    sec[ideal_column].to_numpy(dtype=float), grid)
    return out


def load_pair(py_dir, cpp_dir, cfg):
    """
    Прочитать две папки образца и эталон. Возвращает словарь:
        {"py", "cpp", "grid", "ideals", "tol_mm", "csv_path"}
    Дальше и числа (compare_loaded), и рисунок (viz) работают с ним.
    """
    grid = np.linspace(0.0, 360.0, int(cfg["grid_points"]), endpoint=False)
    py = load_sample(py_dir)
    cpp = load_sample(cpp_dir)

    csv_path = py["input"].get("csv")
    if csv_path and not Path(csv_path).is_absolute():
        candidate = resolve_path(csv_path)
        csv_path = candidate if candidate.exists() else csv_path
    ideals = ideals_for(csv_path, cfg.get("ideal_column", "radius_ideal_mm"), grid)

    return {"py": py, "cpp": cpp, "grid": grid, "ideals": ideals,
            "tol_mm": float(cfg["tol_mm"]), "csv_path": csv_path}


def compare_loaded(loaded, cfg):
    """Сверка уже прочитанных папок. Возвращает (rows, summary)."""
    py, cpp, grid = loaded["py"], loaded["cpp"], loaded["grid"]
    ideals, tol_mm = loaded["ideals"], loaded["tol_mm"]

    ids_py, ids_cpp = set(py["section_ids"]), set(cpp["section_ids"])
    rows = []
    for sid in sorted(ids_py | ids_cpp):
        h = (py["sections"].get(sid) or cpp["sections"].get(sid))["height_mm"]
        row = {"section_id": sid, "height_mm": h, "ok": False,
               "degrees_equal": False, "pits_py": 0, "pits_cpp": 0,
               "max_delta": float("nan"), "rmse_py": None, "rmse_cpp": None,
               "note": ""}
        if sid not in ids_py or sid not in ids_cpp:
            row["note"] = "нет в " + ("Python" if sid not in ids_py else "C++")
            rows.append(row)
            continue

        m_py = py["sections"][sid]["model"]
        m_cpp = cpp["sections"][sid]["model"]
        y_py, y_cpp = m_py.eval(grid), m_cpp.eval(grid)

        row["degrees_equal"] = ([int(d) for d in m_py.degrees_]
                                == [int(d) for d in m_cpp.degrees_])
        row["pits_py"], row["pits_cpp"] = pits_count(m_py), pits_count(m_cpp)
        row["max_delta"] = float(np.max(np.abs(y_py - y_cpp)))
        if sid in ideals:
            row["rmse_py"] = float(np.sqrt(np.mean((y_py - ideals[sid]) ** 2)))
            row["rmse_cpp"] = float(np.sqrt(np.mean((y_cpp - ideals[sid]) ** 2)))
        row["ok"] = bool(row["degrees_equal"] and row["max_delta"] <= tol_mm)
        rows.append(row)

    finite = [r for r in rows if r["max_delta"] == r["max_delta"]]
    worst = max(finite, key=lambda r: r["max_delta"]) if finite else rows[0]
    n_ok = sum(1 for r in rows if r["ok"])
    summary = {
        "max_delta": float(worst["max_delta"]) if finite else float("nan"),
        "worst_section": worst["section_id"],
        "n_ok": n_ok, "n_total": len(rows),
        "verdict": ("порт воспроизводит референс в пределах допуска"
                    if n_ok == len(rows) and rows else
                    "есть расхождения: см. таблицу отчёта"),
    }
    return rows, summary


def compare(py_dir, cpp_dir, cfg):
    """Сверить две папки образца: (rows, summary)."""
    return compare_loaded(load_pair(py_dir, cpp_dir, cfg), cfg)


def curves(loaded, sid):
    """
    Кривые одного сечения для рисунка:
        {"grid", "y_py", "y_cpp", "ideal" (или None), "res_py", "res_cpp",
         "max_delta", "deg_py", "deg_cpp", "pits_py", "pits_cpp", "height_mm"}.
    Остатки считаются от эталона, если он есть; иначе от модели Python.
    """
    grid = loaded["grid"]
    m_py = loaded["py"]["sections"][sid]["model"]
    m_cpp = loaded["cpp"]["sections"][sid]["model"]
    y_py, y_cpp = m_py.eval(grid), m_cpp.eval(grid)
    ideal = loaded["ideals"].get(sid)
    base = ideal if ideal is not None else y_py
    return {
        "grid": grid, "y_py": y_py, "y_cpp": y_cpp, "ideal": ideal,
        "res_py": y_py - base, "res_cpp": y_cpp - base,
        "max_delta": float(np.max(np.abs(y_py - y_cpp))),
        "deg_py": [int(d) for d in m_py.degrees_],
        "deg_cpp": [int(d) for d in m_cpp.degrees_],
        "pits_py": pits_count(m_py), "pits_cpp": pits_count(m_cpp),
        "height_mm": float(loaded["py"]["sections"][sid]["height_mm"]),
    }


def pit_angles(model):
    """Углы центров ям модели (глобальные, °) — для крупных планов на рисунке."""
    out = []
    for p in model.patches_:
        center = float(p["center"])
        for dx in p.get("pit_offsets", []):
            a = (center + float(dx)) % 360.0
            if all(abs((a - b + 180.0) % 360.0 - 180.0) > 1e-6 for b in out):
                out.append(a)
    return sorted(out)
