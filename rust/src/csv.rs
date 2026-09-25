//! Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go).

use std::fs;
use std::time::Instant;

use crate::cleaner::{self, CleanerOptions};
use crate::detector::{self, DetectorOptions};
use crate::model::{Model, ModelOptions};

#[derive(Debug, Clone)]
pub struct Row {
    pub section_id: usize,
    pub height_mm: f64,
    pub angle_deg: f64,
    pub radius_mm: f64,
}

/// Сечение + обученная модель + метаданные для документа.
pub struct SectionModel {
    pub section_id: usize,
    pub height_mm: f64,
    pub model: Model,
    pub n_points_total: usize,
    pub n_outliers: usize,
    pub fit_time_ms: f64,
    pub description: String,
    pub pits: Vec<f64>,
    pub n_used: usize,
}

/// Параметры посекционного расчёта: значения по умолчанию — как в референсе.
pub struct PipelineOptions {
    pub model: ModelOptions,
    pub cleaner: CleanerOptions,
    pub detector: DetectorOptions,
    pub pits: bool,
    pub verbose: bool,
}

impl Default for PipelineOptions {
    fn default() -> Self {
        Self {
            model: ModelOptions::default(),
            cleaner: CleanerOptions::default(),
            detector: DetectorOptions::default(),
            pits: true,
            verbose: true,
        }
    }
}

/// Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок).
pub fn load(path: &str) -> Result<Vec<Row>, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("не читать CSV {path}: {e}"))?;
    let lines: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).collect();
    if lines.is_empty() {
        return Err(format!("пустой CSV: {path}"));
    }

    let head: Vec<&str> = lines[0].split(',').map(|s| s.trim()).collect();
    let col = |name: &str| head.iter().position(|h| *h == name);
    let (i_sec, i_h, i_a, i_r) = (
        col("section_id").ok_or_else(|| "в CSV нет колонки section_id".to_string())?,
        col("height_mm").ok_or_else(|| "в CSV нет колонки height_mm".to_string())?,
        col("angle_deg").ok_or_else(|| "в CSV нет колонки angle_deg".to_string())?,
        col("radius_mm").ok_or_else(|| "в CSV нет колонки radius_mm".to_string())?,
    );
    let need = i_sec.max(i_h).max(i_a).max(i_r);

    let mut rows = Vec::with_capacity(lines.len() - 1);
    for line in &lines[1..] {
        let f: Vec<&str> = line.split(',').collect();
        if f.len() <= need {
            continue;
        }
        let parse = |i: usize| -> Result<f64, String> {
            f[i].trim()
                .parse::<f64>()
                .map_err(|e| format!("{}: {e}", f[i]))
        };
        rows.push(Row {
            section_id: parse(i_sec)? as usize,
            height_mm: parse(i_h)?,
            angle_deg: parse(i_a)?,
            radius_mm: parse(i_r)?,
        });
    }
    if rows.is_empty() {
        return Err("в CSV нет строк с данными".to_string());
    }
    Ok(rows)
}

/// Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение.
pub fn process_sections(rows: &[Row], opt: &PipelineOptions) -> Vec<SectionModel> {
    let mut ids: Vec<usize> = rows.iter().map(|r| r.section_id).collect();
    ids.sort_unstable();
    ids.dedup();

    let mut out = Vec::with_capacity(ids.len());
    for sid in ids {
        let mut group: Vec<&Row> = rows.iter().filter(|r| r.section_id == sid).collect();
        group.sort_by(|a, b| a.angle_deg.total_cmp(&b.angle_deg));
        let n = group.len();
        let angles: Vec<f64> = group.iter().map(|r| r.angle_deg).collect();
        let radii: Vec<f64> = group.iter().map(|r| r.radius_mm).collect();

        let cl = cleaner::clean_iqr(&angles, &radii, opt.cleaner);
        let mut a_clean = Vec::with_capacity(n);
        let mut r_clean = Vec::with_capacity(n);
        for i in 0..n {
            if cl.mask[i] {
                continue;
            }
            a_clean.push(angles[i]);
            r_clean.push(radii[i]);
        }

        let pits = if opt.pits {
            detector::pits(&a_clean, &r_clean, opt.detector)
        } else {
            Vec::new()
        };
        let mut model = Model::new(opt.model.clone(), &pits);

        let t0 = Instant::now();
        model.fit(&a_clean, &r_clean);
        let fit_ms = t0.elapsed().as_secs_f64() * 1000.0;

        if opt.verbose {
            println!(
                "  секция {sid} (h={:.0} мм): точек {n}, выброшено {}, ям найдено {}, степени {:?}, обучение {:.1} мс",
                group[0].height_mm, cl.n_outliers, pits.len(), model.degrees(), fit_ms
            );
        }
        out.push(SectionModel {
            section_id: sid,
            height_mm: group[0].height_mm,
            model,
            n_points_total: n,
            n_outliers: cl.n_outliers,
            fit_time_ms: fit_ms,
            description: format!("сечение {sid}, h={:.0} мм", group[0].height_mm),
            pits,
            n_used: a_clean.len(),
        });
    }
    out
}
