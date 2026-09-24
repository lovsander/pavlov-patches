# вырезано из _src_star_layout.py (рефакторинг, см. CONTEXT.md §21)
"""appa.core.geometry — углы узлов/центров патчей и круговые операции."""

import numpy as np

def node_angles(n_patches, phase_deg):
    """
    Углы узлов (границ патчей) симметричной раскладки, °.

    PatchApproximator: центр патча i = i*sector + sector/2 + phase
    => граница между патчами i и i+1 = (i+1)*sector + phase.
    """
    sector = 360.0 / n_patches
    return np.mod(phase_deg + sector * np.arange(n_patches), 360.0)


def patch_centers(n_patches, phase_deg):
    """Углы центров патчей (вершин лучей) симметричной раскладки, °."""
    sector = 360.0 / n_patches
    return np.mod(phase_deg + sector * (np.arange(n_patches) + 0.5), 360.0)
