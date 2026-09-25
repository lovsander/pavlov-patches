//! Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin:
//!   <out_dir>/sample.json              манифест (format pappa-sample v1.0)
//!   <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
//! Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
//! сравниваются численно (python/studies/verify_port.py).

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::cleaner::CleanerOptions;
use crate::csv::SectionModel;
use crate::detector::DetectorOptions;
use crate::json;
use crate::model::Model;
use crate::{PORT_LANGUAGE, PORT_VERSION};

/// Сечение даты из числа дней с 1970-01-01 (алгоритм Говарда Хиннанта).
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as i64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = (if mp < 10 { mp + 3 } else { mp - 9 }) as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

pub fn iso_utc_now() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let days = secs.div_euclid(86400);
    let rem = secs.rem_euclid(86400);
    let (y, m, d) = civil_from_days(days);
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}Z",
        y,
        m,
        d,
        rem / 3600,
        (rem % 3600) / 60,
        rem % 60
    )
}

/// Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++.
pub struct Writer {
    pub sb: String,
    depth: usize,
}

impl Default for Writer {
    fn default() -> Self {
        Self::new()
    }
}

impl Writer {
    pub fn new() -> Self {
        Self {
            sb: String::new(),
            depth: 0,
        }
    }

    pub fn ind(&self) -> String {
        "  ".repeat(self.depth)
    }

    pub fn obj_start(&mut self) {
        self.sb.push('{');
        self.depth += 1;
        self.sb.push('\n');
        self.sb.push_str(&self.ind());
    }

    pub fn obj_end(&mut self) {
        self.depth -= 1;
        let ind = self.ind();
        self.sb.push('\n');
        self.sb.push_str(&ind);
        self.sb.push('}');
    }

    pub fn arr_start(&mut self) {
        self.sb.push('[');
        self.depth += 1;
        self.sb.push('\n');
        self.sb.push_str(&self.ind());
    }

    pub fn arr_end(&mut self) {
        self.depth -= 1;
        let ind = self.ind();
        self.sb.push('\n');
        self.sb.push_str(&ind);
        self.sb.push(']');
    }

    pub fn comma(&mut self) {
        self.sb.push(',');
        self.sb.push('\n');
        self.sb.push_str(&self.ind());
    }

    pub fn key(&mut self, k: &str) {
        let ind = self.ind();
        self.sb.push_str(&ind);
        self.sb.push('"');
        self.sb.push_str(k);
        self.sb.push_str("\": ");
    }

    pub fn str_val(&mut self, v: &str) {
        self.sb.push('"');
        self.sb.push_str(&json::esc(v));
        self.sb.push('"');
    }

    pub fn num_val(&mut self, v: f64) {
        self.sb.push_str(&json::num(v));
    }

    pub fn raw(&mut self, s: &str) {
        self.sb.push_str(s);
    }

    pub fn kv_str(&mut self, k: &str, v: &str) {
        self.key(k);
        self.str_val(v);
    }

    pub fn kv_num(&mut self, k: &str, v: f64) {
        self.key(k);
        self.num_val(v);
    }

    pub fn kv_usize(&mut self, k: &str, v: usize) {
        self.key(k);
        self.sb.push_str(&v.to_string());
    }

    pub fn kv_bool(&mut self, k: &str, v: bool) {
        self.key(k);
        self.sb.push_str(if v { "true" } else { "false" });
    }
}

fn write_patches(w: &mut Writer, m: &Model) {
    w.key("patches");
    w.arr_start();
    for (i, p) in m.patches().iter().enumerate() {
        if i > 0 {
            w.sb.push_str(",\n");
            w.sb.push_str(&w.ind());
        } else {
            w.sb.push('\n');
            w.sb.push_str(&w.ind());
        }
        w.obj_start();
        w.kv_num("center_deg", p.center_deg);
        w.comma();
        w.kv_usize("degree", p.degree);
        w.comma();
        w.kv_usize("n_points", p.n_points);
        w.comma();
        w.key("coefs");
        w.arr_start();
        for (j, c) in p.coefs.iter().enumerate() {
            if j > 0 {
                w.raw(", ");
            }
            w.num_val(*c);
        }
        w.arr_end();
        w.comma();

        w.key("metrics");
        w.obj_start();
        w.kv_num("amplitude_mm", p.metrics.amplitude_mm);
        w.comma();
        w.kv_num("mean_radius_mm", p.metrics.mean_radius_mm);
        w.comma();
        w.kv_num("amplitude_norm", p.metrics.amplitude_norm);
        w.comma();
        w.kv_num("deg_elbow_tol", p.metrics.deg_elbow_tol);
        w.comma();
        w.kv_num("rmse_selected_mm", p.metrics.rmse_selected_mm);
        w.comma();
        w.kv_num("rmse_best_mm", p.metrics.rmse_best_mm);
        w.comma();
        w.kv_usize("n_train_points", p.metrics.n_train_points);
        w.obj_end();
        w.comma();

        w.key("stats");
        w.obj_start();
        w.kv_num("rmse_mm", p.stats.rmse_mm);
        w.comma();
        w.kv_num("mae_mm", p.stats.mae_mm);
        w.comma();
        w.kv_num("max_err_mm", p.stats.max_err_mm);
        w.comma();
        w.kv_num("correlation", p.stats.correlation);
        w.obj_end();

        // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
        // (включая пустой список): так ждёт загрузчик Python.
        if m.has_pits() {
            w.comma();
            w.key("pit_terms");
            w.arr_start();
            for (j, off) in p.pit_offsets_deg.iter().enumerate() {
                if j > 0 {
                    w.raw(", ");
                }
                w.obj_start();
                w.kv_num("dx_deg", *off);
                w.comma();
                w.kv_num("amp", p.pit_coefs[j]);
                w.obj_end();
            }
            w.arr_end();
        }
        w.obj_end();
    }
    if !m.patches().is_empty() {
        w.sb.push('\n');
        w.sb.push_str(&w.ind());
    }
    w.arr_end();
}

