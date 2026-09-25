# Pappa$Json
#
# Минимальный JSON: разбор и запись без внешних пакетов (jsonlite принципиально
# не используется — порт должен работать на голом R).
# Объекты — именованные списки, массивы — списки, числа — double, null — NULL.

Pappa$Json <- new.env(parent = Pappa)

evalq({

  # Число в стиле %.17g из C/C++: целые без дробной части, иначе кратчайшая
  # запись, которая читается обратно в то же double (для очень малых — экспонента,
  # это валидный JSON и понятно парсеру Python).
  json_num <- function(v) {
    v <- as.numeric(v)
    if (length(v) != 1L || !is.finite(v)) return("0")
    if (v == 0) return("0")
    if (abs(v) < 1e15 && v == round(v)) return(sprintf("%.0f", v))
    for (d in 1:17) {
      s <- trimws(format(v, digits = d, scientific = NA))
      back <- suppressWarnings(as.numeric(s))
      if (!is.na(back) && back == v) return(s)
    }
    trimws(format(v, digits = 17, scientific = NA))
  }

  json_esc <- function(s) {
    ch <- strsplit(as.character(s), "", fixed = TRUE)[[1]]
    if (length(ch) == 0L) return("")
    out <- vapply(ch, function(c0) {
      if (c0 == "\"") "\\\""
      else if (c0 == "\\") "\\\\"
      else if (c0 == "\n") "\\n"
      else if (c0 == "\r") "\\r"
      else if (c0 == "\t") "\\t"
      else c0
    }, character(1), USE.NAMES = FALSE)
    paste0(out, collapse = "")
  }

  read_text <- function(path) {
    txt <- readLines(path, warn = FALSE, encoding = "UTF-8")
    paste(txt, collapse = "\n")
  }

  write_text <- function(path, text) {
    con <- file(path, open = "wb")
    on.exit(close(con))
    writeBin(charToRaw(enc2utf8(as.character(text))), con)
    invisible(path)
  }

  # ---------- доступ к разобранному ----------

  jget <- function(v, key) {
    if (!(key %in% names(v))) stop("JSON: нет ключа ", key)
    v[[key]]
  }

  jdbl <- function(v, key) as.numeric(jget(v, key))

  jdbl_or <- function(v, key, def = 0) {
    x <- v[[key]]
    if (is.numeric(x) && length(x) == 1L) as.numeric(x) else as.numeric(def)
  }

  jint <- function(v, key) as.integer(round(jdbl(v, key)))

  jtext <- function(v, key) as.character(jget(v, key))

  jbool_or <- function(v, key, def = FALSE) {
    x <- v[[key]]
    if (is.logical(x) && length(x) == 1L) isTRUE(x) else def
  }

  jarr <- function(v) {
    if (!is.list(v)) stop("JSON: ожидался массив")
    v
  }

  jdoubles <- function(v, key) {
    a <- jarr(jget(v, key))
    if (length(a) == 0L) return(numeric(0))
    vapply(a, as.numeric, numeric(1), USE.NAMES = FALSE)
  }

  jints <- function(v, key) {
    a <- jarr(jget(v, key))
    if (length(a) == 0L) return(integer(0))
    vapply(a, function(x) as.integer(round(as.numeric(x))), integer(1), USE.NAMES = FALSE)
  }

  jcount <- function(v) length(jarr(v))

  # ---------- разбор ----------

  json_parse <- function(text) {
    s <- strsplit(as.character(text), "", fixed = TRUE)[[1]]
    if (length(s) == 0L) stop("JSON: пустой ввод")
    p <- new.env(parent = emptyenv())
    p$s <- s
    p$i <- 1L
    p$n <- length(s)
    skipws(p)
    parse_value(p)
  }

  skipws <- function(p) {
    while (p$i <= p$n && (p$s[p$i] == " " || p$s[p$i] == "\t" ||
                          p$s[p$i] == "\n" || p$s[p$i] == "\r")) {
      p$i <- p$i + 1L
    }
  }

  parse_value <- function(p) {
    if (p$i > p$n) stop("JSON: неожиданный конец")
    c0 <- p$s[p$i]
    if (c0 == "{") return(parse_object(p))
    if (c0 == "[") return(parse_array(p))
    if (c0 == "\"") return(parse_string(p))
    if (c0 == "t") { expect_lit(p, "true"); return(TRUE) }
    if (c0 == "f") { expect_lit(p, "false"); return(FALSE) }
    if (c0 == "n") { expect_lit(p, "null"); return(NULL) }
    parse_number(p)
  }

  expect_lit <- function(p, lit) {
    for (c0 in strsplit(lit, "", fixed = TRUE)[[1]]) {
      if (p$i > p$n || p$s[p$i] != c0) stop("JSON: ожидался литерал ", lit)
      p$i <- p$i + 1L
    }
  }

  parse_object <- function(p) {
    d <- list()
    p$i <- p$i + 1L                                # {
    skipws(p)
    if (p$s[p$i] == "}") {
      p$i <- p$i + 1L
      return(d)
    }
    repeat {
      skipws(p)
      k <- parse_string(p)
      skipws(p)
      if (p$s[p$i] != ":") stop("JSON: ожидалось ':'")
      p$i <- p$i + 1L
      skipws(p)
      # ВАЖНО: именно `d[k] <- list(v)`, а не `d[[k]] <- v`: в R присваивание
      # NULL через [[<- УДАЛЯЕТ элемент, то есть JSON-null исчезал бы из объекта.
      v <- parse_value(p)
      d[k] <- list(v)
      skipws(p)
      c0 <- p$s[p$i]
      p$i <- p$i + 1L
      if (c0 == "}") return(d)
      if (c0 != ",") stop("JSON: ожидалась ',' или '}'")
    }
  }

  parse_array <- function(p) {
    a <- list()
    p$i <- p$i + 1L                                # [
    skipws(p)
    if (p$s[p$i] == "]") {
      p$i <- p$i + 1L
      return(a)
    }
    repeat {
      skipws(p)
      v <- parse_value(p)
      a[length(a) + 1L] <- list(v)   # list(): иначе JSON-null удалял бы элемент
      skipws(p)
      c0 <- p$s[p$i]
      p$i <- p$i + 1L
      if (c0 == "]") return(a)
      if (c0 != ",") stop("JSON: ожидалась ',' или ']'")
    }
  }

  parse_string <- function(p) {
    if (p$s[p$i] != "\"") stop("JSON: ожидалась строка")
    p$i <- p$i + 1L
    out <- character(0)
    repeat {
      c0 <- p$s[p$i]
      p$i <- p$i + 1L
      if (c0 == "\"") return(paste0(out, collapse = ""))
      if (c0 != "\\") {
        out <- c(out, c0)
        next
      }
      e <- p$s[p$i]
      p$i <- p$i + 1L
      if (e == "n") out <- c(out, "\n")
      else if (e == "t") out <- c(out, "\t")
      else if (e == "r") out <- c(out, "\r")
      else if (e == "b") out <- c(out, "\b")
      else if (e == "f") out <- c(out, "\f")
      else if (e == "u") {
        hex <- paste0(p$s[p$i:(p$i + 3L)], collapse = "")
        p$i <- p$i + 4L
        code <- strtoi(hex, 16L)
        out <- c(out, if (!is.na(code) && code < 0x80) rawToChar(as.raw(code)) else "?")
      } else out <- c(out, e)
    }
  }

  parse_number <- function(p) {
    start <- p$i
    while (p$i <= p$n && p$s[p$i] %in% c("+", "-", "0", "1", "2", "3", "4", "5",
                                         "6", "7", "8", "9", ".", "e", "E")) {
      p$i <- p$i + 1L
    }
    txt <- paste0(p$s[start:(p$i - 1L)], collapse = "")
    v <- suppressWarnings(as.numeric(txt))
    if (is.na(v)) stop("JSON: плохое число ", txt)
    v
  }

}, Pappa$Json)


