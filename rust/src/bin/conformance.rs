//! Проверка Rust-порта PAPPA по конформанс-векторам.
//! Запуск: cargo run --release --bin conformance [каталог с векторами]
//! Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.

use std::path::PathBuf;
use std::process::exit;

use pappa::conformance;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let dir = PathBuf::from(
        args.get(1)
            .cloned()
            .unwrap_or_else(|| "../spec/conformance/vectors".to_string()),
    );
    if !dir.is_dir() {
        println!("нет каталога векторов: {}", dir.display());
        exit(2);
    }
    let vectors = match conformance::load(&dir) {
        Ok(v) => v,
        Err(e) => {
            println!("{e}");
            exit(2);
        }
    };
    println!(
        "Rust-порт PAPPA: {} векторов (pappa {})",
        vectors.len(),
        pappa::PORT_VERSION
    );

    let mut bad = 0;
    for v in &vectors {
        let r = conformance::check(&v.data);
        if !r.ok {
            bad += 1;
        }
        println!(
            "{:<46} {:<5} {}",
            v.file,
            if r.ok { "OK" } else { "FAIL" },
            r.detail
        );
        for n in r.notes.iter().take(4) {
            println!("{}{}", " ".repeat(52), format_args!("-> {n}"));
        }
    }
    println!(
        "{}",
        if bad == 0 {
            "ВЫВОД: Rust-порт проходит все векторы".to_string()
        } else {
            format!("ВЫВОД: расхождений {bad}")
        }
    );
    exit(if bad == 0 { 0 } else { 1 });
}
