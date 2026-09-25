"""
verify_port_figure.py

Рисунок к сверке порта (числа — в studies/verify_port.py, там же код возврата
для CI). Здесь только тонкий слой: прочитать папки образца, посчитать сверку
(pappa.analysis.port_study), напечатать ту же таблицу и собрать ОДИН широкий
рисунок (pappa.viz.port_figs) — 16:9, >= 2K по ширине.

Это замена demos/cpp_plot_results.py: тот требовал CSV рядом со скриптом,
принимал на вход «набор точек» и рисовал вертикальную сетку 2x5, где числа
тонули в картинке (CONTEXT §27, шаг 5).

Запуск: <python> verify_port_figure.py [--py-dir ...] [--cpp-dir ...]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pappa.analysis.port_study import compare_loaded, load_pair, resolve_dir
from pappa.paths import resolve_plot
from pappa.report.sample_report import print_verify
from pappa.viz.port_figs import plot_port_check

CONFIG = {
    "py_dir": "synthetic_sphere",        # образец, собранный Python-ом
    "cpp_dir": "synthetic_sphere_cpp",   # папка, куда пишет порт C++
    "ideal_column": "radius_ideal_mm",
    "grid_points": 6000,
    "tol_mm": 1e-6,                      # допуск паритета (§27)
    "crops": 3,                          # сколько крупных планов ям рисовать
    "crop_half_deg": 14.0,               # полуширина крупного плана
    "dpi": 160,                          # 22 x 10 дюймов => 3520 x 1600 px
    "out_figure": "port_check.png",
}

EXIT_OK, EXIT_MISMATCH, EXIT_NO_DATA = 0, 1, 2


def main():
    ap = argparse.ArgumentParser(description="Рисунок сверки порта C++ с Python")
    ap.add_argument("--py-dir", default=None)
    ap.add_argument("--cpp-dir", default=None)
    ap.add_argument("--tol", type=float, default=None)
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
              f"запустите порт: pappa_pipeline --input <csv> --out-dir {cpp_dir}")
        return EXIT_NO_DATA

    loaded = load_pair(py_dir, cpp_dir, cfg)
    rows, summary = compare_loaded(loaded, cfg)

    # Числа печатаем теми же словами, что и verify_port.py (одна и та же таблица)
    print_verify(rows, summary, cfg["tol_mm"], Path(py_dir).name,
                 Path(cpp_dir).name)

    cfg["py_name"] = Path(py_dir).name
    cfg["cpp_name"] = Path(cpp_dir).name
    out = plot_port_check(cfg, loaded, rows, summary,
                          resolve_plot(cfg["out_figure"]))
    print(f"\nРисунок: {out}")

    return EXIT_OK if summary["n_ok"] == summary["n_total"] else EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main())
