"""appa.io — чтение/запись: CSV-набор сечений, документ модели .pappa.json,
папка образца (манифест + сечение на файл)."""

from .dataset import (attach_ideal_grid, load_and_clean, load_sections,
                      ring_interp)
from .model_file import (FORMAT_NAME, FORMAT_VERSION, load_model, save_model,
                         summary, validate_model)
from .sample_store import (MANIFEST_NAME, SAMPLE_FORMAT, SAMPLE_VERSION,
                           SECTIONS_DIR, load_report, load_sample, sample_dir,
                           save_report, save_sample)

__all__ = [
    "load_sections", "load_and_clean", "attach_ideal_grid", "ring_interp",
    "save_model", "load_model", "validate_model", "summary",
    "FORMAT_NAME", "FORMAT_VERSION",
    "save_sample", "load_sample", "sample_dir", "save_report", "load_report",
    "SAMPLE_FORMAT", "SAMPLE_VERSION", "MANIFEST_NAME", "SECTIONS_DIR",
]
