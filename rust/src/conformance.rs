//! Проверка порта по конформанс-векторам (spec/conformance/vectors).
//! Допуски — те же, что у C++/Go/C/JS/Java/Kotlin: контур 1e-6 мм, коэффициенты
//! max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).

use std::fs;
use std::path::Path;

use crate::cleaner::{self, CleanerOptions};
use crate::detector::{self, DetectorOptions};
use crate::json::{self, Value};
use crate::model::{Model, ModelOptions, PitShape};

pub struct Outcome {
    pub ok: bool,
    pub detail: String,
    pub notes: Vec<String>,
}

pub struct Vector {
    pub file: String,
    pub data: Value,
}

pub fn load(dir: &Path) -> Result<Vec<Vector>, String> {
    let mut files: Vec<_> = fs::read_dir(dir)
        .map_err(|e| format!("не читать каталог {dir:?}: {e}"))?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "json").unwrap_or(false))
        .collect();
    files.sort();

    let mut out = Vec::with_capacity(files.len());
    for p in files {
        let text = fs::read_to_string(&p).map_err(|e| format!("не читать {p:?}: {e}"))?;
        out.push(Vector {
            file: p
                .file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default(),
            data: json::parse(&text),
        });
    }
    Ok(out)
}

fn near(a: f64, b: f64, rel: f64, floor: f64) -> bool {
    (a - b).abs() <= floor.max(rel * b.abs())
}

pub fn check(v: &Value) -> Outcome {
    match v.text("kind").as_str() {
        "model" => check_model(v),
        "detector" => check_detector(v),
        _ => check_cleaner(v),
    }
}

fn doubles(v: &Value) -> Vec<f64> {
    v.arr().iter().map(|x| x.as_f64()).collect()
}

fn check_detector(v: &Value) -> Outcome {
    let cfg = v.key("config");
    let exp = v.key("expected");
    let input = v.key("input");
    let angles = input.doubles("angles_deg");
    let radii = input.doubles("radii_mm");
    let o = DetectorOptions {
        window_deg: cfg.dbl("window_deg"),
        wide_deg: cfg.dbl("wide_deg"),
        smooth_deg: cfg.dbl("smooth_deg"),
        k: cfg.dbl("k"),
        min_zone_deg: cfg.dbl("min_zone_deg"),
    };

    let band = detector::band_indicator(&angles, &radii, o);
    let zn = detector::zones(&angles, &band, o);
    let exp_zones = exp.key("zones_deg").arr();
    let exp_pits = exp.doubles("pits_deg");
    let mut notes = Vec::new();

    let mut ok = zn.len() == exp_zones.len();
    if !ok {
        notes.push(format!("зон {} != {}", zn.len(), exp_zones.len()));
    }
    let mut dev = 0.0_f64;
    for (i, z) in exp_zones.iter().enumerate() {
        if i >= zn.len() {
            break;
        }
        let e = doubles(z);
        dev = dev.max((zn[i][0] - e[0]).abs()).max((zn[i][1] - e[1]).abs());
    }
    if zn.len() != exp_pits.len() {
        ok = false;
        notes.push(format!("ям {} != {}", zn.len(), exp_pits.len()));
    }
    for (i, p) in exp_pits.iter().enumerate() {
        if i >= zn.len() {
            break;
        }
        let d = (0.5 * (zn[i][0] + zn[i][1]) - p).abs();
        dev = dev.max(d);
        if d > 1e-6 {
            ok = false;
        }
    }
    Outcome {
        ok,
        detail: format!(
            "зон {}/{}, ям {}/{}, max|Δ| {:.2e}°",
            zn.len(),
            exp_zones.len(),
            zn.len(),
            exp_pits.len(),
            dev
        ),
        notes,
    }
}

fn check_cleaner(v: &Value) -> Outcome {
    let cfg = v.key("config");
    let exp = v.key("expected");
    let input = v.key("input");
    let angles = input.doubles("angles_deg");
    let radii = input.doubles("radii_mm");
    let o = CleanerOptions {
        baseline_deg: cfg.dbl("baseline_deg"),
        iqr_k: cfg.dbl("iqr_k"),
        ..CleanerOptions::default()
    };
    let r = cleaner::clean_iqr(&angles, &radii, o);

    let mut ref_mask = vec![false; radii.len()];
    for i in exp.ints("mask_true_indices") {
        ref_mask[i] = true;
    }
    let n = radii.len();
    let (mut extra, mut missing, mut got) = (0usize, 0usize, 0usize);
    for i in 0..n {
        if r.mask[i] {
            got += 1;
            if !ref_mask[i] {
                extra += 1;
            }
        } else if ref_mask[i] {
            missing += 1;
        }
    }
    let frac = v.key("tolerance").dbl_or("frac", 0.02);
    let tol = ((frac * n as f64).floor() as usize).max(1);
    let want = exp.int("n_outliers");
    let ok = extra <= tol && missing <= tol && got.abs_diff(want) <= tol;
    Outcome {
        ok,
        detail: format!("выбросов {got} (эталон {want}), лишних {extra}, пропущено {missing}"),
        notes: Vec::new(),
    }
}

