"""
verify_port.py

Сверка порта с референсом: две папки образца (собрал Python — собрал C++) и
числовое сравнение по каждому сечению. Рисунков тут нет намеренно: сначала
числа, картинка — отдельным тонким скриптом (CONTEXT §27).

ЧТО СРАВНИВАЕТСЯ (по каждому сечению):
  * контур: max|Δr| между документами Python и C++ по общей сетке углов
    (допуск tol_mm, по умолчанию 1e-6 мм — как в §27);
  * степени патчей: при одинаковых данных и одной политике они ОБЯЗАНЫ совпасть,
    поэтому расхождение степеней — ошибка даже при малой |Δ|;
  * число терминов фичера ям в базисе (подсказка, откуда расхождение);
  * если в CSV есть эталонная колонка — RMSE каждого порта к эталону.

КОДЫ ВОЗВРАТА (чтобы годилось для CI):
  0 — всё в допуске; 1 — расхождение больше допуска; 2 — нет/нечитаемы данные
  одной из сторон (например, порт ещё не запускали).

ЗАПУСК:
  python studies/verify_port.py                          # пути из CONFIG
  python studies/verify_port.py --py-dir samples/x --cpp-dir samples/x_cpp
Пути можно задавать относительно корня репозитория, относительно samples/ или
абсолютные. Отчёт пишется в report/verify.json папки C++ (это и есть предмет
проверки), переопределяется ключом --report-dir.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import pandas as pd

from pappa.io.dataset import ring_interp
from pappa.io.sample_store import load_sample, save_report
from pappa.paths import REPO_ROOT, SAMPLES_DIR, resolve_path
from pappa.report.sample_report import print_verify

CONFIG = {
    # образец, собранный Python-ом, и папка, куда пишет порт C++
    "py_dir": "synthetic_sphere",
    "cpp_dir": "synthetic_sphere_cpp",
    "ideal_column": "radius_ideal_mm",
    "grid_points": 6000,
    "tol_mm": 1e-6,          # допуск на расхождение контура (§27)
}

EXIT_OK, EXIT_MISMATCH, EXIT_NO_DATA = 0, 1, 2


def _resolve_dir(spec):
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


def _pits_count(model):
    return int(sum(len(p.get("pit_offsets", [])) for p in model.patches_))

def _ideals(csv_path, ideal_column, grid):
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


def compare(py_dir, cpp_dir, cfg):
    """Сверить две папки образца. Возвращает (rows, summary)."""
    py = load_sample(py_dir)
    cpp = load_sample(cpp_dir)

    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)
    csv_path = py["input"].get("csv")
    if csv_path and not Path(csv_path).is_absolute():
        csv_path = resolve_path(csv_path)
    ideals = _ideals(csv_path, cfg["ideal_column"], grid)

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
        row["pits_py"], row["pits_cpp"] = _pits_count(m_py), _pits_count(m_cpp)
        row["max_delta"] = float(np.max(np.abs(y_py - y_cpp)))
        if sid in ideals:
            row["rmse_py"] = float(np.sqrt(np.mean((y_py - ideals[sid]) ** 2)))
            row["rmse_cpp"] = float(np.sqrt(np.mean((y_cpp - ideals[sid]) ** 2)))
        row["ok"] = bool(row["degrees_equal"] and row["max_delta"] <= cfg["tol_mm"])
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
                    "есть расхождения: см. таблицу и report/verify.json"),
    }
    return rows, summary



def main():
    ap = argparse.ArgumentParser(description="Сверить порт C++ с референсом Python")
    ap.add_argument("--py-dir", default=None, help="папка образца, собранного Python")
    ap.add_argument("--cpp-dir", default=None, help="папка образца, собранного портом")
    ap.add_argument("--report-dir", default=None, help="куда писать report/verify.json")
    ap.add_argument("--tol", type=float, default=None, help="допуск |Δ| контура, мм")
    args = ap.parse_args()

    cfg = dict(CONFIG)
    if args.tol is not None:
        cfg["tol_mm"] = float(args.tol)

    py_dir = _resolve_dir(args.py_dir or cfg["py_dir"])
    cpp_dir = _resolve_dir(args.cpp_dir or cfg["cpp_dir"])

    if not py_dir.is_dir():
        print(f"нет папки референса: {py_dir}\n"
              f"соберите её: python studies/build_sample.py")
        return EXIT_NO_DATA
    if not cpp_dir.is_dir():
        print(f"нет папки порта: {cpp_dir}\n"
              f"запустите порт, указав её как выходную: --out-dir {cpp_dir}")
        return EXIT_NO_DATA

    rows, summary = compare(py_dir, cpp_dir, cfg)

    report_dir = _resolve_dir(args.report_dir) if args.report_dir else cpp_dir
    report_path = save_report(str(report_dir), {
        "check": "verify_port",
        "tol_mm": cfg["tol_mm"],
        "grid_points": cfg["grid_points"],
        "py_dir": str(py_dir), "cpp_dir": str(cpp_dir),
        "summary": summary, "sections": rows,
    })

    print_verify(rows, summary, cfg["tol_mm"], Path(py_dir).name,
                 Path(cpp_dir).name, report_path)

    return EXIT_OK if summary["n_ok"] == summary["n_total"] else EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main())
