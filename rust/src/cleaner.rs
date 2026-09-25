//! Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
//! по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
//! Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py).

use crate::signal;

#[derive(Debug, Clone, Copy)]
pub struct CleanerOptions {
    pub baseline_deg: f64,
    pub iqr_k: f64,
    pub max_removed_frac: f64,
    pub min_points: usize,
}

impl Default for CleanerOptions {
    fn default() -> Self {
        Self {
            baseline_deg: 1.0,
            iqr_k: 3.0,
            max_removed_frac: 0.5,
            min_points: 20,
        }
    }
}

pub struct CleanResult {
    pub mask: Vec<bool>,
    pub n_outliers: usize,
    pub window: usize,
}

pub fn clean_iqr(angles: &[f64], radii: &[f64], o: CleanerOptions) -> CleanResult {
    let n = radii.len();
    let mut mask = vec![false; n];
    if n < o.min_points {
        return CleanResult {
            mask,
            n_outliers: 0,
            window: 0,
        };
    }

    let w = signal::window_points(angles, o.baseline_deg);
    let base = signal::median_filter_wrap(radii, w);
    let res: Vec<f64> = (0..n).map(|i| radii[i] - base[i]).collect();

    let center = signal::median(&res);
    let spread = signal::iqr(&res);
    let denom = if spread > 1e-12 { spread } else { 1.0 }; // защита референса

    let sev: Vec<f64> = res.iter().map(|r| (r - center).abs() / denom).collect();
    let mut flagged = 0;
    for i in 0..n {
        mask[i] = sev[i] > o.iqr_k;
        if mask[i] {
            flagged += 1;
        }
    }

    // Предохранитель: не выбрасываем больше max_removed_frac точек.
    let cap = (o.max_removed_frac * n as f64).floor() as usize;
    if cap > 0 && cap < n && flagged > cap {
        let mut kept: Vec<f64> = (0..n).filter(|i| mask[*i]).map(|i| sev[i]).collect();
        kept.sort_by(f64::total_cmp);
        let level = kept[kept.len() - cap];
        flagged = 0;
        for i in 0..n {
            mask[i] = mask[i] && sev[i] >= level;
            if mask[i] {
                flagged += 1;
            }
        }
    }

    CleanResult {
        mask,
        n_outliers: flagged,
        window: w,
    }
}
