# Тесты R-порта PAPPA: конформанс-векторы + дымовые проверки.
# Запуск: Rscript r/tests/runtests.R   (или powershell -File r/build_r.ps1 -Test)
#
# testthat НЕ используется намеренно: порт обязан работать на голом R без
# пакетов, поэтому проверки — свой минимальный харнесс (как в остальных портах,
# которые тоже обходятся без внешних тест-фреймворков).

script_dir <- function() {
  a <- commandArgs(trailingOnly = FALSE)
  m <- grep("^--file=", a, value = TRUE)
  if (length(m) == 0L) return(normalizePath("."))
  normalizePath(dirname(sub("^--file=", "", m[[1L]])))
}

SRC_DIR <- file.path(script_dir(), "..", "src")
VECTORS_DIR <- normalizePath(file.path(SRC_DIR, "..", "..", "spec", "conformance", "vectors"))
source(file.path(SRC_DIR, "pappa.R"))
Pappa$load(SRC_DIR)

passed <- 0L
failed <- 0L

check <- function(name, cond) {
  if (isTRUE(cond)) {
    passed <<- passed + 1L
    cat(sprintf("  OK   %s\n", name))
  } else {
    failed <<- failed + 1L
    cat(sprintf("  FAIL %s\n", name))
  }
}

count_fixed <- function(hay, needle) {
  hits <- gregexpr(needle, hay, fixed = TRUE)[[1L]]
  if (length(hits) == 1L && hits[1L] == -1L) 0L else length(hits)
}

cat("== конформанс-векторы ==\n")
vectors <- Pappa$Conformance$load_vectors(VECTORS_DIR)
check("векторов не меньше 4", length(vectors) >= 4L)
for (v in vectors) {
  r <- Pappa$Conformance$check_vector(v$data)
  check(sprintf("%s: %s", v$file, r$detail), r$ok)
  if (!r$ok) for (note in r$notes) cat(sprintf("       -> %s\n", note))
}

cat("== гладкая синусоида воспроизводится ==\n")
angles <- 0:359
radii <- 50 + 0.4 * sin(angles * pi / 180)
m <- Pappa$Model$new_model()
invisible(Pappa$Model$fit(m, angles, radii))
check("патчей 7", length(m$patches) == 7L)
curve <- Pappa$Model$eval_model(m, angles)
check("контур совпадает лучше 1e-6 мм", max(abs(curve - radii)) < 1e-6)

cat("== документ: формат и контракт pit_terms ==\n")
csv_path <- file.path(tempdir(), "smoke.csv")
lines <- c("section_id,height_mm,angle_deg,radius_mm",
           sprintf("0,7.5,%d,%.10f", 0:359, 40 + 0.2 * sin(0:359)))
writeLines(lines, csv_path, useBytes = TRUE)

rows <- Pappa$Csv$load_csv(csv_path)
# Четыре колонки: регрессия на off-by-one проверку числа полей (need — это
# НОМЕР последней колонки, поэтому условие отбраковки — length(f) < need).
check("из четырёхколоночного CSV прочитаны все 360 строк", rows$n == 360L)
sections <- Pappa$Csv$process_sections(rows, Pappa$Csv$pipeline_options(verbose = FALSE))
check("получено одно сечение", length(sections) == 1L)

out <- file.path(tempdir(), "smoke_sample")
invisible(Pappa$Document$save_sample(out, "smoke", sections,
                                     Pappa$Document$sample_options(input_csv = csv_path)))
manifest <- Pappa$Json$read_text(file.path(out, "sample.json"))
section <- Pappa$Json$read_text(file.path(out, "sections", "00.pappa.json"))
check("манифест: format pappa-sample", grepl("\"format\": \"pappa-sample\"", manifest, fixed = TRUE))
check("сечение: format pappa", grepl("\"format\": \"pappa\"", section, fixed = TRUE))
check("сечение: есть statistics", grepl("\"statistics\"", section, fixed = TRUE))
has_pits <- Pappa$Model$has_pits(sections[[1L]]$model)
check("pit_terms у каждого патча, когда модель с ямами (или ни у одного)",
      count_fixed(section, "\"pit_terms\"") == (if (has_pits) 7L else 0L))
check("sample.json разбирается обратно", is.list(Pappa$Json$json_parse(manifest)))
check("документ сечения разбирается обратно", is.list(Pappa$Json$json_parse(section)))
parsed_manifest <- Pappa$Json$json_parse(manifest)
check("JSON-null сохраняется как NULL (а не исчезает)",
      "detector" %in% names(parsed_manifest$config) && is.null(parsed_manifest$config$detector))
