# Pappa$Conformance
#
# Проверка порта по конформанс-векторам (spec/conformance/vectors).
# Допуски — те же, что у C++/Go/C/JS/Java/Kotlin/Rust/Pascal/Swift/Julia:
# контур 1e-6 мм, коэффициенты max(1e-8, 1e-9·|c|), детектор 1e-6°,
# очистка — доля точек (frac).

Pappa$Conformance <- new.env(parent = Pappa)

evalq({

  load_vectors <- function(dir) {
    if (!dir.exists(dir)) stop("нет каталога векторов: ", dir)
    files <- sort(list.files(dir, pattern = "\\.json$", full.names = FALSE))
    if (length(files) == 0L) stop("нет каталога векторов: ", dir)
    lapply(files, function(f) {
      list(file = f, data = Json$json_parse(Json$read_text(file.path(dir, f))))
    })
  }

  outcome <- function(ok, detail, notes = character(0)) {
    list(ok = isTRUE(ok), detail = detail, notes = notes)
  }

  near <- function(a, b, rel, flr) abs(a - b) <= max(flr, rel * abs(b))

  sig2 <- function(x) if (x == 0) "0" else format(x, digits = 2, scientific = TRUE)

  check_vector <- function(v) {
    kind <- Json$jtext(v, "kind")
    if (kind == "model") return(check_model(v))
    if (kind == "detector") return(check_detector(v))
    check_cleaner(v)
  }

  check_detector <- function(v) {
    J <- Json
    cfg <- J$jget(v, "config")
    exp <- J$jget(v, "expected")
    input <- J$jget(v, "input")
    angles <- J$jdoubles(input, "angles_deg")
    radii <- J$jdoubles(input, "radii_mm")
    o <- Detector$detector_options(
      window_deg = J$jdbl(cfg, "window_deg"), wide_deg = J$jdbl(cfg, "wide_deg"),
      smooth_deg = J$jdbl(cfg, "smooth_deg"), k = J$jdbl(cfg, "k"),
      min_zone_deg = J$jdbl(cfg, "min_zone_deg"))

    band <- Detector$band_indicator(angles, radii, o)
    zs <- Detector$zones(angles, band, o)
    exp_zones <- J$jarr(J$jget(exp, "zones_deg"))
    exp_pits <- J$jdoubles(exp, "pits_deg")
    notes <- character(0)

    ok <- length(zs) == length(exp_zones)
    if (!ok) notes <- c(notes, sprintf("зон %d != %d", length(zs), length(exp_zones)))
    dev <- 0
    for (i in seq_along(exp_zones)) {
      if (i > length(zs)) break
      e <- as.numeric(J$jarr(exp_zones[[i]]))
      dev <- max(dev, abs(zs[[i]]$lo - e[1L]), abs(zs[[i]]$hi - e[2L]))
    }
    if (length(zs) != length(exp_pits)) {
      ok <- FALSE
      notes <- c(notes, sprintf("ям %d != %d", length(zs), length(exp_pits)))
    }
    for (i in seq_along(exp_pits)) {
      if (i > length(zs)) break
      d <- abs(Detector$zone_center(zs[[i]]) - exp_pits[i])
      dev <- max(dev, d)
      if (d > 1e-6) ok <- FALSE
    }
    outcome(ok, sprintf("зон %d/%d, ям %d/%d, max|Δ| %s°", length(zs), length(exp_zones),
                        length(zs), length(exp_pits), sig2(dev)), notes)
  }

  check_cleaner <- function(v) {
    J <- Json
    cfg <- J$jget(v, "config")
    exp <- J$jget(v, "expected")
    input <- J$jget(v, "input")
    tol <- J$jget(v, "tolerance")
    angles <- J$jdoubles(input, "angles_deg")
    radii <- J$jdoubles(input, "radii_mm")
    o <- Cleaner$cleaner_options(baseline_deg = J$jdbl(cfg, "baseline_deg"),
                                       iqr_k = J$jdbl(cfg, "iqr_k"))
    r <- Cleaner$clean_iqr(angles, radii, o)

    n <- length(radii)
    ref <- logical(n)
    for (i in J$jints(exp, "mask_true_indices")) {          # индексы 0-based
      if (i + 1L >= 1L && i + 1L <= n) ref[i + 1L] <- TRUE
    }
    got <- sum(r$mask)
    extra <- sum(r$mask & !ref)
    missing <- sum(!r$mask & ref)
    tol_n <- max(1, floor(J$jdbl(tol, "frac") * n))
    want <- J$jint(exp, "n_outliers")
    ok <- extra <= tol_n && missing <= tol_n && abs(got - want) <= tol_n
    outcome(ok, sprintf("выбросов %d (эталон %d), лишних %d, пропущено %d",
                        got, want, extra, missing))
  }

  check_model <- function(v) {
    J <- Json
    cfg <- J$jget(v, "config")
    exp <- J$jget(v, "expected")
    tol <- J$jget(v, "tolerance")
    input <- J$jget(v, "input")
    notes <- character(0)
    ok <- TRUE

    opt <- Model$model_options(
      n_patches = J$jint(cfg, "n_patches"), phase_deg = J$jdbl(cfg, "phase_deg"),
      deg_min = J$jint(cfg, "deg_min"), deg_max = J$jint(cfg, "deg_max"),
      overlap_train = J$jdbl(cfg, "overlap_train"),
      overlap_use = J$jdbl(cfg, "overlap_use"),
      deg_elbow_tol = J$jdbl(cfg, "deg_elbow_tol"),
      amplitude_scale = J$jdbl_or(cfg, "amplitude_scale", 180),
      coord_mode = J$jtext(cfg, "coord_mode"))
    pits_deg <- J$jdoubles(cfg, "pits_deg")
    m <- Model$new_model(opt, pits_deg)
    if (length(pits_deg) > 0L) {
      m$pit_shape$sigma_deg <- J$jdbl(cfg, "sigma_deg")
      m$pit_shape$core_sigma <- J$jdbl(cfg, "pit_core_sigma")
      m$pit_shape$window_sigma <- J$jdbl(cfg, "pit_window_sigma")
      m$pit_shape$pit_min_amp <- J$jdbl(cfg, "pit_min_amp")
      m$pit_shape$tapering <- J$jbool_or(cfg, "tapering", TRUE)
    }
    Model$fit(m, J$jdoubles(input, "angles_deg"), J$jdoubles(input, "radii_mm"))

    want_deg <- J$jints(exp, "degrees")
    got_deg <- Model$degrees(m)
    deg_ok <- identical(want_deg, got_deg)
    if (!deg_ok) {
      ok <- FALSE
      notes <- c(notes, sprintf("степени [%s] != [%s]", paste(got_deg, collapse = ", "),
                                paste(want_deg, collapse = ", ")))
    }

    rel <- J$jdbl(tol, "coefs_rel")
    flr <- J$jdbl(tol, "coefs_abs_floor")
    max_c <- 0
    bad_c <- 0L
    coefs_nodes <- J$jarr(J$jget(exp, "coefs"))
    for (i in seq_along(coefs_nodes)) {
      ref <- as.numeric(J$jarr(coefs_nodes[[i]]))
      got <- if (i <= length(m$patches)) m$patches[[i]]$coefs else numeric(0)
      if (length(got) != length(ref)) {
        ok <- FALSE
        bad_c <- bad_c + 1L
        next
      }
      for (j in seq_along(ref)) {
        max_c <- max(max_c, abs(got[j] - ref[j]))
        if (!near(got[j], ref[j], rel, flr)) {
          ok <- FALSE
          bad_c <- bad_c + 1L
        }
      }
    }

    max_pit <- 0
    bad_pit <- 0L
    for (i in seq_along(J$jarr(J$jget(exp, "pit_terms")))) {
      node <- J$jarr(J$jget(exp, "pit_terms"))[[i]]
      ref_dx <- J$jdoubles(node, "dx_deg")
      ref_amp <- J$jdoubles(node, "amp")
      got_dx <- if (i <= length(m$patches)) m$patches[[i]]$pit_offsets_deg else numeric(0)
      got_amp <- if (i <= length(m$patches)) m$patches[[i]]$pit_coefs else numeric(0)
      if (length(got_dx) != length(ref_dx)) {
        ok <- FALSE
        bad_pit <- bad_pit + 1L
        next
      }
      for (j in seq_along(ref_dx)) {
        da <- abs(got_dx[j] - ref_dx[j])
        max_pit <- max(max_pit, da, abs(got_amp[j] - ref_amp[j]))
        if (da > 1e-9 || !near(got_amp[j], ref_amp[j], rel, flr)) {
          ok <- FALSE
          bad_pit <- bad_pit + 1L
        }
      }
    }

    curve <- J$jget(exp, "curve")
    ca <- J$jdoubles(curve, "angles_deg")
    cr <- J$jdoubles(curve, "radii_mm")
    got <- Model$eval_model(m, ca)
    max_r <- max(abs(got - cr))
    if (max_r > J$jdbl(tol, "curve_mm")) ok <- FALSE

    detail <- sprintf("степени %s, коэфф. max|Δ| %s (плохих %d), термины ям max|Δ| %s (плохих %d), контур max|Δ| %s мм",
                      if (deg_ok) "совпали" else "РАСХОДЯТСЯ", sig2(max_c), bad_c,
                      sig2(max_pit), bad_pit, sig2(max_r))
    outcome(ok, detail, notes)
  }

}, Pappa$Conformance)

