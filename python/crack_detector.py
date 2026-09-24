"""
crack_detector.py

CrackDetector v3.
Логика: трещина = участок, где detailed < coarse (грубая не провалилась в яму).
Кромки (звон) отсекаются эрозией маски.
"""

import numpy as np
from patch_approximator import PatchApproximator


class CrackDetector:
    def __init__(self,
                 coarse_deg_max=4,
                 coarse_overlap_train=15.0,
                 coarse_overlap_use=5.0,
                 threshold_factor=3.0,
                 min_depth_mm=0.05,
                 min_width_deg=10.0,
                 merge_gap_deg=30.0,
                 erosion_points=5):
        self.coarse_deg_max = coarse_deg_max
        self.coarse_overlap_train = coarse_overlap_train
        self.coarse_overlap_use = coarse_overlap_use
        self.threshold_factor = threshold_factor
        self.min_depth_mm = min_depth_mm
        self.min_width_deg = min_width_deg
        self.merge_gap_deg = merge_gap_deg
        self.erosion_points = erosion_points

    def detect(self, angles, radii, approx_detailed):
        angles = np.asarray(angles, dtype=float)
        radii = np.asarray(radii, dtype=float)

        order = np.argsort(angles)
        angles = angles[order]
        radii = radii[order]
        n = len(radii)
        if n < 20:
            return []

        approx_coarse = PatchApproximator(
            n_patches=approx_detailed.n_patches,
            deg_min=self.coarse_deg_max,
            deg_max=self.coarse_deg_max,
            amplitude_scale=approx_detailed.amplitude_scale,
            overlap_train=self.coarse_overlap_train,
            overlap_use=self.coarse_overlap_use,
        )
        approx_coarse.fit(angles, radii)

        fitted_detailed = approx_detailed.eval(angles)
        fitted_coarse = approx_coarse.eval(angles)

        diff = fitted_detailed - fitted_coarse
        diff_work = diff.copy()

        defects = []
        max_iter = 20

        for _ in range(max_iter):
            i_min = int(np.argmin(diff_work))
            depth = float(-diff_work[i_min])
            if depth < self.min_depth_mm:
                break

            local_threshold = 0.5 * depth

            i_lo = i_min
            while i_lo > 0 and diff_work[i_lo - 1] < -local_threshold:
                i_lo -= 1

            i_hi = i_min
            while i_hi < n - 1 and diff_work[i_hi + 1] < -local_threshold:
                i_hi += 1

            if i_lo > 0:
                d0 = diff_work[i_lo - 1]
                d1 = diff_work[i_lo]
                t = (-local_threshold - d0) / (d1 - d0) if d1 != d0 else 0.0
                a_start = float(angles[i_lo - 1] + t * (angles[i_lo] - angles[i_lo - 1]))
            else:
                a_start = float(angles[i_lo])

            if i_hi < n - 1:
                d0 = diff_work[i_hi]
                d1 = diff_work[i_hi + 1]
                t = (-local_threshold - d0) / (d1 - d0) if d1 != d0 else 0.0
                a_end = float(angles[i_hi] + t * (angles[i_hi + 1] - angles[i_hi]))
            else:
                a_end = float(angles[i_hi])

            width = a_end - a_start
            if width < 0:
                width += 360.0

            # Обрезаем с запасом: от края ямы идём дальше, пока diff < 0,
            # плюс ещё на 5 градусов с каждой стороны
            pad_deg = 10.0
            i_pad_lo = i_lo
            while i_pad_lo > 0 and angles[i_lo] - angles[i_pad_lo] < pad_deg:
                i_pad_lo -= 1
            i_pad_hi = i_hi
            while i_pad_hi < n - 1 and angles[i_pad_hi] - angles[i_hi] < pad_deg:
                i_pad_hi += 1

            for j in range(i_pad_lo, i_pad_hi + 1):
                diff_work[j] = 0.0

            if width < self.min_width_deg:
                continue

            defects.append({
                'angle_start': float(a_start),
                'angle_end': float(a_end),
                'width_deg': float(width),
                'depth_mm': depth,
                'n_points': int(i_hi - i_lo + 1),
            })

        defects = self._merge_defects_by_gap(defects)
        return defects
            
    def _merge_defects_by_gap(self, defects):
        if len(defects) < 2:
            return defects
        defects = sorted(defects, key=lambda d: d['angle_start'])
        merged = [defects[0]]
        for d in defects[1:]:
            last = merged[-1]
            gap = d['angle_start'] - last['angle_end']
            if gap < self.merge_gap_deg:
                last['angle_end'] = d['angle_end']
                last['width_deg'] = last['angle_end'] - last['angle_start']
                last['depth_mm'] = max(last['depth_mm'], d['depth_mm'])
                last['n_points'] += d['n_points']
            else:
                merged.append(d)
        return merged

    def print_report(self, defects):
        if not defects:
            print("  Трещины не обнаружены.")
            return
        print(f"  Найдено трещин: {len(defects)}")
        for j, d in enumerate(defects):
            print(f"    Трещина {j+1}: "
                  f"участок={d['angle_start']:.1f}°—{d['angle_end']:.1f}°, "
                  f"ширина={d['width_deg']:.1f}°, "
                  f"глубина={d['depth_mm']:.3f} мм")
                
    def _cluster_continuous(self, angles, mask):
        clusters = []
        current = []
        for i in range(len(mask)):
            if mask[i]:
                current.append(i)
            else:
                if current:
                    clusters.append(current)
                    current = []
        if current:
            clusters.append(current)
        return clusters

    def _merge_close_clusters(self, angles, clusters, max_gap):
        if len(clusters) < 2:
            return clusters
        merged = [clusters[0]]
        for c in clusters[1:]:
            prev = merged[-1]
            gap = angles[c[0]] - angles[prev[-1]]
            if gap < max_gap:
                merged[-1] = prev + c
            else:
                merged.append(c)
        return merged

    def _merge_wraparound(self, angles, clusters, max_gap):
        if len(clusters) < 2:
            return clusters
        first = clusters[0]
        last = clusters[-1]
        gap = (angles[first[0]] + 360) - angles[last[-1]]
        if gap < max_gap:
            return [last + first] + clusters[1:-1]
        return clusters

    def _merge_nearby_defects(self, defects):
        if len(defects) < 2:
            return defects
        defects = sorted(defects, key=lambda d: d['angle_center'])
        merged = []
        for d in defects:
            if merged:
                last = merged[-1]
                gap = d['angle_start'] - last['angle_end']
                if gap < self.merge_gap_deg:
                    last['angle_end'] = max(last['angle_end'], d['angle_end'])
                    last['width_deg'] = last['angle_end'] - last['angle_start']
                    last['depth_mm'] = max(last['depth_mm'], d['depth_mm'])
                    last['n_points'] += d['n_points']
                    last['angle_center'] = (last['angle_start'] +
                                            last['angle_end']) / 2 % 360
                    continue
            merged.append(d)
        return merged

    def print_report(self, defects):
        if not defects:
            print("  Трещины не обнаружены.")
            return
        print(f"  Найдено трещин: {len(defects)}")
        for j, d in enumerate(defects):
            print(f"    Трещина {j+1}: центр={d['angle_center']:.1f}°, "
                  f"участок={d['angle_start']:.1f}°—{d['angle_end']:.1f}°, "
                  f"ширина={d['width_deg']:.1f}°, "
                  f"глубина={d['depth_mm']:.3f} мм")