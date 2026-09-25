# Pappa$Model
#
# Модель PAPPA на R: патчи с адаптивной степенью по нормированной координате,
# smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
# Совпадает с референсом Python и остальными портами: тот же базис, та же
# политика степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней —
# ОДНОЙ матрицей Грама в базисе Чебышёва + RMSE по явным остаткам.
#
# Модель — окружение (в R это единственный способ мутировать объект по ссылке,
# как `mutable struct Model` в Julia): Model$new_model() -> m, Model$fit(m, ...).

Pappa$Model <- new.env(parent = Pappa$Linalg)   # цепочка Linalg -> Signal -> Pappa

evalq({

  model_options <- function(n_patches = 7L, phase_deg = 24.75, deg_min = 4L,
                            deg_max = 14L, overlap_train = 15.0, overlap_use = 5.0,
                            deg_elbow_tol = 0.05, amplitude_scale = 180.0,
                            coord_mode = "normalized") {
    list(n_patches = as.integer(n_patches), phase_deg = phase_deg,
         deg_min = as.integer(deg_min), deg_max = as.integer(deg_max),
         overlap_train = overlap_train, overlap_use = overlap_use,
         deg_elbow_tol = deg_elbow_tol, amplitude_scale = amplitude_scale,
         coord_mode = coord_mode)
  }

  pit_shape <- function(sigma_deg = 3.0, core_sigma = 2.0, window_sigma = 3.2,
                        pit_min_amp = 3e-3, tapering = TRUE) {
    list(sigma_deg = sigma_deg, core_sigma = core_sigma,
         window_sigma = window_sigma, pit_min_amp = pit_min_amp, tapering = tapering)
  }

  new_model <- function(options = model_options(), pits_deg = numeric(0)) {
    m <- new.env(parent = emptyenv())
    class(m) <- "PappaModel"
    m$options <- options
    m$pit_shape <- pit_shape()
    m$pits <- as.numeric(pits_deg) %% 360
    m$patches <- list()
    m$half_sector <- 0
    m$is_fitted <- FALSE
    m
  }

  has_pits <- function(m) length(m$pits) > 0L
  half_train <- function(m) m$half_sector + m$options$overlap_train
  half_use <- function(m) m$half_sector + m$options$overlap_use
  degrees <- function(m) {
    vapply(m$patches, function(p) as.integer(p$degree), integer(1))
  }

  # Оконный гаусс как функция расстояния от центра ямы.
  pit_shape_deg <- function(m, d_deg) {
    d <- abs(d_deg)
    sigma <- m$pit_shape$sigma_deg
    base <- exp(-(d * d) / (2 * sigma * sigma))
    if (!isTRUE(m$pit_shape$tapering)) return(base)
    core <- m$pit_shape$core_sigma * sigma
    edge <- m$pit_shape$window_sigma * sigma
    if (edge <= core) return(base)
    t <- min(max((edge - d) / (edge - core), 0), 1)
    base * t * t * (3 - 2 * t)
  }

  # Смещения видимых ям в локальной системе патча (°).
  pit_offsets <- function(m, center_deg, half_win_deg) {
    if (length(m$pits) == 0L) return(numeric(0))
    dx <- vapply(m$pits, function(p) circ_local(p, center_deg), numeric(1))
    dx[abs(dx) <= half_win_deg]
  }

  weight <- function(m, d_deg, half_use_deg) {
    if (d_deg <= m$half_sector) return(1)
    if (d_deg <= half_use_deg) {
      return(smoothstep(1 - (d_deg - m$half_sector) / (half_use_deg - m$half_sector)))
    }
    0
  }

  # Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
  # не хуже лучшей более чем на deg_elbow_tol. Возвращает list(степень, RMSE
  # выбранной, лучшая RMSE).
  estimate_degree <- function(m, xs, ys) {
    n <- length(xs)
    if (n < 5L) return(list(m$options$deg_min, 0, 0))

    xs <- as.numeric(xs)
    ys <- as.numeric(ys)
    degs <- integer(0)
    rmses <- numeric(0)
    best_deg <- m$options$deg_min
    best <- Inf

    if (m$options$coord_mode == "raw") {
      # Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
      for (deg in seq(m$options$deg_min, m$options$deg_max, by = 2L)) {
        a <- matrix(0, n, deg + 1L)
        for (pw in 0:deg) a[, deg + 1L - pw] <- xs^pw
        co <- lstsq_qr(a, ys)
        r <- sqrt(sum((as.numeric(a %*% co) - ys)^2) / n)
        degs <- c(degs, deg); rmses <- c(rmses, r)
        if (r < best) { best <- r; best_deg <- deg }
      }
    } else {
      dmax <- m$options$deg_max
      yref <- sum(ys) / n
      tt <- cheb_matrix(xs, dmax)
      yc <- ys - yref
      gram <- crossprod(tt)
      rhs <- as.numeric(crossprod(tt, yc))
      for (deg in seq(m$options$deg_min, dmax, by = 2L)) {
        nn <- deg + 1L
        co <- lstsq_qr(gram[1:nn, 1:nn, drop = FALSE], rhs[1:nn])
        r <- sqrt(sum((as.numeric(tt[, 1:nn, drop = FALSE] %*% co) - yc)^2) / n)
        degs <- c(degs, deg); rmses <- c(rmses, r)
        if (r < best) { best <- r; best_deg <- deg }
      }
    }

    limit <- best * (1 + m$options$deg_elbow_tol)
    sel <- best_deg
    rmse_sel <- best
    for (k in seq_along(degs)) {
      if (rmses[k] <= limit) {
        sel <- degs[k]
        rmse_sel <- rmses[k]
        break
      }
    }
    list(sel, rmse_sel, best)
  }

  # Точки обучающего окна патча (локальная координата: нормированная или сырая).
  # Порядок обхода — как в Julia-порте: сдвиги -360, 0, +360, внутри — по углам.
  window_of <- function(m, angles, radii, center) {
    half <- half_train(m)
    norm <- m$options$coord_mode != "raw"
    ang <- as.numeric(angles)
    rad <- as.numeric(radii)
    dxs <- numeric(0)
    ys <- numeric(0)
    for (shift in c(-360, 0, 360)) {
      dx <- ang + shift - center
      keep <- which(dx >= -half & dx <= half)
      if (length(keep) > 0L) {
        dxs <- c(dxs, dx[keep])
        ys <- c(ys, rad[keep])
      }
    }
    list(xs = if (norm) dxs / half else dxs, ys = ys)
  }

  fit <- function(m, angles, radii) {
    if (length(angles) != length(radii)) stop("fit: длины не совпадают")
    if (length(angles) < 10L) stop("fit: слишком мало точек")

    sector <- 360 / m$options$n_patches
    m$half_sector <- sector / 2
    centers <- (seq_len(m$options$n_patches) - 1L) * sector + m$half_sector +
               m$options$phase_deg
    centers <- centers %% 360
    ht <- half_train(m)
    m$patches <- list()

    for (c0 in centers) {
      w <- window_of(m, angles, radii, c0)
      xs <- w$xs
      ys <- w$ys
      n <- length(xs)
      if (n < 5L) next
      est <- estimate_degree(m, xs, ys)
      deg <- as.integer(est[[1]])
      rmse_sel <- est[[2]]
      rmse_best <- est[[3]]

      offs <- pit_offsets(m, c0, ht)
      ncol <- deg + 1L + length(offs)
      a <- matrix(0, n, ncol)
      for (pw in 0:deg) a[, deg + 1L - pw] <- xs^pw
      for (j in seq_along(offs)) {
        for (i in seq_len(n)) {
          a[i, deg + 1L + j] <- pit_shape_deg(m, abs(xs[i] * ht - offs[j]))
        }
      }
      co <- lstsq_qr(a, ys)
      poly_coef <- co[1:(deg + 1L)]

      # Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
      kept_offsets <- numeric(0)
      kept_coefs <- numeric(0)
      for (j in seq_along(offs)) {
        max_abs <- 0
        for (i in seq_len(n)) {
          d_deg <- abs(xs[i] * ht - offs[j])
          max_abs <- max(max_abs, abs(co[deg + 1L + j] * pit_shape_deg(m, d_deg)))
        }
        if (max_abs >= m$pit_shape$pit_min_amp) {
          kept_offsets <- c(kept_offsets, offs[j])
          kept_coefs <- c(kept_coefs, co[deg + 1L + j])
        }
      }

      m$patches[[length(m$patches) + 1L]] <-
        build_patch(m, c0, deg, xs, ys, poly_coef, kept_offsets, kept_coefs,
                    rmse_sel, rmse_best, angles, radii)
    }
    m$is_fitted <- TRUE
    m
  }

  # Метрики и статистика патча по его обучающему окну (полный базис).
  build_patch <- function(m, c0, deg, xs, ys, poly_coef, kept_offsets, kept_coefs,
                          rmse_sel, rmse_best, angles, radii) {
    n <- length(xs)
    ht <- half_train(m)
    sse <- 0
    sae <- 0
    mx <- 0
    fit_vals <- numeric(n)
    for (i in seq_len(n)) {
      v <- polyval(poly_coef, xs[i])
      for (j in seq_along(kept_offsets)) {
        v <- v + kept_coefs[j] * pit_shape_deg(m, abs(xs[i] * ht - kept_offsets[j]))
      }
      fit_vals[i] <- v
      e <- v - ys[i]
      sse <- sse + e * e
      sae <- sae + abs(e)
      mx <- max(mx, abs(e))
    }
    nf <- as.numeric(n)
    mf <- sum(fit_vals) / nf
    my <- sum(ys) / nf
    cov <- 0
    vf <- 0
    vy <- 0
    for (i in seq_len(n)) {
      df <- fit_vals[i] - mf
      dy <- ys[i] - my
      cov <- cov + df * dy
      vf <- vf + df * df
      vy <- vy + dy * dy
    }
    corr <- if (vf > 0 && vy > 0) cov / sqrt(vf * vy) else 0

    # Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
    ang <- as.numeric(angles)
    dist <- abs(((ang - c0 + 180) %% 360) - 180)
    sec <- as.numeric(radii)[dist <= m$half_sector]
    amp <- 0
    mean_sec <- 0
    if (length(sec) >= 5L) {
      amp <- percentile_linear(sec, 95) - percentile_linear(sec, 5)
      mean_sec <- sum(sec) / length(sec)
    }

    list(center_deg = c0, degree = deg, n_points = n, coefs = poly_coef,
         pit_offsets_deg = kept_offsets, pit_coefs = kept_coefs,
         metrics = list(amplitude_mm = amp, mean_radius_mm = mean_sec,
                        amplitude_norm = if (mean_sec > 0) amp / mean_sec else 0,
                        deg_elbow_tol = m$options$deg_elbow_tol,
                        rmse_selected_mm = rmse_sel, rmse_best_mm = rmse_best,
                        n_train_points = n),
         stats = list(rmse_mm = sqrt(sse / nf), mae_mm = sae / nf,
                      max_err_mm = mx, correlation = corr))
  }

  # Контур: нормированное smoothstep-смешивание патчей (partition of unity).
  eval_part <- function(m, angles, part = "total") {
    if (!isTRUE(m$is_fitted)) stop("Сначала вызовите fit()")
    hu <- half_use(m)
    ht <- half_train(m)
    raw <- m$options$coord_mode == "raw"
    ang <- as.numeric(angles)
    out <- numeric(length(ang))
    for (k in seq_along(ang)) {
      a <- ang[k]
      sum_wv <- 0
      sum_w <- 0
      for (p in m$patches) {
        w <- weight(m, circ_dist(a, p$center_deg), hu)
        if (w <= 0) next
        dx <- circ_local(a, p$center_deg)
        x <- if (raw) dx else dx / ht
        v <- 0
        if (part != "pit") v <- v + polyval(p$coefs, x)
        if (part != "poly") {
          for (j in seq_along(p$pit_offsets_deg)) {
            v <- v + p$pit_coefs[j] * pit_shape_deg(m, abs(x * ht - p$pit_offsets_deg[j]))
          }
        }
        sum_wv <- sum_wv + w * v
        sum_w <- sum_w + w
      }
      out[k] <- if (sum_w > 0) sum_wv / sum_w else 0
    }
    out
  }

  eval_model <- function(m, angles) eval_part(m, angles, "total")

}, Pappa$Model)

