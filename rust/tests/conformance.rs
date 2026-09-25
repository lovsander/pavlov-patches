//! Тесты: конформанс-векторы (как у C++/Go/JS/Java/Kotlin) + дымовой тест пайплайна.
//! Запуск: cargo test

use std::fs;
use std::path::PathBuf;

use pappa::{conformance, csv, document, model::Model};

fn vectors_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("spec")
        .join("conformance")
        .join("vectors")
}

#[test]
fn passes_all_vectors() {
    let vectors = conformance::load(&vectors_dir()).expect("каталог векторов");
    assert!(vectors.len() >= 4, "ожидались минимум 4 вектора");
    for v in &vectors {
        let r = conformance::check(&v.data);
        assert!(r.ok, "{}: {} {}", v.file, r.detail, r.notes.join("; "));
    }
}

#[test]
fn csv_smoke_and_smooth_curve() {
    let mut csv_text = String::from("section_id,height_mm,angle_deg,radius_mm\n");
    for i in 0..360 {
        let a = i as f64;
        csv_text.push_str(&format!(
            "0,0,{i},{:.6}\n",
            50.0 + 0.4 * (a * std::f64::consts::PI / 180.0).sin()
        ));
    }
    let tmp = std::env::temp_dir().join("pappa_rust_smoke.csv");
    fs::write(&tmp, &csv_text).expect("записать CSV");

    let rows = csv::load(tmp.to_str().unwrap()).expect("прочитать CSV");
    fs::remove_file(&tmp).ok();
    assert_eq!(rows.len(), 360);

    let angles: Vec<f64> = rows.iter().map(|r| r.angle_deg).collect();
    let radii: Vec<f64> = rows.iter().map(|r| r.radius_mm).collect();
    let mut m = Model::with_defaults();
    m.fit(&angles, &radii);
    assert_eq!(m.patches().len(), 7);

    let curve = m.eval(&angles);
    let mut max_err = 0.0_f64;
    for i in 0..radii.len() {
        max_err = max_err.max((curve[i] - radii[i]).abs());
    }
    assert!(max_err < 1e-6, "контур гладкой синусоиды: max|Δ| = {max_err:e}");
}

#[test]
fn document_round_trip_smoke() {
    let dir = std::env::temp_dir().join("pappa_rust_doc_smoke");
    let _ = fs::remove_dir_all(&dir);

    let mut csv_text = String::from("section_id,height_mm,angle_deg,radius_mm\n");
    for i in 0..360 {
        csv_text.push_str(&format!("0,7.5,{i},{:.6}\n", 40.0 + 0.2 * (i as f64).sin()));
    }
    let tmp = std::env::temp_dir().join("pappa_rust_doc_smoke.csv");
    fs::write(&tmp, &csv_text).expect("записать CSV");
    let rows = csv::load(tmp.to_str().unwrap()).expect("прочитать CSV");
    let sections = csv::process_sections(
        &rows,
        &csv::PipelineOptions {
            verbose: false,
            ..Default::default()
        },
    );

    let root = document::save_sample(
        dir.to_str().unwrap(),
        "smoke",
        &sections,
        &document::SampleOptions {
            input_csv: tmp.to_string_lossy().to_string(),
            ..Default::default()
        },
    )
    .expect("записать образец");

    let manifest = fs::read_to_string(PathBuf::from(&root).join("sample.json")).expect("манифест");
    assert!(manifest.contains("\"format\": \"pappa-sample\""));
    assert!(manifest.contains("\"sections\""));
    let section =
        fs::read_to_string(PathBuf::from(&root).join("sections/00.pappa.json")).expect("документ");
    assert!(section.contains("\"format\": \"pappa\""));
    assert!(section.contains("\"patches\""));
    assert!(section.contains("\"statistics\""));
    let has_pits = sections[0].model.has_pits();
    // Контракт: ключ pit_terms есть у КАЖДОГО патча (7 штук), когда модель с ямами,
    // и отсутствует, когда модель без ям. (На гладких данных детектор может дать
    // ложную зону — это то же поведение, что у референса: индикатор нормируется на
    // свою робастную sigma, а она у гладкого профиля ~0.)
    assert_eq!(
        section.matches("\"pit_terms\"").count(),
        if has_pits { 7 } else { 0 },
        "pit_terms: has_pits={has_pits}"
    );
    assert_eq!(section.matches("\"dx_deg\"").count() > 0, has_pits);

    fs::remove_file(&tmp).ok();
    fs::remove_dir_all(&dir).ok();
}
