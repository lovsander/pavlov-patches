# Пайплайн PAPPA на Julia: CSV с сечениями -> папка образца.
# Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
#   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
# Проверка: python python/studies/verify_port.py --cpp-dir <out-dir>
# Запуск: julia --project=julia julia/bin/pappa.jl --input FILE.csv --out-dir DIR [--name NAME]
#         [--description ТЕКСТ] [--no-pits] [--quiet]

using Pappa

function usage()
    println("PAPPA (Julia): --input FILE.csv --out-dir DIR [--name NAME] ",
            "[--description ТЕКСТ] [--no-pits] [--quiet]")
end

function main()
    input = ""
    out_dir = ""
    name = "sample"
    description = "PAPPA Julia port"
    pits = true
    quiet = false

    i = 1
    while i <= length(ARGS)
        a = ARGS[i]
        if a == "--input"
            i += 1
            i <= length(ARGS) && (input = ARGS[i])
        elseif a == "--out-dir"
            i += 1
            i <= length(ARGS) && (out_dir = ARGS[i])
        elseif a == "--name"
            i += 1
            i <= length(ARGS) && (name = ARGS[i])
        elseif a == "--description"
            i += 1
            i <= length(ARGS) && (description = ARGS[i])
        elseif a == "--no-pits"
            pits = false
        elseif a == "--quiet"
            quiet = true
        else
            usage()
            return 2
        end
        i += 1
    end
    if isempty(input) || isempty(out_dir)
        usage()
        return 2
    end

    rows = Csv.load_csv(input)
    println("PAPPA (Julia): $(length(rows)) точек, вход $input")

    opt = Csv.PipelineOptions(; pits = pits, verbose = !quiet)
    sections = Csv.process_sections(rows, opt)

    opts = Document.SampleOptions(; input_csv = input, pits = pits, description = description,
                                  cleaner = opt.cleaner, detector = opt.detector)
    root = Document.save_sample(out_dir, name, sections, opts)

    println()
    println("Образец записан: $root")
    println("  манифест: $(joinpath(root, "sample.json"))")
    println("  сечений:  $(length(sections)) (sections/*.pappa.json)")
    println()
    println("Сверка с референсом Python:")
    println("  python python/studies/verify_port.py --cpp-dir $root")
    0
end

exit(main())
