# Pappa$Cleaner
#
# Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
# по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
# Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py).

Pappa$Cleaner <- new.env(parent = Pappa$Signal)   # видно имена Signal (как using ..Signal)

evalq({

  # Параметры очистки (замена @kwdef-структуры остальных портов).
  cleaner_options <- function(baseline_deg = 1.0, iqr_k = 3.0,
                              max_removed_frac = 0.5, min_points = 20L) {
    list(baseline_deg = baseline_deg, iqr_k = iqr_k,
         max_removed_frac = max_removed_frac, min_points = min_points)
  }

  # Маска выбросов: TRUE — точка выброшена.
  clean_iqr <- function(angles, radii, o = cleaner_options()) {
    n <- length(radii)
    mask <- logical(n)
    if (n < o$min_points) {
      return(list(mask = mask, n_outliers = 0L, window = 0L))
    }

    w <- window_points(angles, o$baseline_deg)
    base <- median_filter_wrap(radii, w)
    res <- as.numeric(radii) - base

    center <- median2(res)
    spread <- iqr2(res)
    denom <- if (spread > 1e-12) spread else 1.0     # защита референса

    sev <- abs(res - center) / denom
    mask <- sev > o$iqr_k
    flagged <- sum(mask)

    # Предохранитель: не выбрасываем больше max_removed_frac точек.
    cap <- floor(o$max_removed_frac * n)
    if (cap > 0 && cap < n && flagged > cap) {
      kept <- sort(sev[mask])
      level <- kept[length(kept) - cap + 1L]
      mask <- mask & (sev >= level)
      flagged <- sum(mask)
    }
    list(mask = mask, n_outliers = as.integer(flagged), window = as.integer(w))
  }

}, Pappa$Cleaner)
