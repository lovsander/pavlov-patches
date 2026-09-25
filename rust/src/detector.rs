//! Детектор ям (трещин) — повторение python/pappa/analysis/zones.py:
//!   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
//!   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
//!   зоны = участки, где индикатор > k, длиной не короче min_zone_deg.

use crate::signal;

#[derive(Debug, Clone, Copy)]
pub struct DetectorOptions {
    pub window_deg: f64,
    pub wide_deg: f64,
    pub smooth_deg: f64,
    pub k: f64,
    pub min_zone_deg: f64,
}

impl Default for DetectorOptions {
    fn default() -> Self {
        Self {
            window_deg: 1.0,
            wide_deg: 10.0,
            smooth_deg: 2.0,
            k: 5.5,
            min_zone_deg: 2.0,
        }
    }
}

pub fn band_indicator(angles: &[f64], radii: &[f64], o: DetectorOptions) -> Vec<f64> {
    let n = radii.len();
    let w_narrow = signal::window_points(angles, o.window_deg);
    let w_wide = signal::window_points(angles, o.wide_deg);
    let w_smooth = signal::window_points(angles, o.smooth_deg);

    let narrow = signal::median_filter_wrap(radii, w_narrow);
    let wide = signal::median_filter_wrap(radii, w_wide);
    let band: Vec<f64> = (0..n).map(|i| (narrow[i] - wide[i]).abs()).collect();

    let mut out = signal::smooth_wrap(&band, w_smooth);
    let s = signal::robust_sigma(&out);
    if s > 1e-12 {
        for v in out.iter_mut() {
            *v /= s;
        }
    } else {
        out.iter_mut().for_each(|v| *v = 0.0);
    }
    out
}

/// Непрерывные зоны по маске: Vec<[начало, конец]> в градусах.
pub fn mask_to_zones(angles: &[f64], mask: &[bool], o: DetectorOptions) -> Vec<[f64; 2]> {
    let n = angles.len();
    if !mask.iter().any(|b| *b) {
        return Vec::new();
    }

    let diffs: Vec<f64> = (1..n).map(|i| angles[i] - angles[i - 1]).collect();
    let step = if diffs.is_empty() {
        1.0
    } else {
        signal::median(&diffs)
    };

    let mut zones: Vec<[f64; 2]> = Vec::new();
    let mut i = 0;
    while i < n {
        if !mask[i] {
            i += 1;
            continue;
        }
        let mut j = i;
        while j + 1 < n && mask[j + 1] {
            j += 1;
        }
        zones.push([angles[i] - step / 2.0, angles[j] + step / 2.0]);
        i = j + 1;
    }

    // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
    if zones.len() > 1 && mask[0] && mask[n - 1] {
        let first = zones[0];
        let last = zones[zones.len() - 1];
        let mut merged: Vec<[f64; 2]> = Vec::with_capacity(zones.len() - 1);
        merged.push([last[0] - 360.0, first[1]]);
        merged.extend_from_slice(&zones[1..zones.len() - 1]);
        zones = merged;
    }

    zones
        .into_iter()
        .filter(|z| z[1] - z[0] >= o.min_zone_deg)
        .collect()
}

pub fn zones(angles: &[f64], values: &[f64], o: DetectorOptions) -> Vec<[f64; 2]> {
    let mask: Vec<bool> = values.iter().map(|v| *v > o.k).collect();
    mask_to_zones(angles, &mask, o)
}

/// Центры ям (°) — середины найденных зон.
pub fn pits(angles: &[f64], radii: &[f64], o: DetectorOptions) -> Vec<f64> {
    let band = band_indicator(angles, radii, o);
    zones(angles, &band, o)
        .into_iter()
        .map(|z| 0.5 * (z[0] + z[1]))
        .collect()
}
