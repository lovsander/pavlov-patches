# Pappa$Signal
#
# Сигнальные утилиты — поведение как у numpy и как в остальных портах: медиана
# (чётное n — среднее двух центральных), перцентиль с линейной интерполяцией,
# MAD/робастная sigma, IQR, окна по кольцу.
#
# Почему не stats::median / stats::quantile / stats::mad: у них другие типы
# интерполяции и масштаб; референс numpy-совместим, поэтому считаем сами.
# Округление же в R уже «половина к чётному» (IEC 60559) — как Python round()
# и math.RoundToEven, поэтому эмуляций, которых требовали другие порты, нет.

Pappa$Signal <- new.env(parent = Pappa)

evalq({

  # Медиана: чётное n — среднее двух центральных (numpy.median).
  median2 <- function(values) {
    n <- length(values)
    if (n == 0L) return(0)
    v <- sort(as.numeric(values))
    if (n %% 2L == 1L) v[(n + 1L) %/% 2L] else 0.5 * (v[n %/% 2L] + v[n %/% 2L + 1L])
  }

  # Перцентиль с линейной интерполяцией (numpy.percentile / тип 7 у R).
  percentile_linear <- function(values, q) {
    n <- length(values)
    if (n == 0L) return(0)
    v <- sort(as.numeric(values))
    pos <- (q / 100) * (n - 1)          # позиция 0-based, как в numpy
    lo <- floor(pos)                    # позиция 1-based — это lo + 1
    fr <- pos - lo
    hi <- min(lo + 1, n - 1L)           # позиция 0-based
    v[lo + 1L] + fr * (v[hi + 1L] - v[lo + 1L])
  }

  iqr2 <- function(values) {
    if (length(values) == 0L) return(0)
    percentile_linear(values, 75) - percentile_linear(values, 25)
  }

  mad2 <- function(values) {
    if (length(values) == 0L) return(0)
    m <- median2(values)
    median2(abs(as.numeric(values) - m))
  }

  robust_sigma <- function(values) 1.4826 * mad2(values)

  # Медианный шаг сетки по углам (медиана положительных разностей, иначе 1).
  angular_step <- function(angles) {
    n <- length(angles)
    if (n < 2L) return(1)
    d <- diff(as.numeric(angles))
    d <- d[d > 0]
    if (length(d) == 0L) 1 else median2(d)
  }

  # Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная,
  # не шире массива (минимум 3).
  window_points <- function(angles, span_deg) {
    n <- length(angles)
    if (n < 3L) return(max(1L, n))
    w <- as.integer(round(span_deg / angular_step(angles)))
    if (w %% 2L == 0L) w <- w + 1L
    if (w < 3L) w <- 3L
    if (w > n) w <- if (n %% 2L == 1L) n else n - 1L
    max(3L, w)
  }

  odd_window <- function(window, n) {
    w <- as.integer(window)
    if (w %% 2L == 0L) w <- w + 1L
    if (w < 3L) w <- 3L
    if (w > n) w <- if (n %% 2L == 1L) n else n - 1L
    w
  }

  # Медианный фильтр по кольцу (окно в точках).
  median_filter_wrap <- function(x, window) {
    n <- length(x)
    w <- odd_window(window, n)
    if (w < 3L || n < 3L) return(rep(median2(x), n))
    h <- (w - 1L) %/% 2L
    k0 <- seq_len(w) - 1L
    out <- numeric(n)
    for (i in seq_len(n)) out[i] <- median2(x[((i - h + k0 - 1L) %% n) + 1L])
    out
  }

  # Скользящее среднее по кольцу (окно в точках).
  smooth_wrap <- function(x, window) {
    n <- length(x)
    w <- odd_window(window, n)
    if (w < 3L || n < 3L) return(as.numeric(x))
    h <- (w - 1L) %/% 2L
    ks <- (-h):h
    out <- numeric(n)
    for (i in seq_len(n)) out[i] <- sum(x[((i + ks - 1L) %% n) + 1L]) / w
    out
  }

  # Расстояние по кольцу (0..180) и локальное смещение (-180..180).
  circ_dist <- function(a, b) abs(((a - b + 180) %% 360) - 180)
  circ_local <- function(a, b) ((a - b + 180) %% 360) - 180

  smoothstep <- function(t) {
    if (t < 0) return(0)
    if (t > 1) return(1)
    t * t * (3 - 2 * t)
  }

}, Pappa$Signal)
