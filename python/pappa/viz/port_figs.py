"""
pappa.viz.port_figs — ШИРОКИЙ рисунок проверки порта (замена cpp_plot_results).

Зачем: старая сверка C++ и Python рисовала вертикальную сетку 2x5 (dpi 300), в
которой числа тонули в картинке, и требовала CSV рядом со скриптом. Теперь
сначала идут числа (studies/verify_port.py), а рисунок — дополнение к ним:
одна широкая полоса (16:9, >= 2K по ширине) с тем же смыслом, что и таблица.

Раскладка (2 строки x 4 колонки):
  * профиль показательного сечения: эталон, модель Python, модель порта;
  * остаток модели к эталону (где порт и Python совпадают, кривые ложатся друг
    на друга — видно качество метода, а не паритет);
  * max|Δr| по всем сечениям (лог. шкала) с линией допуска — паритет;
  * текстовый блок с числами: степени, ямы, RMSE, допуск, вердикт;
  * нижний ряд: крупные планы участков ям (эталон + модели + паритетный Δ).
"""

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..analysis import port_study


def pick_sections(rows, crops=3):
    """
    Показательные сечения: сначала худшее по |Δ| (паритет), затем сечения с
    наибольшим числом ям (там метод интереснее всего). Без повторов.
    """
    picked = []
    finite = [r for r in rows if r["max_delta"] == r["max_delta"]]
    if finite:
        worst = max(finite, key=lambda r: r["max_delta"])
        picked.append(worst["section_id"])
    for r in sorted(rows, key=lambda r: -r["pits_py"]):
        if len(picked) >= crops:
            break
        if r["section_id"] not in picked:
            picked.append(r["section_id"])
    return picked[:crops]


