# Проверка R-порта PAPPA по конформанс-векторам.
# Запуск: Rscript r/bin/conformance.R [каталог с векторами]
# Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.
#
# Каталог этого скрипта R выдаёт только через commandArgs() (`--file=`), потому
# что в Rscript нет аналога @__DIR__ из Julia-порта.

script_dir <- function() {
  a <- commandArgs(trailingOnly = FALSE)
  m <- grep("^--file=", a, value = TRUE)
  if (length(m) == 0L) return(normalizePath("."))
  normalizePath(dirname(sub("^--file=", "", m[[1L]])))
}

SRC_DIR <- file.path(script_dir(), "..", "src")
source(file.path(SRC_DIR, "pappa.R"))
Pappa$load(SRC_DIR)

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  dir <- if (length(args) >= 1L) args[[1L]] else
         file.path(SRC_DIR, "..", "..", "spec", "conformance", "vectors")

  vectors <- tryCatch(Pappa$Conformance$load_vectors(dir), error = function(e) {
    cat(sprintf("нет каталога векторов: %s (%s)\n", dir, conditionMessage(e)))
    NULL
  })
  if (is.null(vectors)) return(2L)

  cat(sprintf("R-порт PAPPA: %d векторов (pappa %s, R %s)\n", length(vectors),
              Pappa$PORT_VERSION, paste(R.version$major, R.version$minor, sep = ".")))

  bad <- 0L
  for (v in vectors) {
    r <- Pappa$Conformance$check_vector(v$data)
    if (!r$ok) bad <- bad + 1L
    cat(sprintf("%-46s %s %s\n", v$file, if (r$ok) "OK  " else "FAIL", r$detail))
    for (note in utils::head(r$notes, 4L)) cat(sprintf("%52s-> %s\n", "", note))
  }
  if (bad == 0L) {
    cat("ВЫВОД: R-порт проходит все векторы\n")
    0L
  } else {
    cat(sprintf("ВЫВОД: расхождений %d\n", bad))
    1L
  }
}

quit(save = "no", status = main())
