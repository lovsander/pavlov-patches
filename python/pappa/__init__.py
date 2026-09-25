"""
pappa — Piecewise Adaptive Poly-Patch Approximation (PAPPA), aka «Pavlov patches».

Карта пакета (подробности — в CONTEXT.md §21):

  pappa.paths      корень python/ и resolve_path() — общий для всех скриптов
  pappa.core       ядро модели
    patch_approximator  PatchApproximator (полиномы на патчах, правило «локтя»)
    outlier_cleaner     OutlierCleaner + AutoOutlierCleaner
    signal_tools        MAD/robust sigma/IQR, круговые фильтры, GMM
    crack_detector      CrackDetector (разница грубой и точной модели)
    pit_feature         фичер ям: оконный гаусс + ЕДИНАЯ сборка модели
                        (MODEL_DEFAULTS, PIT_DEFAULTS, build_model)
    geometry            узлы/центры патчей, круговые операции
  pappa.io         ввод/вывод: model_file (документ .pappa.json: save/load/validate),
                  sample_store (папка образца: манифест + сечение на файл),
                  dataset (CSV, очистка)
  pappa.analysis   метрики и исследования: zones (детектор трещин), layout (раскладка
                  звездой), per_section_phase, phase_study, defect_study,
                  cleaner_study, pit_study, model_scan
  pappa.viz        рисунки: style, star, layout_figs, phase_figs, pit_figs,
                  defect_figs, cleaner_figs
  pappa.report     текстовые отчёты в консоль (layout/phase/pit/defect/cleaner)

Точки входа (тонкие скрипты, запускаются напрямую):
  studies/  — исследования (compare_*, explore_*)
  demos/    — демонстрации
  generator/— генератор синтетических данных
  research/ — архив исследований и отклонённых гипотез (red flags метода)
"""

from .core.crack_detector import CrackDetector
from .core.outlier_cleaner import AutoOutlierCleaner, OutlierCleaner, build_cleaner
from .core.patch_approximator import COORD_MODE, PatchApproximator
from .core.pit_feature import (DETECTOR_DEFAULTS, MODEL_DEFAULTS, PIT_DEFAULTS,
                               build_model, validate_pit_cfg)
from .io.sample_store import load_sample, sample_dir, save_sample
from .paths import (PY_ROOT, REPO_ROOT, SAMPLES_DIR, resolve_path,
                    resolve_plot)

__all__ = [
    "PatchApproximator", "OutlierCleaner", "AutoOutlierCleaner", "build_cleaner",
    "CrackDetector", "PY_ROOT", "REPO_ROOT", "SAMPLES_DIR", "resolve_path",
    "resolve_plot", "COORD_MODE", "build_model", "MODEL_DEFAULTS",
    "PIT_DEFAULTS", "DETECTOR_DEFAULTS", "validate_pit_cfg",
    "save_sample", "load_sample", "sample_dir",
]

__version__ = "0.3.0"
