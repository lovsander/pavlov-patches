"""
    Pappa.Csv

Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go).
"""
module Csv

using ..Signal
using ..Json
using ..Cleaner
using ..Detector
import ..Model            # import, а не using: экспортированный тип Model затеняет модуль

export Row, SectionModel, PipelineOptions, load_csv, process_sections

struct Row
    section_id::Int
    height_mm::Float64
    angle_deg::Float64
    radius_mm::Float64
end

"""Сечение + обученная модель + метаданные для документа."""
mutable struct SectionModel
    section_id::Int
    height_mm::Float64
    model::Model.Model
    n_points_total::Int
    n_outliers::Int
    n_used::Int
    fit_time_ms::Float64
    description::String
    pits::Vector{Float64}
end

Base.@kwdef struct PipelineOptions
    model::Model.ModelOptions = Model.ModelOptions()
    cleaner::Cleaner.CleanerOptions = Cleaner.CleanerOptions()
    detector::Detector.DetectorOptions = Detector.DetectorOptions()
    pits::Bool = true
    verbose::Bool = true
end

"""Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок)."""
function load_csv(path::AbstractString)
    text = read_text(path)
    lines = [strip(l, ['\r', ' ']) for l in split(text, '\n')]
    lines = filter(!isempty, lines)
    isempty(lines) && error("пустой CSV: $path")

    split_comma(s) = [strip(f) for f in split(s, ',')]
    head = split_comma(lines[1])
    col(name) = begin
        i = findfirst(==(name), head)
        i === nothing && error("в CSV нет колонки $name")
        i
    end
    i_sec = col("section_id")
    i_h = col("height_mm")
    i_a = col("angle_deg")
    i_r = col("radius_mm")
    need = max(i_sec, i_h, i_a, i_r)

    rows = Row[]
    for line in lines[2:end]
        f = split_comma(line)
        # length(f) < need, а НЕ <= need: индексы в Julia с 1, поэтому need — это
        # НОМЕР последней нужной колонки (4 для файла из четырёх колонок), и
        # строка годится, если полей не меньше, чем need.
        length(f) < need && continue
        push!(rows, Row(parse(Int, f[i_sec]), parse(Float64, f[i_h]),
                        parse(Float64, f[i_a]), parse(Float64, f[i_r])))
    end
    isempty(rows) && error("в CSV нет строк с данными")
    rows
end

"""Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение."""
function process_sections(rows::Vector{Row}, opt::PipelineOptions = PipelineOptions())
    ids = sort(unique(r.section_id for r in rows))
    out = SectionModel[]

    for sid in ids
        group = sort(filter(r -> r.section_id == sid, rows), by = r -> r.angle_deg)
        n = length(group)
        angles = [g.angle_deg for g in group]
        radii = [g.radius_mm for g in group]

        cl = Cleaner.clean_iqr(angles, radii, opt.cleaner)
        a_clean = Float64[]
        r_clean = Float64[]
        for i in 1:n
            cl.mask[i] && continue
            push!(a_clean, angles[i])
            push!(r_clean, radii[i])
        end

        pits = opt.pits ? Detector.pits(a_clean, r_clean, opt.detector) : Float64[]
        model = Model.Model(opt.model, pits)

        t0 = time()
        Model.fit!(model, a_clean, r_clean)
        fit_ms = (time() - t0) * 1000.0

        if opt.verbose
            println("  секция $sid (h=$(round(Int, group[1].height_mm)) мм): точек $n, "
                    * "выброшено $(cl.n_outliers), ям найдено $(length(pits)), "
                    * "степени $(Model.degrees(model)), обучение $(round(fit_ms, digits=1)) мс")
        end

        push!(out, SectionModel(sid, group[1].height_mm, model, n, cl.n_outliers,
                                length(a_clean), fit_ms,
                                "сечение $sid, h=$(round(Int, group[1].height_mm)) мм", pits))
    end
    out
end

end # module Csv