def plot_port_check(cfg, loaded, rows, summary, out_path):
    """Собрать широкий рисунок сверки порта. Возвращает путь к файлу."""
    dpi = int(cfg.get("dpi", 160))
    half = float(cfg.get("crop_half_deg", 14.0))
    tol_mm = float(cfg.get("tol_mm", 1e-6))
    grid = loaded["grid"]
    worst_sid = summary["worst_section"]
    sections = pick_sections(rows, cfg.get("crops", 3))
    row_by_sid = {r["section_id"]: r for r in rows}

    fig = plt.figure(figsize=(22, 10))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.1, 1.0], hspace=0.32, wspace=0.24)

    # --- 1. профиль и модели показательного сечения ---
    ax = fig.add_subplot(gs[0, :2])
    cur = port_study.curves(loaded, worst_sid)
    if cur["ideal"] is not None:
        ax.plot(grid, cur["ideal"], "k-", lw=1.2, alpha=0.75, label="эталон")
    ax.plot(grid, cur["y_cpp"], "--", color="tab:red", lw=2.4, label="модель порта C++")
    ax.plot(grid, cur["y_py"], "-", color="tab:blue", lw=1.1, label="модель Python")
    for a in port_study.pit_angles(loaded["py"]["sections"][worst_sid]["model"]):
        ax.axvline(a, color="0.55", ls=":", lw=0.9)
    ax.set_xlim(0, 360)
    ax.set_xlabel("Угол, °")
    ax.set_ylabel("Радиус, мм")
    ax.set_title(f"Сечение {worst_sid} (h={cur['height_mm']:.0f} мм): эталон и обе "
                 f"модели; пунктир — центры ям\nстепени Python {cur['deg_py']} / "
                 f"порт {cur['deg_cpp']}, ям в базисе {cur['pits_py']}/{cur['pits_cpp']}")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")

    # --- 2. остаток модели к эталону ---
    ax = fig.add_subplot(gs[0, 2])
    ax.plot(grid, cur["res_cpp"], "-", color="tab:red", lw=2.0, label="порт C++")
    ax.plot(grid, cur["res_py"], "-", color="tab:blue", lw=0.9, label="Python")
    ax.axhline(0.0, color="k", lw=0.8)
    ax.set_xlim(0, 360)
    ax.set_xlabel("Угол, °")
    ax.set_ylabel("модель − эталон, мм")
    ax.set_title(f"Остаток к эталону, сечение {worst_sid}\n"
                 f"пик {np.max(np.abs(cur['res_py'])):.4f} мм (кривые совпадают)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # --- 3. паритет по всем сечениям: max|Δr| и допуск ---
    ax = fig.add_subplot(gs[0, 3])
    deltas = [max(r["max_delta"], 1e-18) for r in rows]
    ax.bar([str(r["section_id"]) for r in rows], deltas, color="tab:green", alpha=0.8)
    ax.axhline(tol_mm, color="tab:red", ls="--", lw=1.2, label=f"допуск {tol_mm:g} мм")
    ax.set_yscale("log")
    ax.set_ylim(min(deltas) / 10.0, max(max(deltas) * 10.0, tol_mm))
    ax.set_xlabel("Сечение")
    ax.set_ylabel("max|Δr| Python↔порт, мм")
    ax.set_title("Паритет по сечениям (log)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=8)

    # --- 4. текстовый блок с числами ---
    ax = fig.add_subplot(gs[1, 3])
    ax.axis("off")
    n_pits = [r["pits_py"] for r in rows]
    rmse = [r["rmse_py"] for r in rows if r["rmse_py"] is not None]
    lines = [
        "ЧИСЛА (studies/verify_port.py)",
        f"папка Python: {cfg.get('py_name', '?')}",
        f"папка порта:  {cfg.get('cpp_name', '?')}",
        f"сетка: {len(grid)} точек, допуск {tol_mm:g} мм",
        "",
        f"сечений в допуске: {summary['n_ok']}/{summary['n_total']}",
        f"max|Δr|: {summary['max_delta']:.3e} мм "
        f"(худшее сечение {summary['worst_section']})",
        f"степени совпали: {sum(1 for r in rows if r['degrees_equal'])}/{len(rows)}",
        f"ямы (термины фичера): {n_pits}",
    ]
    if rmse:
        lines += ["", f"RMSE к эталону (Python): {min(rmse):.6f}…{max(rmse):.6f} мм"]
    lines += ["", f"ВЫВОД: {summary['verdict']}"]
    ax.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=10,
            family="monospace", transform=ax.transAxes)

    # --- 5. крупные планы ям ---
    for k in range(min(3, len(sections))):
        sid = sections[k]
        c = port_study.curves(loaded, sid)
        r = row_by_sid[sid]
        ax = fig.add_subplot(gs[1, k])
        pits = port_study.pit_angles(loaded["py"]["sections"][sid]["model"])
        center = pits[0] if pits else 0.0
        lo, hi = center - half, center + half
        m = (grid >= lo) & (grid <= hi)
        ax.plot(grid[m], c["res_cpp"][m], "-", color="tab:red", lw=2.0,
                label="порт C++ − эталон")
        ax.plot(grid[m], c["res_py"][m], "-", color="tab:blue", lw=0.9,
                label="Python − эталон")
        ax.plot(grid[m], np.abs(c["y_py"][m] - c["y_cpp"][m]), ":", color="0.15",
                lw=1.4, label="|Python − порт|")
        ax.axhline(0.0, color="k", lw=0.8)
        ax.axvline(center, color="0.55", ls="--", lw=1.0)
        ax.set_xlim(lo, hi)
        ax.set_xlabel("Угол, °")
        ax.set_ylabel("мм")
        ax.set_title(f"Сечение {sid} (h={c['height_mm']:.0f} мм), яма {center:.1f}°, "
                     f"max|Δ| {r['max_delta']:.2e} мм")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=7)

    fig.suptitle("PAPPA: сверка порта C++ с референсом Python — профиль, остаток "
                 "к эталону и паритет", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.965))

    out_path = Path(out_path)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path

