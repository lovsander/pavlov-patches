# Pappa$Linalg
#
# Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
# np.linalg.lstsq, алгоритм совпадает с остальными портами) + базис Чебышёва
# для быстрого выбора степени.
#
# Почему не base::qr / qr.solve / lm.fit: у них LAPACK-путь со своей
# псевдообработкой вырожденных столбцов (pivoting) — коэффициенты разошлись бы
# с остальными портами сильнее, чем допускает вектор модели (1e-9 отн.).
#
# Родитель — Signal: цепочка Pappa$Model -> Linalg -> Signal -> Pappa -> base
# заменяет `using ..Signal; using ..Linalg` из Julia-порта (у окружения в R
# родитель ровно один, поэтому модули выстроены в цепочку).

Pappa$Linalg <- new.env(parent = Pappa$Signal)

evalq({

  # Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится.
  lstsq_qr <- function(a_in, b_in) {
    m <- nrow(a_in)
    n <- ncol(a_in)
    if (m == 0L) stop("lstsq: пустая матрица")
    if (length(b_in) != m) stop("lstsq: длины A и b не совпадают")
    if (m < n) stop("lstsq: нужно m >= n")

    a <- matrix(as.numeric(a_in), m, n)
    b <- as.numeric(b_in)

    for (k in seq_len(n)) {
      nrm <- sqrt(sum(a[k:m, k]^2))
      if (nrm < 1e-300) next

      alpha <- if (a[k, k] > 0) -nrm else nrm
      v <- numeric(m)
      v[k:m] <- a[k:m, k]
      v[k] <- v[k] - alpha
      vnorm2 <- sum(v[k:m]^2)
      if (vnorm2 < 1e-300) next

      for (j in k:n) {
        cc <- 2 * sum(v[k:m] * a[k:m, j]) / vnorm2
        a[k:m, j] <- a[k:m, j] - cc * v[k:m]
      }
      cb <- 2 * sum(v[k:m] * b[k:m]) / vnorm2
      b[k:m] <- b[k:m] - cb * v[k:m]
    }

    x <- numeric(n)
    for (i in n:1) {
      s <- b[i]
      if (i < n) s <- s - sum(a[i, (i + 1L):n] * x[(i + 1L):n])
      d <- a[i, i]
      if (abs(d) < 1e-300) stop("lstsq: вырожденная система")
      x[i] <- s / d
    }
    x
  }

  # Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval).
  polyval <- function(coefs, x) {
    r <- 0
    for (c0 in coefs) r <- r * x + c0
    r
  }

  polyfit <- function(xs, ys, deg) {
    xs <- as.numeric(xs)
    a <- matrix(0, length(xs), deg + 1L)
    for (pw in 0:deg) a[, deg + 1L - pw] <- xs^pw   # столбцы по УБЫВАНИЮ степени
    lstsq_qr(a, ys)
  }

  # T_0(x)..T_deg_max(x) — базис Чебышёва (x ∈ [-1, 1]) для одного x или вектора.
  cheb_row <- function(x, deg_max) {
    t <- numeric(deg_max + 1L)
    t[1L] <- 1
    if (deg_max >= 1L) t[2L] <- x
    if (deg_max >= 2L) for (k in 3:(deg_max + 1L)) t[k] <- 2 * x * t[k - 1L] - t[k - 2L]
    t
  }

  # Матрица Чебышёва n×p (векторный вариант cheb_row — тот же рекуррентный ряд).
  cheb_matrix <- function(x, deg_max) {
    x <- as.numeric(x)
    n <- length(x)
    t <- matrix(1, n, deg_max + 1L)
    if (deg_max >= 1L) t[, 2L] <- x
    if (deg_max >= 2L) for (k in 3:(deg_max + 1L)) t[, k] <- 2 * x * t[, k - 1L] - t[, k - 2L]
    t
  }

  # Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
  cheb_sum <- function(co, deg, x) {
    b1 <- 0
    b2 <- 0
    if (deg >= 1L) {
      for (k in deg:1) {
        b0 <- 2 * x * b1 - b2 + co[k + 1L]
        b2 <- b1
        b1 <- b0
      }
    }
    x * b1 - b2 + co[1L]
  }

}, Pappa$Linalg)
