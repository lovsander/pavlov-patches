# Pappa$Document
#
# Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin/
# Rust/Pascal/Swift/Julia:
#     <out_dir>/sample.json              манифест (format pappa-sample v1.0)
#     <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
# Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
# сравниваются численно (python/studies/verify_port.py).

Pappa$Document <- new.env(parent = Pappa)

# Константы версии/языка кладём в окружение модуля снаружи evalq: ВНУТРИ evalq
# имя `Pappa` не видно (цепочка окружений заканчивается в baseenv, а не в
# globalenv, где живёт сама `Pappa`), поэтому модули обращаются друг к другу по
# коротким именам (`Model$has_pits`, `Json$json_parse`) — они находятся в Pappa.
Pappa$Document$PORT_VERSION <- Pappa$PORT_VERSION
Pappa$Document$PORT_LANGUAGE <- Pappa$PORT_LANGUAGE

evalq({

  sample_options <- function(input_csv = "", pits = TRUE,
                             description = "PAPPA R port",
                             cleaner = Cleaner$cleaner_options(),
                             detector = Detector$detector_options()) {
    list(input_csv = input_csv, pits = isTRUE(pits), description = description,
         cleaner = cleaner, detector = detector)
  }

  # Календарная дата из числа дней с 1970-01-01 (алгоритм Говарда Хиннанта).
  civil_from_days <- function(z0) {
    z <- z0 + 719468
    era <- if (z >= 0) z %/% 146097 else (z - 146096) %/% 146097
    doe <- z - era * 146097
    yoe <- (doe - doe %/% 1460 + doe %/% 36524 - doe %/% 146096) %/% 365
    y <- yoe + era * 400
    doy <- doe - (365 * yoe + yoe %/% 4 - yoe %/% 100)
    mp <- (5 * doy + 2) %/% 153
    d <- doy - (153 * mp + 2) %/% 5 + 1
    m <- if (mp < 10) mp + 3 else mp - 9
    c(y = if (m <= 2) y + 1 else y, m = m, d = d)
  }

  iso_utc_now <- function() {
    secs <- floor(as.numeric(Sys.time()))
    days <- secs %/% 86400
    rem <- secs - days * 86400
    ymd <- civil_from_days(days)
    sprintf("%04d-%02d-%02dT%02d:%02d:%02dZ", ymd[["y"]], ymd[["m"]], ymd[["d"]],
            rem %/% 3600, (rem %% 3600) %/% 60, rem %% 60)
  }

  # ---------- плоский писатель JSON: отступ 2 пробела, как JsonWriter в C++ ----------
  # Строка в R неизменяема, поэтому копим куски в векторе внутри окружения —
  # тогда мутация видна из вложенных вызовов (в R это передача по ссылке).

  writer <- function() {
    w <- new.env(parent = emptyenv())
    w$out <- character(0)
    w$depth <- 0L
    w
  }

  w_raw <- function(w, s) {
    w$out <- c(w$out, s)
    invisible(NULL)
  }

  w_ind <- function(w) strrep(" ", max(0L, w$depth) * 2L)
  obj_start <- function(w) {
    w_raw(w, "{")
    w$depth <- w$depth + 1L
    w_raw(w, paste0("\n", w_ind(w)))
  }
  obj_end <- function(w) {
    w$depth <- w$depth - 1L
    w_raw(w, paste0("\n", w_ind(w), "}"))
  }
  arr_start <- function(w) {
    w_raw(w, "[")
    w$depth <- w$depth + 1L
    w_raw(w, paste0("\n", w_ind(w)))
  }
  arr_end <- function(w) {
    w$depth <- w$depth - 1L
    w_raw(w, paste0("\n", w_ind(w), "]"))
  }
  comma <- function(w) w_raw(w, paste0(",\n", w_ind(w)))
  key <- function(w, k) w_raw(w, paste0(w_ind(w), "\"", k, "\": "))
  str_val <- function(w, v) w_raw(w, paste0("\"", Json$json_esc(v), "\""))
  num_val <- function(w, v) w_raw(w, Json$json_num(v))
  bool_val <- function(w, v) w_raw(w, if (isTRUE(v)) "true" else "false")

  # Тип значения выбирает запись (аналог диспетчеризации kv в Julia-порте).
  kv <- function(w, k, v) {
    key(w, k)
    if (is.character(v)) str_val(w, v)
    else if (is.logical(v)) bool_val(w, v)
    else num_val(w, v)
  }

  text_of <- function(w) paste0(w$out, collapse = "")

  write_patches <- function(w, m) {
    key(w, "patches")
    arr_start(w)
    for (i in seq_along(m$patches)) {
      p <- m$patches[[i]]
      w_raw(w, if (i > 1L) paste0(",\n", w_ind(w)) else paste0("\n", w_ind(w)))
      obj_start(w)
      kv(w, "center_deg", p$center_deg);  comma(w)
      kv(w, "degree", p$degree);          comma(w)
      kv(w, "n_points", p$n_points);      comma(w)
      key(w, "coefs")
      arr_start(w)
      for (j in seq_along(p$coefs)) {
        if (j > 1L) w_raw(w, ", ")
        num_val(w, p$coefs[j])
      }
      arr_end(w)
      comma(w)

      key(w, "metrics")
      obj_start(w)
      kv(w, "amplitude_mm", p$metrics$amplitude_mm);          comma(w)
      kv(w, "mean_radius_mm", p$metrics$mean_radius_mm);      comma(w)
      kv(w, "amplitude_norm", p$metrics$amplitude_norm);      comma(w)
      kv(w, "deg_elbow_tol", p$metrics$deg_elbow_tol);        comma(w)
      kv(w, "rmse_selected_mm", p$metrics$rmse_selected_mm);  comma(w)
      kv(w, "rmse_best_mm", p$metrics$rmse_best_mm);          comma(w)
      kv(w, "n_train_points", p$metrics$n_train_points)
      obj_end(w)
      comma(w)

      key(w, "stats")
      obj_start(w)
      kv(w, "rmse_mm", p$stats$rmse_mm);        comma(w)
      kv(w, "mae_mm", p$stats$mae_mm);          comma(w)
      kv(w, "max_err_mm", p$stats$max_err_mm);  comma(w)
      kv(w, "correlation", p$stats$correlation)
      obj_end(w)

      # Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
      # (включая пустой список): так ждёт загрузчик Python.
      if (Model$has_pits(m)) {
        comma(w)
        key(w, "pit_terms")
        arr_start(w)
        for (j in seq_along(p$pit_offsets_deg)) {
          if (j > 1L) w_raw(w, ", ")
          obj_start(w)
          kv(w, "dx_deg", p$pit_offsets_deg[j]); comma(w)
          kv(w, "amp", p$pit_coefs[j])
          obj_end(w)
        }
        arr_end(w)
      }
      obj_end(w)
    }
    if (length(m$patches) > 0L) w_raw(w, paste0("\n", w_ind(w)))
    arr_end(w)
  }

  save_section_document <- function(path, section) {
    m <- section$model
    if (!isTRUE(m$is_fitted)) stop("save_section_document: модель не обучена")
    w <- writer()
    obj_start(w)
    kv(w, "format", "pappa");   comma(w)
    kv(w, "version", "2.0");    comma(w)
    kv(w, "method", if (Model$has_pits(m)) "PitPatchApproximator" else "PatchApproximator")
    comma(w)
    kv(w, "created", iso_utc_now());  comma(w)

    key(w, "software")
    obj_start(w)
    kv(w, "language", PORT_LANGUAGE);   comma(w)
    kv(w, "pappa_version", PORT_VERSION)
    obj_end(w)
    comma(w)

    key(w, "meta")
    obj_start(w)
    kv(w, "section_id", section$section_id);   comma(w)
    kv(w, "height_mm", section$height_mm);     comma(w)
    kv(w, "source", "csv");                    comma(w)
    kv(w, "description", section$description)
    obj_end(w)
    comma(w)

    key(w, "global")
    obj_start(w)
    key(w, "units")
    obj_start(w)
    kv(w, "angle", "degree");  comma(w)
    kv(w, "length", "mm")
    obj_end(w)
    comma(w)

    opt <- m$options
    kv(w, "n_patches", opt$n_patches);                  comma(w)
    kv(w, "half_sector_deg", m$half_sector);            comma(w)
    kv(w, "phase_deg", opt$phase_deg);                  comma(w)
    kv(w, "half_train_deg", Model$half_train(m)); comma(w)
    kv(w, "half_use_deg", Model$half_use(m));     comma(w)
    kv(w, "overlap_train_deg", opt$overlap_train);      comma(w)
    kv(w, "overlap_use_deg", opt$overlap_use);          comma(w)
    kv(w, "deg_min", opt$deg_min);                      comma(w)
    kv(w, "deg_max", opt$deg_max);                      comma(w)
    kv(w, "coord_mode", opt$coord_mode);                comma(w)
    kv(w, "deg_elbow_tol", opt$deg_elbow_tol);          comma(w)
    kv(w, "amplitude_scale", opt$amplitude_scale)

    if (Model$has_pits(m)) {
      ps <- m$pit_shape
      comma(w)
      key(w, "pit")
      obj_start(w)
      kv(w, "sigma_deg", ps$sigma_deg);          comma(w)
      kv(w, "core_sigma", ps$core_sigma);        comma(w)
      kv(w, "window_sigma", ps$window_sigma);    comma(w)
      kv(w, "pit_min_amp", ps$pit_min_amp);      comma(w)
      kv(w, "tapering", ps$tapering);            comma(w)
      key(w, "centers_deg")
      arr_start(w)
      for (i in seq_along(m$pits)) {
        if (i > 1L) w_raw(w, ", ")
        num_val(w, m$pits[i])
      }
      arr_end(w)
      obj_end(w)
    }
    obj_end(w)
    comma(w)

    write_patches(w, m)
    comma(w)

    key(w, "statistics")
    obj_start(w)
    kv(w, "n_points_total", section$n_points_total);    comma(w)
    kv(w, "n_outliers_removed", section$n_outliers);    comma(w)
    kv(w, "fit_time_ms", section$fit_time_ms)
    obj_end(w)

    obj_end(w)
    Json$write_text(path, paste0(text_of(w), "\n"))
    path
  }

  save_sample <- function(out_dir, name, sections, o = sample_options()) {
    dir.create(file.path(out_dir, "sections"), recursive = TRUE, showWarnings = FALSE)
    if (length(sections) > 0L) {
      sections <- sections[order(vapply(sections, function(s) as.integer(s$section_id),
                                        integer(1), USE.NAMES = FALSE))]
    }
    fm <- if (length(sections) == 0L) NULL else sections[[1L]]$model
    gopt <- function(field, def) if (is.null(fm)) def else fm$options[[field]]

    w <- writer()
    obj_start(w)
    kv(w, "format", "pappa-sample");  comma(w)
    kv(w, "version", "1.0");          comma(w)
    kv(w, "name", name);              comma(w)
    kv(w, "created", iso_utc_now());  comma(w)

    key(w, "units")
    obj_start(w)
    kv(w, "angle", "degree");  comma(w)
    kv(w, "length", "mm")
    obj_end(w)
    comma(w)

    key(w, "meta")
    obj_start(w)
    kv(w, "description", o$description)
    obj_end(w)
    comma(w)

    if (nzchar(o$input_csv)) {
      key(w, "input")
      obj_start(w)
      kv(w, "csv", o$input_csv)
      obj_end(w)
      comma(w)
    }

    key(w, "config")
    obj_start(w)
    kv(w, "n_patches", gopt("n_patches", 0L));          comma(w)
    kv(w, "phase_deg", gopt("phase_deg", 0));           comma(w)
    kv(w, "deg_min", gopt("deg_min", 0L));              comma(w)
    kv(w, "deg_max", gopt("deg_max", 0L));              comma(w)
    kv(w, "overlap_train", gopt("overlap_train", 0));   comma(w)
    kv(w, "overlap_use", gopt("overlap_use", 0));       comma(w)
    kv(w, "deg_elbow_tol", gopt("deg_elbow_tol", 0));   comma(w)
    key(w, "cleaner")
    w_raw(w, paste0("{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", \"baseline_deg\": ",
                    Json$json_num(o$cleaner$baseline_deg), ", \"iqr_k\": ",
                    Json$json_num(o$cleaner$iqr_k), "}}"))
    comma(w)
    kv(w, "pits", o$pits)
    if (o$pits && !is.null(fm)) {
      ps <- fm$pit_shape
      comma(w)
      kv(w, "sigma_deg", ps$sigma_deg);             comma(w)
      kv(w, "pit_core_sigma", ps$core_sigma);       comma(w)
      kv(w, "pit_window_sigma", ps$window_sigma);   comma(w)
      kv(w, "pit_min_amp", ps$pit_min_amp);         comma(w)
      kv(w, "tapering", ps$tapering)
    }
    comma(w)
    key(w, "detector")
    w_raw(w, "null")
    obj_end(w)
    comma(w)

    key(w, "sections")
    arr_start(w)
    for (i in seq_along(sections)) {
      s <- sections[[i]]
      file <- paste0("sections/", sprintf("%02d", i - 1L), ".pappa.json")
      save_section_document(file.path(out_dir, file), s)
      w_raw(w, if (i > 1L) paste0(",\n", w_ind(w)) else paste0("\n", w_ind(w)))
      obj_start(w)
      kv(w, "index", as.integer(i - 1L));     comma(w)
      kv(w, "section_id", s$section_id);      comma(w)
      kv(w, "height_mm", s$height_mm);        comma(w)
      kv(w, "file", file);                    comma(w)
      kv(w, "n_points", s$n_points_total);    comma(w)
      kv(w, "n_outliers", s$n_outliers)
      obj_end(w)
    }
    if (length(sections) > 0L) w_raw(w, paste0("\n", w_ind(w)))
    arr_end(w)

    obj_end(w)
    Json$write_text(file.path(out_dir, "sample.json"), paste0(text_of(w), "\n"))
    out_dir
  }

}, Pappa$Document)


