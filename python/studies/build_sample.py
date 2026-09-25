"""
build_sample.py

Собрать ОБРАЗЕЦ из CSV средствами Python: samples/<имя>/ с манифестом и
документом описания на каждое сечение (.pappa.json).

ЧТО ДЕЛАЕТ (по шагам, как в пайплайне):
  1. читает CSV и чистит выбросы авто-очистителем (iqr) на каждом сечении;
  2. находит центры ям детектором трещин (band, DETECTOR_DEFAULTS) — если
     фичер ям включён;
  3. обучает модель сечения через ЕДИНУЮ точку сборки build_model
     (MODEL_DEFAULTS + PIT_DEFAULTS: N=7, phase 24.75°, оконный гаусс 3.2σ);
  4. пишет документы сечений и манифест через pappa.io.sample_store.

Зачем: это питоновская половина контракта «папка образца» (CONTEXT §27).
Порт C++ обязан записать такую же папку; после этого
studies/verify_port.py сравнивает две папки числами.

Запуск: <python> build_sample.py [--name ИМЯ] [--no-pits] [--root ПАПКА]
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

from pappa.analysis.layout import section_crack_zones
from pappa.core.pit_feature import (DETECTOR_DEFAULTS, MODEL_DEFAULTS,
                                   PIT_DEFAULTS, build_model)
from pappa.io.dataset import load_sections, ring_interp
from pappa.io.model_file import validate_model
from pappa.io.sample_store import load_sample, sample_dir, save_sample
from pappa.paths import resolve_path
from pappa.report.sample_report import print_built_sample

STYLE = {"bar": "=" * 96}

CONFIG = {
    "csv": "synthetic_data.csv",
    "ideal_column": "radius_ideal_mm",
    "cleaner": {"mode": "auto", "auto": {"method": "iqr"}},
    "name": "synthetic_sphere",
    "description": "Синтетический образец: 10 сечений по высоте, R=15 мм, три трещины",
    "pits": True,                 # фичер ям включён (решение §25)
    "grid_points": 6000,          # сетка честной RMSE (метрика отчёта)
    "detector": dict(DETECTOR_DEFAULTS),
    **MODEL_DEFAULTS,
    **PIT_DEFAULTS,
}


def build(cfg, name=None, pits_on=None, root=None):
    """Собрать образец. Возвращает (каталог, строки отчёта, манифест, валидации)."""
    name = name or cfg["name"]
    pits_on = cfg["pits"] if pits_on is None else bool(pits_on)
    grid = np.linspace(0.0, 360.0, cfg["grid_points"], endpoint=False)

    csv_path = resolve_path(cfg["csv"])
    sections = load_sections(csv_path, cfg["ideal_column"], cfg["cleaner"])
    sids = sorted(sections)

    pits_by_section = {}
    if pits_on:
        zones = section_crack_zones({**cfg, "sections": sids}, sections, sids)
        pits_by_section = {sid: [0.5 * (a + b) for a, b in zones[sid]]
                           for sid in sids}

    rows, payload = [], []
    for sid in sids:
        sec = sections[sid]
        pits = pits_by_section.get(sid, [])
        model = build_model(cfg, pits=pits or None)
        model.fit(sec["angles_clean"], sec["radii_clean"])

        ideal = ring_interp(sec["angles"], sec["ideal"], grid)
        rmse = float(np.sqrt(np.mean((model.eval(grid) - ideal) ** 2)))
        n_pits = int(sum(len(p.get("pit_offsets", [])) for p in model.patches_))

        rows.append({
            "index": len(rows), "section_id": sid,
            "height_mm": float(sec["height_mm"]),
            "n_points": int(len(sec["angles_clean"])),
            "n_outliers": int(np.sum(sec["mask"])),
            "degrees": [int(d) for d in model.degrees_],
            "n_pits": n_pits, "rmse_ideal": rmse,
        })
        payload.append({
            "section_id": sid, "height_mm": float(sec["height_mm"]),
            "model": model, "n_points": int(len(sec["angles_clean"])),
            "n_outliers": int(np.sum(sec["mask"])),
            "source": csv_path.name,
            "description": f"Сечение {sid}, h={float(sec['height_mm']):.0f} мм, "
                           f"ям в базисе: {n_pits}",
        })

    config = {"n_patches": cfg["n_patches"], "phase_deg": cfg["phase_deg"],
              "deg_min": cfg["deg_min"], "deg_max": cfg["deg_max"],
              "overlap_train": cfg["overlap_train"], "overlap_use": cfg["overlap_use"],
              "deg_elbow_tol": cfg["deg_elbow_tol"],
              "cleaner": cfg["cleaner"], "pits": bool(pits_on),
              "sigma_deg": cfg["sigma_deg"], "pit_core_sigma": cfg["pit_core_sigma"],
              "pit_window_sigma": cfg["pit_window_sigma"],
              "pit_min_amp": cfg["pit_min_amp"], "tapering": cfg["tapering"],
              "detector": cfg["detector"] if pits_on else None}

    root_dir = save_sample(name, payload,
                           meta={"description": cfg["description"]},
                           config=config, input_csv=csv_path, root=root)

    docs = []
    for entry in sorted(rows, key=lambda r: r["index"]):
        doc = root_dir / "sections" / f"{entry['index']:02d}.pappa.json"
        ok, _ = validate_model(doc)
        docs.append((doc, ok))

    return root_dir, rows, load_sample(root_dir)["manifest"], docs


def main():
    ap = argparse.ArgumentParser(description="Собрать образец (папка samples/<имя>)")
    ap.add_argument("--name", default=None, help="имя образца (по умолчанию из CONFIG)")
    ap.add_argument("--no-pits", action="store_true",
                    help="без фичера ям (чистая полиномиальная модель)")
    ap.add_argument("--root", default=None, help="корень папок образцов")
    args = ap.parse_args()

    root_dir, rows, manifest, docs = build(CONFIG, name=args.name,
                                           pits_on=not args.no_pits, root=args.root)
    print_built_sample(root_dir, rows, manifest, docs)
    print(f"Путь для порта (--out-dir): {root_dir}")
    print(f"Сверить порт: python studies/verify_port.py --cpp-dir {root_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
