# Pappa$Csv
#
# Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go).
#
# В R вместо массива структур — ЧЕТЫРЕ параллельных вектора (rows$section_id,
# rows$height_mm, rows$angle_deg, rows$radius_mm): на 60 000 строк это и быстрее,
# и идиоматичнее (векторизация вместо роста списка в цикле). Семантика та же.

Pappa$Csv <- new.env(parent = Pappa)

evalq({

  pipeline_options <- function(model = Model$model_options(),
                               cleaner = Cleaner$cleaner_options(),
                               detector = Detector$detector_options(),
                               pits = TRUE, verbose = TRUE) {
    list(model = model, cleaner = cleaner, detector = detector,
         pits = isTRUE(pits), verbose = isTRUE(verbose))
  }

  # Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок).
  load_csv <- function(path) {
    text <- Json$read_text(path)
    lines <- trimws(strsplit(text, "\n", fixed = TRUE)[[1]])
    lines <- lines[nzchar(lines)]
    if (length(lines) == 0L) stop("пустой CSV: ", path)

    split_comma <- function(s) trimws(strsplit(s, ",", fixed = TRUE)[[1]])
    head <- split_comma(lines[1L])
    col <- function(name) {
      i <- match(name, head)
      if (is.na(i)) stop("в CSV нет колонки ", name)
      i
    }
    i_sec <- col("section_id")
    i_h <- col("height_mm")
    i_a <- col("angle_deg")
    i_r <- col("radius_mm")
    need <- max(i_sec, i_h, i_a, i_r)

    fields <- lapply(lines[-1L], split_comma)
    fields <- Filter(function(f) length(f) >= need, fields)
    # length(f) >= need, а НЕ > need: в R/Julia индексация с 1, поэтому need —
    # это НОМЕР последней нужной колонки (4 для файла из четырёх колонок).
    if (length(fields) == 0L) stop("в CSV нет строк с данными")

    to_int <- function(s) {
      v <- suppressWarnings(as.integer(s))
      if (is.na(v)) stop("в CSV не целое число: ", s)
      v
    }
    to_num <- function(s) {
      v <- suppressWarnings(as.numeric(s))
      if (is.na(v)) stop("в CSV не число: ", s)
      v
    }
    rows <- list(
      n = length(fields),
      section_id = vapply(fields, function(f) to_int(f[i_sec]), integer(1), USE.NAMES = FALSE),
      height_mm = vapply(fields, function(f) to_num(f[i_h]), numeric(1), USE.NAMES = FALSE),
      angle_deg = vapply(fields, function(f) to_num(f[i_a]), numeric(1), USE.NAMES = FALSE),
      radius_mm = vapply(fields, function(f) to_num(f[i_r]), numeric(1), USE.NAMES = FALSE))
    class(rows) <- "PappaRows"
    rows
  }

  # Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение.
  process_sections <- function(rows, opt = pipeline_options()) {
    ids <- sort(unique(rows$section_id))
    out <- list()

    for (sid in ids) {
      idx <- which(rows$section_id == sid)
      idx <- idx[order(rows$angle_deg[idx])]
      n <- length(idx)
      angles <- rows$angle_deg[idx]
      radii <- rows$radius_mm[idx]

      cl <- Cleaner$clean_iqr(angles, radii, opt$cleaner)
      keep <- !cl$mask
      a_clean <- angles[keep]
      r_clean <- radii[keep]

      pits <- if (opt$pits) Detector$pits(a_clean, r_clean, opt$detector) else numeric(0)
      m <- Model$new_model(opt$model, pits)

      t0 <- proc.time()[["elapsed"]]
      Model$fit(m, a_clean, r_clean)
      fit_ms <- (proc.time()[["elapsed"]] - t0) * 1000

      h <- rows$height_mm[idx[1L]]
      if (opt$verbose) {
        cat(sprintf("  секция %d (h=%d мм): точек %d, выброшено %d, ям найдено %d, степени [%s], обучение %.1f мс\n",
                    sid, as.integer(round(h)), n, cl$n_outliers, length(pits),
                    paste(Model$degrees(m), collapse = ", "), fit_ms))
      }

      out[[length(out) + 1L]] <- list(
        section_id = sid, height_mm = h, model = m, n_points_total = n,
        n_outliers = cl$n_outliers, n_used = length(a_clean), fit_time_ms = fit_ms,
        description = sprintf("сечение %d, h=%d мм", sid, as.integer(round(h))),
        pits = pits)
    }
    out
  }

}, Pappa$Csv)
