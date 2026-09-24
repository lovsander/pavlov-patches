# вырезано из _src_baseline_defects.py (рефакторинг, см. CONTEXT.md §21)

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ..core.outlier_cleaner import build_cleaner, median_filter_wrap, window_points
from .zones import defect_maps, detect_zones, indicator_curve, load_crack_table, mask_to_zones, score_zones, truth_zone_mask

def in_zone(angles, zone):
    """Маска углов внутри угловой зоны (zone = [start, end])."""
    a = np.asarray(angles, dtype=float)
    return (a >= zone[0]) & (a <= zone[1])


def robust_sigma_local(x):
    """sigma = 1.4826 * MAD (локальная копия, чтобы не тянуть лишние импорты)."""
    x = np.asarray(x, dtype=float)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def window_metrics(sec, window_deg, table, depth_frac=0.05):
    """
    Что окно медианного фильтра делает с профилем ОДНОГО сечения.

    retained_depth_mm — насколько фильтр проследил дно каждой трещины:
        0   — проследил (baseline лежит на дне, как эталон);
        < 0 — «срезал»: baseline выше дна, значит признак дефекта ослаблен;
        > 0 — переспустился ниже эталона (обычно шум).
    noise_mm — робастная sigma остатка r − baseline (сколько шума снял фильтр);
    bias_mm  — максимальное расхождение фильтра и эталона ВНЕ трещин
               (насколько фильтр увёл форму профиля).
    """
    a, r = sec["angles"], sec["radii"]
    w = window_points(a, window_deg)
    baseline = median_filter_wrap(r, w)

    truth_zones = mask_to_zones(a, truth_zone_mask(a, sec["height_mm"], table,
                                                  depth_frac), 0.1)
    retained, outside = [], np.ones(len(a), dtype=bool)
    for z in truth_zones:
        m = in_zone(a, z)
        outside &= ~m
        retained.append(float(np.min((sec["ideal"] - baseline)[m])))

    return {
        "window_deg": float(window_deg),
        "window_points": int(w),
        "retained_depth_mm": retained,
        "noise_mm": robust_sigma_local(r - baseline),
        "bias_mm": float(np.max(np.abs(baseline - sec["ideal"])[outside]))
        if np.any(outside) else 0.0,
    }


def candidate_values(cfg, sections, cand, section_ids):
    """Значения кандидата по сечениям: {sid: values}."""
    out = {}
    for sid in section_ids:
        s = sections[sid]
        out[sid] = indicator_curve(s["angles_clean"], s["radii_clean"],
                                   cand["kind"], cand.get("window_deg", 1.0),
                                   cand.get("envelope_deg", cfg["envelope_deg"]),
                                   cand.get("smooth_deg", cfg["smooth_deg"]),
                                   cand.get("wide_deg", cfg["wide_deg"]))
    return out


def truth_zones_by_section(cfg, sections, table, section_ids=None):
    """Истинные зоны трещин (по таблице генератора) для каждого сечения."""
    ids = section_ids if section_ids is not None else list(sections.keys())
    out = {}
    for sid in ids:
        s = sections[sid]
        out[sid] = mask_to_zones(
            s["angles"],
            truth_zone_mask(s["angles"], s["height_mm"], table,
                            cfg["detector"]["truth_depth_frac"]),
            0.1)
    return out


def candidate_results(cfg, sections, table, section_ids=None, truth=None):
    """
    Прогон кандидатов при «паспортных» порогах k из конфига.

    Возвращает dict:
      labels   — порядок подписей;
      per      — {label: {sid: {'values', 'zones', 'score'}}};
      mean     — {label: средние precision/recall/f1/fp по сечениям};
      truth    — {sid: истинные зоны};
      sections — по каким сечениям считали.
    """
    ids = list(section_ids if section_ids is not None else cfg["sections"])
    if truth is None:
        truth = truth_zones_by_section(cfg, sections, table, ids)
    dz = cfg["detector"]["min_zone_deg"]
    per, mean, labels = {}, {}, []
    for cand in cfg["candidates"]:
        labels.append(cand["label"])
        values = candidate_values(cfg, sections, cand, ids)
        block, prec, rec, f1, fp = {}, [], [], [], []
        for sid in ids:
            zones = detect_zones(sections[sid]["angles_clean"], values[sid],
                                 cand["k"], dz)
            sc = score_zones(zones, truth[sid])
            block[sid] = {"values": values[sid], "zones": zones, "score": sc}
            prec.append(sc["precision"])
            rec.append(sc["recall"])
            f1.append(sc["f1"])
            fp.append(sc["fp"])
        per[cand["label"]] = block
        mean[cand["label"]] = {
            "k": cand["k"],
            "precision": float(np.mean(prec)),
            "recall": float(np.mean(rec)),
            "f1": float(np.mean(f1)),
            "fp": float(np.mean(fp)),
        }
    return {"labels": labels, "per": per, "mean": mean, "truth": truth,
            "sections": ids}


def sweep_thresholds(cfg, sections, table, truth=None):
    """
    Подбор порога k для каждого кандидата по максимуму F1 (по зонам, среднее по
    сечениям). Признак полезен, если у него есть k с высоким F1, и он устойчив.

    Возвращает {label: {'rows': [{'k','precision','recall','f1','fp'}],
                        'best': row, 'sections': [...]}}.
    """
    ks = np.arange(cfg["k_sweep"]["min"], cfg["k_sweep"]["max"] + 1e-9,
                   cfg["k_sweep"]["step"])
    ids = list(cfg["all_sections"])
    if truth is None:
        truth = truth_zones_by_section(cfg, sections, table, ids)
    dz = cfg["k_sweep"]["min_zone_deg"]
    out = {}
    for cand in cfg["candidates"]:
        values = candidate_values(cfg, sections, cand, ids)
        rows = []
        for k in ks:
            prec, rec, f1, fp = [], [], [], []
            for sid in ids:
                zones = detect_zones(sections[sid]["angles_clean"], values[sid],
                                     float(k), dz)
                sc = score_zones(zones, truth[sid])
                prec.append(sc["precision"])
                rec.append(sc["recall"])
                f1.append(sc["f1"])
                fp.append(sc["fp"])
            rows.append({"k": float(k),
                         "precision": float(np.mean(prec)),
                         "recall": float(np.mean(rec)),
                         "f1": float(np.mean(f1)),
                         "fp": float(np.mean(fp))})
        best = max(rows, key=lambda r: (r["f1"], -r["fp"]))
        out[cand["label"]] = {"rows": rows, "best": best, "sections": ids}
    return out
