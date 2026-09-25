# вырезано из _src_star_layout.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.outlier_cleaner import build_cleaner
from ..core.patch_approximator import PatchApproximator
from ..analysis.zones import crack_depths_mm, detect_zones, indicator_curve, load_crack_table, mask_to_zones, truth_zone_mask
from ..core.geometry import node_angles, patch_centers

STAR_INNER_R = 0.72          # радиус «впадин» (узлов) в условной шкале звезды


STAR_TOP_R = 1.10            # внешний радиус картинки (запретные зоны чуть выше)


def draw_zone_wedges(ax, zones, bottom, height, color="tab:red", alpha=0.18):
    """Закрасить запретные зоны секторами (в полярных осях)."""
    for z in zones:
        width = z[1] - z[0]
        center = 0.5 * (z[0] + z[1])
        ax.bar(np.deg2rad(center), height, width=np.deg2rad(width),
               bottom=bottom, color=color, alpha=alpha, lw=0.0, align="center")


def draw_star(ax, n_patches, phase_deg, arm_colors=None, alpha_fill=0.10):
    """
    Звезда: лучи — патчи (вершина на эталонной окружности r=1),
    впадины — узлы (границы патчей) на r=STAR_INNER_R.
    """
    centers = patch_centers(n_patches, phase_deg)
    nodes = node_angles(n_patches, phase_deg)
    theta, radius = [], []
    for i in range(n_patches):
        theta.extend([np.deg2rad(nodes[i]), np.deg2rad(centers[i])])
        radius.extend([STAR_INNER_R, 1.0])
    theta, radius = np.array(theta), np.array(radius)
    ax.plot(np.append(theta, theta[0]), np.append(radius, radius[0]),
            "-", color="0.35", lw=1.1, zorder=3)
    ax.fill(theta, radius, color="tab:blue", alpha=alpha_fill, zorder=2)

    for i in range(n_patches):                       # луч = патч
        c = "0.35" if arm_colors is None else arm_colors[i]
        ax.plot([np.deg2rad(centers[i]), np.deg2rad(centers[i])],
                [STAR_INNER_R, 1.0], "-", color=c, lw=2.4, zorder=4)
    ax.plot(np.linspace(0, 2 * np.pi, 200), np.ones(200), "-", color="0.75",
            lw=0.8, zorder=1)                        # эталонная окружность
    return nodes
