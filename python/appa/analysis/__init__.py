"""
appa.analysis — метрики и «движки» исследований.

Здесь живут расчёты, которые раньше были внутри длинных скриптов: детектор
трещин (zones), раскладка звёздой (layout), фаза на сечение
(per_section_phase), планирование экспериментов по фазе/дефектам/очистке и
прототип фичера ям. Рисовать и печатать они не умеют — это appa.viz/appa.report.
"""

from .layout import (fit_layout, layout_margins, layout_rmse, search_symmetric,
                     section_crack_zones, union_zones, zone_margin_deg)
from .zones import detect_zones, indicator_curve, mask_to_zones, truth_zone_mask

__all__ = [
    "section_crack_zones", "union_zones", "zone_margin_deg", "layout_margins",
    "fit_layout", "layout_rmse", "search_symmetric",
    "detect_zones", "indicator_curve", "mask_to_zones", "truth_zone_mask",
]
