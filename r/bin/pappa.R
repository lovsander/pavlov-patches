# Пайплайн PAPPA на R: CSV с сечениями -> папка образца.
# Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
#   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
# Проверка: python python/studies/verify_port.py --py-dir samples/synthetic_sphere \
#                                               --cpp-dir <out-dir>
# Запуск: Rscript r/bin/pappa.R --input FILE.csv --out-dir DIR [--name NAME]
#         [--description ТЕКСТ] [--no-pits] [--quiet]

script_dir <- function() {
  a <- commandArgs(trailingOnly = FALSE)
  m <- grep("^--file=", a, value = TRUE)
  if (length(m) == 0L) return(normalizePath("."))
  normalizePath(dirname(sub("^--file=", "", m[[1L]])))
}

SRC_DIR <- file.path(script_dir(), "..", "src")
source(file.path(SRC_DIR, "pappa.R"))
Pappa$load(SRC_DIR)

usage <- function() {
  cat("PAPPA (R): --input FILE.csv --out-dir DIR [--name NAME] ",
      "[--description ТЕКСТ] [--no-pits] [--quiet]\n", sep = "")
}

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  input <- ""
  out_dir <- ""
  name <- "sample"
  description <- "PAPPA R port"
  pits <- TRUE
  quiet <- FALSE

  i <- 1L
  while (i <= length(args)) {
    a <- args[[i]]
    if (a == "--input") {
      i <- i + 1L
      if (i <= length(args)) input <- args[[i]]
    } else if (a == "--out-dir") {
      i <- i + 1L
      if (i <= length(args)) out_dir <- args[[i]]
    } else if (a == "--name") {
      i <- i + 1L
      if (i <= length(args)) name <- args[[i]]
    } else if (a == "--description") {
      i <- i + 1L
      if (i <= length(args)) description <- args[[i]]
    } else if (a == "--no-pits") {
      pits <- FALSE
    } else if (a == "--quiet") {
      quiet <- TRUE
    } else {
      usage()
      return(2L)
    }
    i <- i + 1L
  }
  if (!nzchar(input) || !nzchar(out_dir)) {
    usage()
    return(2L)
  }

  rows <- Pappa$Csv$load_csv(input)
  cat(sprintf("PAPPA (R): %d точек, вход %s\n", rows$n, input))

  opt <- Pappa$Csv$pipeline_options(pits = pits, verbose = !quiet)
  sections <- Pappa$Csv$process_sections(rows, opt)

  opts <- Pappa$Document$sample_options(input_csv = input, pits = pits,
                                        description = description,
                                        cleaner = opt$cleaner, detector = opt$detector)
  root <- Pappa$Document$save_sample(out_dir, name, sections, opts)

  cat("\n")
  cat(sprintf("Образец записан: %s\n", root))
  cat(sprintf("  манифест: %s\n", file.path(root, "sample.json")))
  cat(sprintf("  сечений:  %d (sections/*.pappa.json)\n", length(sections)))
  cat("\n")
  cat("Сверка с референсом Python:\n")
  cat(sprintf("  python python/studies/verify_port.py --cpp-dir %s\n", root))
  0L
}

quit(save = "no", status = main())
