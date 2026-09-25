//! PAPPA (Piecewise Adaptive Poly-Patch Approximation) на Rust.
//!
//! Полный порт референса Python: ядро метода (патчи с адаптивной степенью и
//! нормированной координатой, smoothstep-смешивание = partition of unity, фичер
//! оконных гауссовых ям), детектор трещин (band), авто-очистка выбросов (iqr) и
//! пайплайн CSV -> папка образца в том же формате, что у Python/C++/C/Go/JS/Java/Kotlin.
//!
//! Зависимостей нет: JSON и CSV разбираются своими силами, поэтому `cargo build`
//! работает без сети.

pub mod cleaner;
pub mod conformance;
pub mod csv;
pub mod detector;
pub mod document;
pub mod json;
pub mod linalg;
pub mod model;
pub mod signal;

/// Версия порта (попадает в документ как `software.pappa_version`).
pub const PORT_VERSION: &str = "0.1.0";

/// Язык порта (попадает в документ как `software.language`).
pub const PORT_LANGUAGE: &str = "rust";