fn check_model(v: &Value) -> Outcome {
    let cfg = v.key("config");
    let exp = v.key("expected");
    let tol = v.key("tolerance");
    let input = v.key("input");
    let mut notes = Vec::new();
    let mut ok = true;

    let opt = ModelOptions {
        n_patches: cfg.int("n_patches"),
        phase_deg: cfg.dbl("phase_deg"),
        deg_min: cfg.int("deg_min"),
        deg_max: cfg.int("deg_max"),
        overlap_train: cfg.dbl("overlap_train"),
        overlap_use: cfg.dbl("overlap_use"),
        deg_elbow_tol: cfg.dbl("deg_elbow_tol"),
        amplitude_scale: cfg.dbl_or("amplitude_scale", 180.0),
        coord_mode: cfg.text("coord_mode"),
    };
    let pits_deg = cfg.doubles("pits_deg");
    let mut m = Model::new(opt, &pits_deg);
    if !pits_deg.is_empty() {
        m.set_pit_shape(PitShape {
            sigma_deg: cfg.dbl("sigma_deg"),
            core_sigma: cfg.dbl("pit_core_sigma"),
            window_sigma: cfg.dbl("pit_window_sigma"),
            pit_min_amp: cfg.dbl("pit_min_amp"),
            tapering: cfg.get("tapering").map(|v| v.bool_or(true)).unwrap_or(true),
        });
    }
    m.fit(&input.doubles("angles_deg"), &input.doubles("radii_mm"));

    let want_deg = exp.ints("degrees");
    let got_deg = m.degrees();
    let deg_ok = want_deg == got_deg;
    if !deg_ok {
        ok = false;
        notes.push(format!("степени {got_deg:?} != {want_deg:?}"));
    }

    let rel = tol.dbl("coefs_rel");
    let floor = tol.dbl("coefs_abs_floor");
    let mut max_c = 0.0_f64;
    let mut bad_c = 0;
    for (i, coefs) in exp.key("coefs").arr().iter().enumerate() {
        let refc = doubles(coefs);
        let got = m.patches().get(i).map(|p| p.coefs.clone()).unwrap_or_default();
        if got.len() != refc.len() {
            ok = false;
            bad_c += 1;
            continue;
        }
        for (j, r) in refc.iter().enumerate() {
            max_c = max_c.max((got[j] - r).abs());
            if !near(got[j], *r, rel, floor) {
                ok = false;
                bad_c += 1;
            }
        }
    }

    let mut max_pit = 0.0_f64;
    let mut bad_pit = 0;
    for (i, term) in exp.key("pit_terms").arr().iter().enumerate() {
        let ref_dx = term.doubles("dx_deg");
        let ref_amp = term.doubles("amp");
        let got_dx = m
            .patches()
            .get(i)
            .map(|p| p.pit_offsets_deg.clone())
            .unwrap_or_default();
        let got_amp = m
            .patches()
            .get(i)
            .map(|p| p.pit_coefs.clone())
            .unwrap_or_default();
        if got_dx.len() != ref_dx.len() {
            ok = false;
            bad_pit += 1;
            continue;
        }
        for (j, r) in ref_dx.iter().enumerate() {
            let da = (got_dx[j] - r).abs();
            max_pit = max_pit.max(da).max((got_amp[j] - ref_amp[j]).abs());
            if da > 1e-9 || !near(got_amp[j], ref_amp[j], rel, floor) {
                ok = false;
                bad_pit += 1;
            }
        }
    }

    let curve = exp.key("curve");
    let ca = curve.doubles("angles_deg");
    let cr = curve.doubles("radii_mm");
    let got = m.eval(&ca);
    let mut max_r = 0.0_f64;
    for (i, r) in cr.iter().enumerate() {
        max_r = max_r.max((got[i] - r).abs());
    }
    if max_r > tol.dbl("curve_mm") {
        ok = false;
    }

    Outcome {
        ok,
        detail: format!(
            "степени {}, коэфф. max|Δ| {:.2e} (плохих {}), термины ям max|Δ| {:.2e} (плохих {}), контур max|Δ| {:.2e} мм",
            if deg_ok { "совпали" } else { "РАСХОДЯТСЯ" },
            max_c,
            bad_c,
            max_pit,
            bad_pit,
            max_r
        ),
        notes,
    }
}
