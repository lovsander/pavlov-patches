"""
verify_port.py

Сверка порта с референсом: две папки образца (собрал Python — собрал порт) и
числовое сравнение по каждому сечению. Рисунков тут нет намеренно: сначала
числа, картинка — отдельным тонким скриптом studies/verify_port_figure.py
(CONTEXT §27). Сам расчёт живёт в pappa/analysis/port_study.py (правило слоёв).

ЧТО СРАВНИВАЕТСЯ (по каждому сечению): max|Δr| контура на общей сетке (допуск
tol_mm, по умолчанию 1e-6 мм), совпадение степеней патчей (при одних данных и
одной политике они обязаны совпасть), число терминов фичера ям и RMSE каждого
порта к эталону, если в исходном CSV есть эталонная колонка.

КОДЫ ВОЗВРАТА (чтобы годилось для CI):
  0 — всё в допуске; 1 — расхождение больше допуска; 2 — нет/нечитаемы данные
  одной из сторон (например, порт ещё не запускали).

ЗАПУСК:
  python studies/verify_port.py                          # пути из CONFIG
  python studies/verify_port.py --py-dir samples/x --cpp-dir samples/x_cpp
Пути можно задавать относительно корня репозитория, относительно samples/ или
абсолютные. Отчёт пишется в report/verify.json папки порта (это и есть предмет
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

from pappa.analysis.port_study import compare, resolve_dir
from pappa.io.sample_store import save_report
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

    py_dir = resolve_dir(args.py_dir or cfg["py_dir"])
    cpp_dir = resolve_dir(args.cpp_dir or cfg["cpp_dir"])

    if not py_dir.is_dir():
        print(f"нет папки референса: {py_dir}\n"
              f"соберите её: python studies/build_sample.py")
        return EXIT_NO_DATA
    if not cpp_dir.is_dir():
        print(f"нет папки порта: {cpp_dir}\n"
              f"запустите порт, указав её как выходную: --out-dir {cpp_dir}")
        return EXIT_NO_DATA

    rows, summary = compare(py_dir, cpp_dir, cfg)

    report_dir = resolve_dir(args.report_dir) if args.report_dir else cpp_dir
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
