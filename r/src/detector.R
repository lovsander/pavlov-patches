# Pappa$Detector
#
# Детектор ям (трещин) — повторение python/pappa/analysis/zones.py:
#   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
#   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
#   зоны = участки, где индикатор > k, длиной не короче min_zone_deg.

Pappa$Detector <- new.env(parent = Pappa$Signal)

evalq({

  detector_options <- function(window_deg = 1.0, wide_deg = 10.0, smooth_deg = 2.0,
                               k = 5.5, min_zone_deg = 2.0) {
    list(window_deg = window_deg, wide_deg = wide_deg, smooth_deg = smooth_deg,
         k = k, min_zone_deg = min_zone_deg)
  }

  band_indicator <- function(angles, radii, o = detector_options()) {
    n <- length(radii)
    narrow <- median_filter_wrap(radii, window_points(angles, o$window_deg))
    wide <- median_filter_wrap(radii, window_points(angles, o$wide_deg))
    band <- abs(narrow - wide)

    out <- smooth_wrap(band, window_points(angles, o$smooth_deg))
    s <- robust_sigma(out)
    if (s > 1e-12) out / s else numeric(n)
  }

  # Непрерывные зоны по маске (углы — по возрастанию). Зона = list(lo=, hi=).
  mask_to_zones <- function(angles, mask, o = detector_options()) {
    n <- length(angles)
    if (!any(mask)) return(list())

    diffs <- diff(as.numeric(angles))
    step <- if (length(diffs) == 0L) 1 else median2(diffs)

    zones <- list()
    i <- 1L
    while (i <= n) {
      if (!mask[i]) {
        i <- i + 1L
        next
      }
      j <- i
      while (j + 1L <= n && mask[j + 1L]) j <- j + 1L
      zones[[length(zones) + 1L]] <- list(lo = angles[i] - step / 2,
                                          hi = angles[j] + step / 2)
      i <- j + 1L
    }

    # Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
    if (length(zones) > 1L && mask[1L] && mask[n]) {
      merged <- list(list(lo = zones[[length(zones)]]$lo - 360, hi = zones[[1L]]$hi))
      if (length(zones) > 2L) merged <- c(merged, zones[2:(length(zones) - 1L)])
      zones <- merged
    }

    Filter(function(z) z$hi - z$lo >= o$min_zone_deg, zones)
  }

  zones <- function(angles, values, o = detector_options()) {
    mask_to_zones(angles, values > o$k, o)
  }

  zone_center <- function(z) 0.5 * (z$lo + z$hi)

  # Центры ям (°).
  pits <- function(angles, radii, o = detector_options()) {
    band <- band_indicator(angles, radii, o)
    vapply(zones(angles, band, o), zone_center, numeric(1))
  }

}, Pappa$Detector)
