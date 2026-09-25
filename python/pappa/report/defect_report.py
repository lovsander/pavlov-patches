# вырезано из _src_baseline_defects.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.outlier_cleaner import build_cleaner, median_filter_wrap, window_points
from ..analysis.zones import defect_maps, detect_zones, indicator_curve, load_crack_table, mask_to_zones, score_zones, truth_zone_mask

def report_candidates(cand_res, title):
    """Печать таблицы кандидатов (по зонам) в stdout."""
    print("")
    print(f"--- {title} ---")
    print(f"{'признак':<26} {'k':>5} {'precision':>9} {'recall':>7} "
          f"{'F1':>6} {'FP-зон/сеч':>10}")
    for lab in cand_res["labels"]:
        m = cand_res["mean"][lab]
        print(f"{lab:<26} {m['k']:>5.1f} {m['precision']:>9.2f} "
              f"{m['recall']:>7.2f} {m['f1']:>6.2f} {m['fp']:>10.2f}")
