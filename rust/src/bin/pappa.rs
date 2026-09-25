//! Пайплайн PAPPA на Rust: CSV с сечениями -> папка образца.
//!
//! Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
//!   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
//!
//! Проверка: python python/studies/verify_port.py --cpp-dir <out-dir>
//!
//! Запуск: cargo run --release --bin pappa -- --input python/synthetic_data.csv \
//!         --out-dir samples/synthetic_sphere_rust --name synthetic_sphere

use std::process::exit;

use pappa::{csv, document};

fn usage() {
    println!(
        "PAPPA (Rust): --input FILE.csv --out-dir DIR [--name NAME] \
         [--description ТЕКСТ] [--no-pits] [--quiet]"
    );
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let (mut input, mut out_dir, mut name, mut description) =
        (String::new(), String::new(), "sample".to_string(), "PAPPA Rust port".to_string());
    let (mut pits, mut quiet) = (true, false);

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--input" => {
                i += 1;
                input = args.get(i).cloned().unwrap_or_default();
            }
            "--out-dir" => {
                i += 1;
                out_dir = args.get(i).cloned().unwrap_or_default();
            }
            "--name" => {
                i += 1;
                name = args.get(i).cloned().unwrap_or_default();
            }
            "--description" => {
                i += 1;
                description = args.get(i).cloned().unwrap_or_default();
            }
            "--no-pits" => pits = false,
            "--quiet" => quiet = true,
            _ => {
                usage();
                exit(2);
            }
        }
        i += 1;
    }
    if input.is_empty() || out_dir.is_empty() {
        usage();
        exit(2);
    }

    let rows = match csv::load(&input) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("Ошибка: {e}");
            exit(1);
        }
    };
    println!("PAPPA (Rust): {} точек, вход {}", rows.len(), input);

    let mut opt = csv::PipelineOptions::default();
    opt.pits = pits;
    opt.verbose = !quiet;
    let sections = csv::process_sections(&rows, &opt);

    let sample = document::SampleOptions {
        input_csv: input.clone(),
        pits,
        description,
        cleaner: opt.cleaner,
        detector: opt.detector,
    };
    match document::save_sample(&out_dir, &name, &sections, &sample) {
        Ok(root) => {
            println!("\nОбразец записан: {root}");
            println!("  манифест: {root}/sample.json");
            println!("  сечений:  {} (sections/*.pappa.json)", sections.len());
            println!("\nСверка с референсом Python:");
            println!("  python python/studies/verify_port.py --cpp-dir {root}");
        }
        Err(e) => {
            eprintln!("Ошибка: {e}");
            exit(1);
        }
    }
}