cat("== сигнальные утилиты (как numpy) ==\n")
S <- Pappa$Signal
check("median2 чётного n — среднее центральных", S$median2(c(1, 2, 3, 4)) == 2.5)
check("median2 нечётного n", S$median2(c(1, 2, 3)) == 2)
check("percentile 50 по [1..4] = 2.5", S$percentile_linear(1:4, 50) == 2.5)
check("percentile 0 = минимум, 100 = максимум",
      S$percentile_linear(1:4, 0) == 1 && S$percentile_linear(1:4, 100) == 4)
check("iqr [1..4] = 1.5", S$iqr2(1:4) == 1.5)
check("кольцевые расстояния", S$circ_dist(359, 1) == 2 && S$circ_local(1, 359) == 2 &&
      S$circ_dist(0, 180) == 180)
check("окно в точках: span 1° на шаге 1° = 3, span 10° = 11",
      S$window_points(0:359, 1) == 3L && S$window_points(0:359, 10) == 11L)
check("smoothstep на краях и в середине",
      S$smoothstep(-1) == 0 && S$smoothstep(2) == 1 && S$smoothstep(0.5) == 0.5)

cat("== линейная алгебра ==\n")
xs <- c(-2, -1, 0, 1, 2)
co <- Pappa$Linalg$polyfit(xs, 2 + 3 * xs, 1L)
# Как np.polyfit: коэффициенты по УБЫВАНИЮ степени, то есть [3, 2] для 2 + 3x.
check("polyfit прямой: коэффициенты [3, 2]",
      max(abs(co - c(3, 2))) < 1e-12)
check("polyval по убыванию степени: 2*10 + 3 = 23",
      abs(Pappa$Linalg$polyval(c(2, 3), 10) - 23) < 1e-12)
check("polyval == polyfit на исходных точках",
      max(abs(vapply(xs, function(x) Pappa$Linalg$polyval(co, x), numeric(1)) -
              (2 + 3 * xs))) < 1e-12)
check("cheb_sum == сумма по матрице Чебышёва",
      abs(Pappa$Linalg$cheb_sum(c(1, 2, 3, 4), 3L, 0.3) -
          sum(c(1, 2, 3, 4) * Pappa$Linalg$cheb_row(0.3, 3L))) < 1e-12)

cat("== JSON: запись и разбор ==\n")
J <- Pappa$Json
nums <- c(0.1, 24.75, -3.5, 1e-12, 15, 1e15)
check("json_num round-trip для шести чисел",
      all(vapply(nums, function(v) !is.na(suppressWarnings(as.numeric(J$json_num(v)))) &&
                   as.numeric(J$json_num(v)) == v, logical(1))))
check("json_num: нуль и целые без дробной части",
      J$json_num(0) == "0" && J$json_num(15) == "15" && J$json_num(24.75) == "24.75")
check("json_esc экранирует кавычку и перевод строки",
      identical(J$json_esc("a\"b\nc"), "a\\\"b\\nc"))
doc <- J$json_parse("{\"a\": [1, 2.5, true, null, \"x\\ny\"], \"b\": {\"c\": -0.5}}")
check("разбор вложенного объекта и массива",
      is.list(doc) && length(J$jarr(doc$a)) == 5L && J$jdbl(doc$b, "c") == -0.5 &&
      isTRUE(doc$a[[3L]]) && is.null(doc$a[[4L]]))
check("строка с экранированным переводом строки", identical(doc$a[[5L]], "x\ny"))
check("элемент массива читается как число", as.numeric(doc$a[[1L]]) == 1)

cat("== очистка и детектор: границы ==\n")
cl <- Pappa$Cleaner$clean_iqr(0:9, rep(40, 10),
                              Pappa$Cleaner$cleaner_options(baseline_deg = 10, iqr_k = 3))
check("меньше min_points — очистка отключается", cl$n_outliers == 0L && cl$window == 0L)
mask <- rep(FALSE, 360L)
mask[10:20] <- TRUE
zs <- Pappa$Detector$mask_to_zones(0:359, mask,
                                   Pappa$Detector$detector_options(min_zone_deg = 1))
check("зона по маске: +-полшага от крайних точек",
      length(zs) == 1L && abs(zs[[1L]]$lo - 8.5) < 1e-12 && abs(zs[[1L]]$hi - 19.5) < 1e-12)

cat(sprintf("\nИтог: %d OK, %d FAIL\n", passed, failed))
if (failed == 0L) {
  cat("ВЫВОД: R-порт проходит тесты\n")
  quit(save = "no", status = 0L)
}
cat("ВЫВОД: есть падения\n")
quit(save = "no", status = 1L)