pub fn save_section_document(path: &Path, section: &SectionModel) -> Result<String, String> {
    let m = &section.model;
    if !m.is_fitted() {
        return Err("save_section_document: модель не обучена".to_string());
    }
    let mut w = Writer::new();
    w.obj_start();
    w.kv_str("format", "pappa");
    w.comma();
    w.kv_str("version", "2.0");
    w.comma();
    w.kv_str(
        "method",
        if m.has_pits() {
            "PitPatchApproximator"
        } else {
            "PatchApproximator"
        },
    );
    w.comma();
    w.kv_str("created", &iso_utc_now());
    w.comma();

    w.key("software");
    w.obj_start();
    w.kv_str("language", PORT_LANGUAGE);
    w.comma();
    w.kv_str("pappa_version", PORT_VERSION);
    w.obj_end();
    w.comma();

    w.key("meta");
    w.obj_start();
    w.kv_usize("section_id", section.section_id);
    w.comma();
    w.kv_num("height_mm", section.height_mm);
    w.comma();
    w.kv_str("source", "csv");
    w.comma();
    w.kv_str("description", &section.description);
    w.obj_end();
    w.comma();

    w.key("global");
    w.obj_start();
    w.key("units");
    w.obj_start();
    w.kv_str("angle", "degree");
    w.comma();
    w.kv_str("length", "mm");
    w.obj_end();
    w.comma();
    let opt = m.options();
    w.kv_usize("n_patches", opt.n_patches);
    w.comma();
    w.kv_num("half_sector_deg", m.half_sector());
    w.comma();
    w.kv_num("phase_deg", opt.phase_deg);
    w.comma();
    w.kv_num("half_train_deg", m.half_train());
    w.comma();
    w.kv_num("half_use_deg", m.half_use());
    w.comma();
    w.kv_num("overlap_train_deg", opt.overlap_train);
    w.comma();
    w.kv_num("overlap_use_deg", opt.overlap_use);
    w.comma();
    w.kv_usize("deg_min", opt.deg_min);
    w.comma();
    w.kv_usize("deg_max", opt.deg_max);
    w.comma();
    w.kv_str("coord_mode", &opt.coord_mode);
    w.comma();
    w.kv_num("deg_elbow_tol", opt.deg_elbow_tol);
    w.comma();
    w.kv_num("amplitude_scale", opt.amplitude_scale);
    if m.has_pits() {
        let ps = m.pit_shape();
        w.comma();
        w.key("pit");
        w.obj_start();
        w.kv_num("sigma_deg", ps.sigma_deg);
        w.comma();
        w.kv_num("core_sigma", ps.core_sigma);
        w.comma();
        w.kv_num("window_sigma", ps.window_sigma);
        w.comma();
        w.kv_num("pit_min_amp", ps.pit_min_amp);
        w.comma();
        w.kv_bool("tapering", ps.tapering);
        w.comma();
        w.key("centers_deg");
        w.arr_start();
        for (i, c) in m.pits().iter().enumerate() {
            if i > 0 {
                w.raw(", ");
            }
            w.num_val(*c);
        }
        w.arr_end();
        w.obj_end();
    }
    w.obj_end();
    w.comma();

    write_patches(&mut w, m);
    w.comma();

    w.key("statistics");
    w.obj_start();
    w.kv_usize("n_points_total", section.n_points_total);
    w.comma();
    w.kv_usize("n_outliers_removed", section.n_outliers);
    w.comma();
    w.kv_num("fit_time_ms", section.fit_time_ms);
    w.obj_end();

    w.obj_end();
    fs::write(path, format!("{}\n", w.sb)).map_err(|e| format!("не записать {path:?}: {e}"))?;
    Ok(path.to_string_lossy().to_string())
}

