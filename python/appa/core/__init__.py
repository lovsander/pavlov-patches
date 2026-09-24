"""appa.core — ядро модели (патчи, степени, очистка, детектор трещин)."""

from .crack_detector import CrackDetector
from .geometry import node_angles, patch_centers
from .outlier_cleaner import AutoOutlierCleaner, OutlierCleaner, build_cleaner
from .patch_approximator import PatchApproximator
from .signal_tools import (angular_step, iqr, mad, median_filter_wrap,
                           robust_sigma, window_points)

__all__ = [
    "PatchApproximator", "OutlierCleaner", "AutoOutlierCleaner", "build_cleaner",
    "CrackDetector", "node_angles", "patch_centers", "mad", "robust_sigma",
    "iqr", "angular_step", "window_points", "median_filter_wrap",
]
