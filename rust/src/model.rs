//! Модель PAPPA (Rust): патчи с адаптивной степенью по нормированной координате,
//! smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
//! Совпадает с референсом Python и остальными портами: тот же базис, та же политика
//! степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней — ОДНИМ
//! накоплением Грама в базисе Чебышёва + RMSE по явным остаткам.

use crate::linalg;
use crate::signal;

#[derive(Debug, Clone)]
pub struct ModelOptions {
    pub n_patches: usize,
    pub phase_deg: f64,
    pub deg_min: usize,
    pub deg_max: usize,
    pub overlap_train: f64,
    pub overlap_use: f64,
    pub deg_elbow_tol: f64,
    pub amplitude_scale: f64,
    pub coord_mode: String,
}

impl Default for ModelOptions {
    fn default() -> Self {
        Self {
            n_patches: 7,
            phase_deg: 24.75,
            deg_min: 4,
            deg_max: 14,
            overlap_train: 15.0,
            overlap_use: 5.0,
            deg_elbow_tol: 0.05,
            amplitude_scale: 180.0,
            coord_mode: "normalized".to_string(),
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct PitShape {
    pub sigma_deg: f64,
    pub core_sigma: f64,
    pub window_sigma: f64,
    pub pit_min_amp: f64,
    pub tapering: bool,
}

impl Default for PitShape {
    fn default() -> Self {
        Self {
            sigma_deg: 3.0,
            core_sigma: 2.0,
            window_sigma: 3.2,
            pit_min_amp: 3e-3,
            tapering: true,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Metrics {
    pub amplitude_mm: f64,
    pub mean_radius_mm: f64,
    pub amplitude_norm: f64,
    pub deg_elbow_tol: f64,
    pub rmse_selected_mm: f64,
    pub rmse_best_mm: f64,
    pub n_train_points: usize,
}

#[derive(Debug, Clone)]
pub struct Stats {
    pub rmse_mm: f64,
    pub mae_mm: f64,
    pub max_err_mm: f64,
    pub correlation: f64,
}

#[derive(Debug, Clone)]
pub struct Patch {
    pub center_deg: f64,
    pub degree: usize,
    pub n_points: usize,
    pub coefs: Vec<f64>,
    pub pit_offsets_deg: Vec<f64>,
    pub pit_coefs: Vec<f64>,
    pub metrics: Metrics,
    pub stats: Stats,
}

pub struct Model {
    opt: ModelOptions,
    pit: PitShape,
    pits: Vec<f64>,
    patches: Vec<Patch>,
    half_sector: f64,
    is_fitted: bool,
}

impl Model {
    pub fn new(opt: ModelOptions, pits_deg: &[f64]) -> Self {
        Self {
            opt,
            pit: PitShape::default(),
            pits: pits_deg
                .iter()
                .map(|c| ((c % 360.0) + 360.0) % 360.0)
                .collect(),
            patches: Vec::new(),
            half_sector: 0.0,
            is_fitted: false,
        }
    }

    pub fn with_defaults() -> Self {
        Self::new(ModelOptions::default(), &[])
    }

    pub fn options(&self) -> &ModelOptions {
        &self.opt
    }

    pub fn set_pit_shape(&mut self, shape: PitShape) {
        self.pit = shape;
    }

    pub fn pit_shape(&self) -> PitShape {
        self.pit
    }

    pub fn pits(&self) -> &[f64] {
        &self.pits
    }

    pub fn has_pits(&self) -> bool {
        !self.pits.is_empty()
    }

    pub fn patches(&self) -> &[Patch] {
        &self.patches
    }

    pub fn half_sector(&self) -> f64 {
        self.half_sector
    }

    pub fn half_train(&self) -> f64 {
        self.half_sector + self.opt.overlap_train
    }

    pub fn half_use(&self) -> f64 {
        self.half_sector + self.opt.overlap_use
    }

    pub fn is_fitted(&self) -> bool {
        self.is_fitted
    }

    pub fn degrees(&self) -> Vec<usize> {
        self.patches.iter().map(|p| p.degree).collect()
    }

    /// Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg).
    pub fn pit_shape_deg(&self, d_deg: f64) -> f64 {
        let d = d_deg.abs();
        let sigma = self.pit.sigma_deg;
        let val = (-(d * d) / (2.0 * sigma * sigma)).exp();
        if !self.pit.tapering {
            return val;
        }
        let core = self.pit.core_sigma * sigma;
        let edge = self.pit.window_sigma * sigma;
        if edge <= core {
            return val;
        }
        let mut t = (edge - d) / (edge - core);
        t = t.clamp(0.0, 1.0);
        val * t * t * (3.0 - 2.0 * t)
    }

    /// Смещения видимых ям в локальной системе патча (°).
    pub fn pit_offsets(&self, center_deg: f64, half_win_deg: f64) -> Vec<f64> {
        self.pits
            .iter()
            .map(|p| signal::circ_local(*p, center_deg))
            .filter(|dx| dx.abs() <= half_win_deg)
            .collect()
    }

    pub fn weight(&self, d_deg: f64, half_use: f64) -> f64 {
        if d_deg <= self.half_sector {
            1.0
        } else if d_deg <= half_use {
            signal::smoothstep(1.0 - (d_deg - self.half_sector) / (half_use - self.half_sector))
        } else {
            0.0
        }
    }

    /// Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
    /// не хуже лучшей более чем на deg_elbow_tol. Быстрая ветка (normalized) — одно
    /// накопление Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
    fn estimate_degree(&self, xs: &[f64], ys: &[f64]) -> (usize, f64, f64) {
        let n = xs.len();
        if n < 5 {
            return (self.opt.deg_min, 0.0, 0.0);
        }

        let mut degs: Vec<usize> = Vec::new();
        let mut rmses: Vec<f64> = Vec::new();
        let mut best_deg = self.opt.deg_min;
        let mut best = f64::INFINITY;

        if self.opt.coord_mode == "raw" {
            // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
            for deg in (self.opt.deg_min..=self.opt.deg_max).step_by(2) {
                let mut a = vec![vec![0.0; deg + 1]; n];
                for i in 0..n {
                    let mut p = 1.0;
                    for j in 0..=deg {
                        a[i][deg - j] = p;
                        p *= xs[i];
                    }
                }
                let c = linalg::lstsq_qr(&a, ys);
                let mut sse = 0.0;
                for i in 0..n {
                    let e = linalg::polyval(&c, xs[i]) - ys[i];
                    sse += e * e;
                }
                let r = (sse / n as f64).sqrt();
                degs.push(deg);
                rmses.push(r);
                if r < best {
                    best = r;
                    best_deg = deg;
                }
            }
        } else {
            let dmax = self.opt.deg_max;
            let p = dmax + 1;
            let yref = ys.iter().sum::<f64>() / n as f64;
            let mut gram = vec![vec![0.0; p]; p];
            let mut rhs = vec![0.0; p];
            for i in 0..n {
                let t = linalg::cheb_row(xs[i], dmax);
                let yc = ys[i] - yref;
                for a in 0..p {
                    rhs[a] += t[a] * yc;
                    for c in a..p {
                        gram[a][c] += t[a] * t[c];
                    }
                }
            }
            for a in 0..p {
                for c in a + 1..p {
                    gram[c][a] = gram[a][c];
                }
            }
            for deg in (self.opt.deg_min..=dmax).step_by(2) {
                let nn = deg + 1;
                let a: Vec<Vec<f64>> = (0..nn).map(|r| gram[r][..nn].to_vec()).collect();
                let b = rhs[..nn].to_vec();
                let c = linalg::lstsq_qr(&a, &b);
                let mut sse = 0.0;
                for i in 0..n {
                    let e = linalg::cheb_sum(&c, deg, xs[i]) - (ys[i] - yref);
                    sse += e * e;
                }
                let r = (sse / n as f64).sqrt();
                degs.push(deg);
                rmses.push(r);
                if r < best {
                    best = r;
                    best_deg = deg;
                }
            }
        }

        let limit = best * (1.0 + self.opt.deg_elbow_tol);
        let mut sel = best_deg;
        let mut rmse_sel = best;
        for (k, deg) in degs.iter().enumerate() {
            if rmses[k] <= limit {
                sel = *deg;
                rmse_sel = rmses[k];
                break;
            }
        }
        (sel, rmse_sel, best)
    }

    /// Точки обучающего окна патча (локальная координата: нормированная или сырая).
    fn window_of(&self, angles: &[f64], radii: &[f64], center: f64) -> (Vec<f64>, Vec<f64>) {
        let half = self.half_train();
        let norm = self.opt.coord_mode != "raw";
        let mut xs = Vec::new();
        let mut ys = Vec::new();
        for shift in [-360.0_f64, 0.0, 360.0] {
            for i in 0..angles.len() {
                let dx = angles[i] + shift - center;
                if dx >= -half && dx <= half {
                    xs.push(if norm { dx / half } else { dx });
                    ys.push(radii[i]);
                }
            }
        }
        (xs, ys)
    }

    pub fn fit(&mut self, angles: &[f64], radii: &[f64]) -> &mut Self {
        assert_eq!(angles.len(), radii.len(), "fit: длины не совпадают");
        assert!(angles.len() >= 10, "fit: слишком мало точек");

        let sector = 360.0 / self.opt.n_patches as f64;
        self.half_sector = sector / 2.0;
        let centers: Vec<f64> = (0..self.opt.n_patches)
            .map(|i| {
                let mut c = (i as f64 * sector + self.half_sector + self.opt.phase_deg) % 360.0;
                if c < 0.0 {
                    c += 360.0;
                }
                c
            })
            .collect();
        let half_train = self.half_train();
        self.patches.clear();

        for c in centers {
            let (xs, ys) = self.window_of(angles, radii, c);
            let n = xs.len();
            if n < 5 {
                continue;
            }
            let (deg, rmse_sel, rmse_best) = self.estimate_degree(&xs, &ys);

            let offs = self.pit_offsets(c, half_train);
            let ncol = deg + 1 + offs.len();
            let mut a = vec![vec![0.0; ncol]; n];
            for i in 0..n {
                let mut p = 1.0;
                for k in (0..=deg).rev() {
                    a[i][k] = p;
                    p *= xs[i];
                }
                for (j, off) in offs.iter().enumerate() {
                    a[i][deg + 1 + j] = self.pit_shape_deg((xs[i] * half_train - off).abs());
                }
            }
            let coef = linalg::lstsq_qr(&a, &ys);
            let poly_coef = coef[..deg + 1].to_vec();

            // Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
            let mut kept_offsets: Vec<f64> = Vec::new();
            let mut kept_coefs: Vec<f64> = Vec::new();
            for (j, off) in offs.iter().enumerate() {
                let mut max_abs = 0.0_f64;
                for i in 0..n {
                    let d_deg = (xs[i] * half_train - off).abs();
                    max_abs = max_abs.max((coef[deg + 1 + j] * self.pit_shape_deg(d_deg)).abs());
                }
                if max_abs >= self.pit.pit_min_amp {
                    kept_offsets.push(*off);
                    kept_coefs.push(coef[deg + 1 + j]);
                }
            }

            let patch = self.build_patch(c, deg, &xs, &ys, &poly_coef, &kept_offsets,
                &kept_coefs, rmse_sel, rmse_best, angles, radii);
            self.patches.push(patch);
        }
        self.is_fitted = true;
        self
    }

    /// Метрики и статистика патча по его обучающему окну (полный базис).
    #[allow(clippy::too_many_arguments)]
    fn build_patch(&self, c: f64, deg: usize, xs: &[f64], ys: &[f64], poly_coef: &[f64],
                   kept_offsets: &[f64], kept_coefs: &[f64], rmse_sel: f64, rmse_best: f64,
                   angles: &[f64], radii: &[f64]) -> Patch {
        let n = xs.len();
        let half_train = self.half_train();
        let mut sse = 0.0;
        let mut sae = 0.0;
        let mut mx = 0.0_f64;
        let mut fit_vals = vec![0.0; n];
        for i in 0..n {
            let mut v = linalg::polyval(poly_coef, xs[i]);
            for (j, off) in kept_offsets.iter().enumerate() {
                v += kept_coefs[j] * self.pit_shape_deg((xs[i] * half_train - off).abs());
            }
            fit_vals[i] = v;
            let e = v - ys[i];
            sse += e * e;
            sae += e.abs();
            mx = mx.max(e.abs());
        }
        let nf = n as f64;
        let mf = fit_vals.iter().sum::<f64>() / nf;
        let my = ys.iter().sum::<f64>() / nf;
        let mut cov = 0.0;
        let mut vf = 0.0;
        let mut vy = 0.0;
        for i in 0..n {
            let df = fit_vals[i] - mf;
            let dy = ys[i] - my;
            cov += df * dy;
            vf += df * df;
            vy += dy * dy;
        }
        let corr = if vf > 0.0 && vy > 0.0 {
            cov / (vf * vy).sqrt()
        } else {
            0.0
        };

        // Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
        let sec: Vec<f64> = (0..angles.len())
            .filter(|i| signal::circ_dist(angles[*i], c) <= self.half_sector)
            .map(|i| radii[i])
            .collect();
        let mut amp = 0.0;
        let mut mean_sec = 0.0;
        if sec.len() >= 5 {
            amp = signal::percentile_linear(&sec, 95.0) - signal::percentile_linear(&sec, 5.0);
            mean_sec = sec.iter().sum::<f64>() / sec.len() as f64;
        }

        Patch {
            center_deg: c,
            degree: deg,
            n_points: n,
            coefs: poly_coef.to_vec(),
            pit_offsets_deg: kept_offsets.to_vec(),
            pit_coefs: kept_coefs.to_vec(),
            metrics: Metrics {
                amplitude_mm: amp,
                mean_radius_mm: mean_sec,
                amplitude_norm: if mean_sec > 0.0 { amp / mean_sec } else { 0.0 },
                deg_elbow_tol: self.opt.deg_elbow_tol,
                rmse_selected_mm: rmse_sel,
                rmse_best_mm: rmse_best,
                n_train_points: n,
            },
            stats: Stats {
                rmse_mm: (sse / nf).sqrt(),
                mae_mm: sae / nf,
                max_err_mm: mx,
                correlation: corr,
            },
        }
    }

    /// Контур: нормированное smoothstep-смешивание патчей (partition of unity).
    pub fn eval_part(&self, angles: &[f64], part: &str) -> Vec<f64> {
        assert!(self.is_fitted, "Сначала вызовите fit()");
        let half_use = self.half_use();
        let half_train = self.half_train();
        let raw = self.opt.coord_mode == "raw";
        angles
            .iter()
            .map(|a| {
                let mut sum_wv = 0.0;
                let mut sum_w = 0.0;
                for p in &self.patches {
                    let w = self.weight(signal::circ_dist(*a, p.center_deg), half_use);
                    if w <= 0.0 {
                        continue;
                    }
                    let dx = signal::circ_local(*a, p.center_deg);
                    let x = if raw { dx } else { dx / half_train };
                    let mut v = 0.0;
                    if part != "pit" {
                        v += linalg::polyval(&p.coefs, x);
                    }
                    if part != "poly" {
                        for (j, off) in p.pit_offsets_deg.iter().enumerate() {
                            v += p.pit_coefs[j] * self.pit_shape_deg((x * half_train - off).abs());
                        }
                    }
                    sum_wv += w * v;
                    sum_w += w;
                }
                if sum_w > 0.0 {
                    sum_wv / sum_w
                } else {
                    0.0
                }
            })
            .collect()
    }

    pub fn eval(&self, angles: &[f64]) -> Vec<f64> {
        self.eval_part(angles, "total")
    }
}