/// Параметры записи папки образца.
pub struct SampleOptions {
    pub input_csv: String,
    pub pits: bool,
    pub description: String,
    pub cleaner: CleanerOptions,
    pub detector: DetectorOptions,
}

impl Default for SampleOptions {
    fn default() -> Self {
        Self {
            input_csv: String::new(),
            pits: true,
            description: "PAPPA Rust port".to_string(),
            cleaner: CleanerOptions::default(),
            detector: DetectorOptions::default(),
        }
    }
}

pub fn save_sample(
    out_dir: &str,
    name: &str,
    sections: &[SectionModel],
    o: &SampleOptions,
) -> Result<String, String> {
    let root = PathBuf::from(out_dir);
    fs::create_dir_all(root.join("sections")).map_err(|e| format!("не создать {out_dir}: {e}"))?;

    let mut ordered: Vec<&SectionModel> = sections.iter().collect();
    ordered.sort_by_key(|s| s.section_id);
    let first = ordered.first().map(|s| &s.model);

    let mut w = Writer::new();
    w.obj_start();
    w.kv_str("format", "pappa-sample");
    w.comma();
    w.kv_str("version", "1.0");
    w.comma();
    w.kv_str("name", name);
    w.comma();
    w.kv_str("created", &iso_utc_now());
    w.comma();

    w.key("units");
    w.obj_start();
    w.kv_str("angle", "degree");
    w.comma();
    w.kv_str("length", "mm");
    w.obj_end();
    w.comma();

    w.key("meta");
    w.obj_start();
    w.kv_str("description", &o.description);
    w.obj_end();
    w.comma();

    if !o.input_csv.is_empty() {
        w.key("input");
        w.obj_start();
        w.kv_str("csv", &o.input_csv);
        w.obj_end();
        w.comma();
    }

    w.key("config");
    w.obj_start();
    let opt = first.map(|m| m.options().clone());
    w.kv_usize("n_patches", opt.as_ref().map(|o| o.n_patches).unwrap_or(0));
    w.comma();
    w.kv_num("phase_deg", opt.as_ref().map(|o| o.phase_deg).unwrap_or(0.0));
    w.comma();
    w.kv_usize("deg_min", opt.as_ref().map(|o| o.deg_min).unwrap_or(0));
    w.comma();
    w.kv_usize("deg_max", opt.as_ref().map(|o| o.deg_max).unwrap_or(0));
    w.comma();
    w.kv_num("overlap_train", opt.as_ref().map(|o| o.overlap_train).unwrap_or(0.0));
    w.comma();
    w.kv_num("overlap_use", opt.as_ref().map(|o| o.overlap_use).unwrap_or(0.0));
    w.comma();
    w.kv_num("deg_elbow_tol", opt.as_ref().map(|o| o.deg_elbow_tol).unwrap_or(0.0));
    w.comma();
    w.key("cleaner");
    w.raw(&format!(
        "{{\"mode\": \"auto\", \"auto\": {{\"method\": \"iqr\", \"baseline_deg\": {}, \"iqr_k\": {}}}}}",
        json::num(o.cleaner.baseline_deg),
        json::num(o.cleaner.iqr_k)
    ));
    w.comma();
    w.kv_bool("pits", o.pits);
    if o.pits {
        if let Some(m) = first {
            let ps = m.pit_shape();
            w.comma();
            w.kv_num("sigma_deg", ps.sigma_deg);
            w.comma();
            w.kv_num("pit_core_sigma", ps.core_sigma);
            w.comma();
            w.kv_num("pit_window_sigma", ps.window_sigma);
            w.comma();
            w.kv_num("pit_min_amp", ps.pit_min_amp);
            w.comma();
            w.kv_bool("tapering", ps.tapering);
        }
    }
    w.comma();
    w.key("detector");
    w.raw("null");
    w.obj_end();
    w.comma();

    w.key("sections");
    w.arr_start();
    for (i, s) in ordered.iter().enumerate() {
        let file = format!("sections/{:02}.pappa.json", i);
        save_section_document(&root.join(&file), s)?;
        if i > 0 {
            w.sb.push_str(",\n");
            w.sb.push_str(&w.ind());
        } else {
            w.sb.push('\n');
            w.sb.push_str(&w.ind());
        }
        w.obj_start();
        w.kv_usize("index", i);
        w.comma();
        w.kv_usize("section_id", s.section_id);
        w.comma();
        w.kv_num("height_mm", s.height_mm);
        w.comma();
        w.kv_str("file", &file);
        w.comma();
        w.kv_usize("n_points", s.n_points_total);
        w.comma();
        w.kv_usize("n_outliers", s.n_outliers);
        w.obj_end();
    }
    w.sb.push('\n');
    w.sb.push_str(&w.ind());
    w.arr_end();

    w.obj_end();
    let manifest = root.join("sample.json");
    fs::write(&manifest, format!("{}\n", w.sb))
        .map_err(|e| format!("не записать {manifest:?}: {e}"))?;
    Ok(root.to_string_lossy().to_string())
}
