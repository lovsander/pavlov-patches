# Загрузчик R-порта PAPPA.
#
# Модули повторяют структуру остальных портов (julia/src/*.jl и т.п.), но в R
# модулей нет, поэтому каждый модуль — это отдельное ОКРУЖЕНИЕ, лежащее в Pappa:
#     Pappa$Signal      Pappa$Linalg      Pappa$Cleaner    Pappa$Detector
#     Pappa$Model       Pappa$Json        Pappa$Csv        Pappa$Document
#     Pappa$Conformance
# Цепочка родителей окружений (`new.env(parent = ...)`) заменяет `using`/`import`:
# внутри `Pappa$Cleaner` видны имена `Pappa$Signal`, внутри `Pappa$Model` — имена
# `Pappa$Linalg` и `Pappa$Signal`. Обращения между модулями всё равно
# квалифицированные (`Signal$median2(...)`, `Model$fit(...)`) — как в Julia-порте.
#
# ВАЖНО (почему `evalq`): функция в R захватывает окружение, в котором СОЗДАНА.
# Присваивание `Pappa$Signal$f <- function(...)` на верхнем уровне дало бы
# замыкание в globalenv, и внутренние ссылки на `Signal$...` не разрешились бы.
# Поэтому тела модулей вычисляются через `evalq({...}, Pappa$Signal)`.
#
# Запуск: source("r/src/pappa.R"); Pappa$load("r/src")   (bin/*.R и tests/*.R
# делают это сами, вычисляя свой каталог из `--file=` в commandArgs()).
#
# Родитель Pappa — baseenv(): иначе цепочка окружений обрывается в emptyenv и
# внутри `evalq({...}, Pappa$Signal)` не находятся даже базовые `{`, `if`, `sum`.

Pappa <- new.env(parent = baseenv())

Pappa$PORT_VERSION <- "0.1.0"
Pappa$PORT_LANGUAGE <- "r"

Pappa$load <- function(src_dir) {
  for (f in c("signal.R", "linalg.R", "cleaner.R", "detector.R", "model.R",
              "json.R", "csv.R", "document.R", "conformance.R")) {
    source(file.path(src_dir, f), local = FALSE)
  }
  invisible(Pappa)
}
