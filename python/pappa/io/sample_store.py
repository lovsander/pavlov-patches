"""
pappa/io/sample_store.py — папка образца: манифест + один документ на сечение.

Раскладка (CONTEXT §27):

    samples/<имя_образца>/
        sample.json                  манифест: единицы, параметры метода, список сечений
        sections/<NN>.pappa.json     документ описания ОДНОГО сечения (pappa v2.0)
        report/verify.json           числовой отчёт сверки Python <-> C++

Зачем: результат пайплайна — не «набор точек» в одном CSV, а описание сечений:
по документу на сечение, собранных в папку ОБРАЗЦА. Так результат читают и
Python, и порты (C++), и скрипт проверки порта (studies/verify_port.py), причём
имя файла не зависит от языка, а порядок сечений задаёт манифест.

Имена файлов — по порядку загрузки (`00.pappa.json`, `01.pappa.json`, ...),
а section_id и высота лежат внутри документа (meta) и в манифесте.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..paths import SAMPLES_DIR
from .model_file import load_model, save_model

SAMPLE_FORMAT = "pappa-sample"
SAMPLE_VERSION = "1.0"
MANIFEST_NAME = "sample.json"
SECTIONS_DIR = "sections"
REPORT_DIR = "report"
VERIFY_REPORT_NAME = "verify.json"


def sample_dir(name, root=None):
    """Каталог образца: samples/<name> (root по умолчанию — SAMPLES_DIR)."""
    root = Path(root) if root else SAMPLES_DIR
    return root / str(name)


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path, base):
    """Путь относительно каталога образца (в манифесте храним относительные)."""
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except ValueError:
        return str(path)

def save_sample(name, sections, meta=None, config=None, input_csv=None,
                root=None, created=None):
    """
    Записать папку образца. Возвращает каталог образца.

    name      — имя образца (оно же имя папки);
    sections  — список словарей, по одному на сечение:
                  {"section_id": int,
                   "height_mm": float,
                   "model": fitted PatchApproximator/PitPatchApproximator,
                   "n_points": int,          # точек в сечении после очистки (опц.)
                   "n_outliers": int,        # отброшено очисткой (опц.)
                   "source": str}            # чем обучено (опц.)
    meta      — свободный словарь в манифест (description, operator, ...);
    config    — параметры метода (раскладка, фаза, фичер, чистильщик, детектор) —
                в манифест для воспроизводимости;
    input_csv — CSV, из которого взят образец: пишем путь и sha256 (след того,
                на каких данных обучено; сам файл не копируем).
    """
    root_dir = sample_dir(name, root)
    (root_dir / SECTIONS_DIR).mkdir(parents=True, exist_ok=True)

    manifest = {
        "format": SAMPLE_FORMAT,
        "version": SAMPLE_VERSION,
        "name": str(name),
        "created": created or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "units": {"angle": "degree", "length": "mm"},
        "meta": dict(meta or {}),
        "config": dict(config or {}),
        "sections": [],
    }

    if input_csv:
        csv_path = Path(input_csv)
        manifest["input"] = {
            "csv": _rel(csv_path, root_dir),
            "sha256": _sha256(csv_path) if csv_path.exists() else None,
        }

    for index, s in enumerate(sorted(sections, key=lambda x: int(x["section_id"]))):
        sid = int(s["section_id"])
        fname = f"{index:02d}.pappa.json"
        save_model(s["model"], root_dir / SECTIONS_DIR / fname, meta={
            "section_id": sid,
            "height_mm": float(s.get("height_mm", 0.0)),
            "source": str(s.get("source", "") or ""),
            "description": str(s.get("description", "") or ""),
        })
        manifest["sections"].append({
            "index": index,
            "section_id": sid,
            "height_mm": float(s.get("height_mm", 0.0)),
            "file": f"{SECTIONS_DIR}/{fname}",
            "n_points": int(s.get("n_points", 0)),
            "n_outliers": int(s.get("n_outliers", 0)),
        })

    with (root_dir / MANIFEST_NAME).open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return root_dir
def load_sample(path):
    """
    Прочитать папку образца (путь к папке или к манифесту). Возвращает словарь:
        {"root", "name", "manifest", "meta", "config", "input",
         "sections": {section_id: {"index", "height_mm", "file", "model",
                                   "n_points", "n_outliers"}},
         "section_ids": [...]}
    Документы сечений читаются тем же кодом, что и любой .pappa.json.
    """
    root_dir = Path(path)
    if root_dir.is_dir():
        root_dir = root_dir / MANIFEST_NAME
    if not root_dir.exists():
        raise FileNotFoundError(f"Нет манифеста образца: {root_dir}")

    with root_dir.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("format") != SAMPLE_FORMAT:
        raise ValueError(f"Не манифест образца: format={manifest.get('format')!r}")

    sample_root = root_dir.parent
    sections = {}
    for entry in manifest.get("sections", []):
        file_path = sample_root / entry["file"]
        sections[int(entry["section_id"])] = {
            "index": int(entry.get("index", 0)),
            "height_mm": float(entry.get("height_mm", 0.0)),
            "file": file_path,
            "model": load_model(file_path),
            "n_points": int(entry.get("n_points", 0)),
            "n_outliers": int(entry.get("n_outliers", 0)),
        }

    return {
        "root": sample_root,
        "name": manifest.get("name", sample_root.name),
        "manifest": manifest,
        "meta": manifest.get("meta", {}),
        "config": manifest.get("config", {}),
        "input": manifest.get("input", {}),
        "sections": sections,
        "section_ids": sorted(sections),
    }


def save_report(sample_root, payload, name=VERIFY_REPORT_NAME):
    """Записать числовой отчёт сверки в report/ этого образца."""
    report_dir = Path(sample_root) / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    file_path = report_dir / name
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return file_path


def load_report(sample_root, name=VERIFY_REPORT_NAME):
    """Прочитать отчёт сверки (None, если его нет)."""
    file_path = Path(sample_root) / REPORT_DIR / name
    if not file_path.exists():
        return None
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)

