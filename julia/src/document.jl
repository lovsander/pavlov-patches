"""
    Pappa.Document

Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin/Rust/Pascal/Swift:
    <out_dir>/sample.json              манифест (format pappa-sample v1.0)
    <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
сравниваются численно (python/studies/verify_port.py).
"""
module Document

using ..Json
using ..Cleaner
using ..Detector
import ..Model            # import, а не using: экспортированный тип Model затеняет модуль
using ..Csv

export PORT_VERSION, PORT_LANGUAGE, SampleOptions,
       save_section_document, save_sample, iso_utc_now

const PORT_VERSION = "0.1.0"
const PORT_LANGUAGE = "julia"

Base.@kwdef struct SampleOptions
    input_csv::String = ""
    pits::Bool = true
    description::String = "PAPPA Julia port"
    cleaner::Cleaner.CleanerOptions = Cleaner.CleanerOptions()
    detector::Detector.DetectorOptions = Detector.DetectorOptions()
end

"""Сечение даты из числа дней с 1970-01-01 (алгоритм Говарда Хиннанта)."""
function civil_from_days(z0::Int)
    z = z0 + 719468
    era = (z >= 0 ? z : z - 146096) ÷ 146097
    doe = z - era * 146097
    yoe = (doe - doe ÷ 1460 + doe ÷ 36524 - doe ÷ 146096) ÷ 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe ÷ 4 - yoe ÷ 100)
    mp = (5 * doy + 2) ÷ 153
    d = doy - (153 * mp + 2) ÷ 5 + 1
    m = mp < 10 ? mp + 3 : mp - 9
    (m <= 2 ? y + 1 : y, m, d)
end

function iso_utc_now()
    secs = floor(Int, time())
    days = secs ÷ 86400
    rem = secs - days * 86400
    y, m, d = civil_from_days(days)
    p2(v) = lpad(v, 2, '0')
    "$(y)-$(p2(m))-$(p2(d))T$(p2(rem ÷ 3600)):$(p2((rem % 3600) ÷ 60)):$(p2(rem % 60))Z"
end

"""Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++."""
mutable struct Writer
    io::IOBuffer
    depth::Int
    Writer() = new(IOBuffer(), 0)
end

ind(w::Writer) = repeat(" ", max(0, w.depth) * 2)
obj_start(w::Writer) = (print(w.io, '{'); w.depth += 1; print(w.io, "\n", ind(w)))
obj_end(w::Writer) = (w.depth -= 1; print(w.io, "\n", ind(w), '}'))
arr_start(w::Writer) = (print(w.io, '['); w.depth += 1; print(w.io, "\n", ind(w)))
arr_end(w::Writer) = (w.depth -= 1; print(w.io, "\n", ind(w), ']'))
comma(w::Writer) = print(w.io, ",\n", ind(w))
key(w::Writer, k::AbstractString) = print(w.io, ind(w), '"', k, "\": ")
str_val(w::Writer, v::AbstractString) = print(w.io, '"', json_esc(v), '"')
num_val(w::Writer, v::Real) = print(w.io, json_num(v))
int_val(w::Writer, v::Integer) = print(w.io, string(Int(v)))
bool_val(w::Writer, v::Bool) = print(w.io, v ? "true" : "false")
raw(w::Writer, s::AbstractString) = print(w.io, s)
text(w::Writer) = String(take!(w.io))

kv(w::Writer, k, v::AbstractString) = (key(w, k); str_val(w, v))
kv(w::Writer, k, v::Real) = (key(w, k); num_val(w, v))
kv(w::Writer, k, v::Integer) = (key(w, k); int_val(w, v))
kv(w::Writer, k, v::Bool) = (key(w, k); bool_val(w, v))

function write_patches(w::Writer, m::Model.Model)
    key(w, "patches")
    arr_start(w)
    for (i, p) in enumerate(m.patches)
        raw(w, i > 1 ? ",\n" * ind(w) : "\n" * ind(w))
        obj_start(w)
        kv(w, "center_deg", p.center_deg);  comma(w)
        kv(w, "degree", p.degree);          comma(w)
        kv(w, "n_points", p.n_points);      comma(w)
        key(w, "coefs")
        arr_start(w)
        for (j, c) in enumerate(p.coefs)
            j > 1 && raw(w, ", ")
            num_val(w, c)
        end
        arr_end(w)
        comma(w)

        key(w, "metrics")
        obj_start(w)
        kv(w, "amplitude_mm", p.metrics.amplitude_mm);        comma(w)
        kv(w, "mean_radius_mm", p.metrics.mean_radius_mm);    comma(w)
        kv(w, "amplitude_norm", p.metrics.amplitude_norm);    comma(w)
        kv(w, "deg_elbow_tol", p.metrics.deg_elbow_tol);      comma(w)
        kv(w, "rmse_selected_mm", p.metrics.rmse_selected_mm); comma(w)
        kv(w, "rmse_best_mm", p.metrics.rmse_best_mm);        comma(w)
        kv(w, "n_train_points", p.metrics.n_train_points)
        obj_end(w)
        comma(w)

        key(w, "stats")
        obj_start(w)
        kv(w, "rmse_mm", p.stats.rmse_mm);          comma(w)
        kv(w, "mae_mm", p.stats.mae_mm);            comma(w)
        kv(w, "max_err_mm", p.stats.max_err_mm);    comma(w)
        kv(w, "correlation", p.stats.correlation)
        obj_end(w)

        # Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
        # (включая пустой список): так ждёт загрузчик Python.
        if Model.has_pits(m)
            comma(w)
            key(w, "pit_terms")
            arr_start(w)
            for (j, off) in enumerate(p.pit_offsets_deg)
                j > 1 && raw(w, ", ")
                obj_start(w)
                kv(w, "dx_deg", off);            comma(w)
                kv(w, "amp", p.pit_coefs[j])
                obj_end(w)
            end
            arr_end(w)
        end
        obj_end(w)
    end
    isempty(m.patches) || raw(w, "\n" * ind(w))
    arr_end(w)
end

function save_section_document(path::AbstractString, section::Csv.SectionModel)
    m = section.model
    m.is_fitted || error("save_section_document: модель не обучена")
    w = Writer()
    obj_start(w)
    kv(w, "format", "pappa");   comma(w)
    kv(w, "version", "2.0");    comma(w)
    kv(w, "method", Model.has_pits(m) ? "PitPatchApproximator" : "PatchApproximator"); comma(w)
    kv(w, "created", iso_utc_now());  comma(w)

    key(w, "software")
    obj_start(w)
    kv(w, "language", PORT_LANGUAGE);   comma(w)
    kv(w, "pappa_version", PORT_VERSION)
    obj_end(w)
    comma(w)

    key(w, "meta")
    obj_start(w)
    kv(w, "section_id", section.section_id);   comma(w)
    kv(w, "height_mm", section.height_mm);     comma(w)
    kv(w, "source", "csv");                    comma(w)
    kv(w, "description", section.description)
    obj_end(w)
    comma(w)

    key(w, "global")
    obj_start(w)
    key(w, "units")
    obj_start(w)
    kv(w, "angle", "degree");  comma(w)
    kv(w, "length", "mm")
    obj_end(w)
    comma(w)
    opt = m.options
    kv(w, "n_patches", opt.n_patches);                comma(w)
    kv(w, "half_sector_deg", m.half_sector);          comma(w)
    kv(w, "phase_deg", opt.phase_deg);                comma(w)
    kv(w, "half_train_deg", Model.half_train(m));     comma(w)
    kv(w, "half_use_deg", Model.half_use(m));         comma(w)
    kv(w, "overlap_train_deg", opt.overlap_train);    comma(w)
    kv(w, "overlap_use_deg", opt.overlap_use);        comma(w)
    kv(w, "deg_min", opt.deg_min);                    comma(w)
    kv(w, "deg_max", opt.deg_max);                    comma(w)
    kv(w, "coord_mode", opt.coord_mode);              comma(w)
    kv(w, "deg_elbow_tol", opt.deg_elbow_tol);        comma(w)
    kv(w, "amplitude_scale", opt.amplitude_scale)
    if Model.has_pits(m)
        ps = m.pit_shape
        comma(w)
        key(w, "pit")
        obj_start(w)
        kv(w, "sigma_deg", ps.sigma_deg);          comma(w)
        kv(w, "core_sigma", ps.core_sigma);        comma(w)
        kv(w, "window_sigma", ps.window_sigma);    comma(w)
        kv(w, "pit_min_amp", ps.pit_min_amp);      comma(w)
        kv(w, "tapering", ps.tapering);            comma(w)
        key(w, "centers_deg")
        arr_start(w)
        for (i, c) in enumerate(m.pits)
            i > 1 && raw(w, ", ")
            num_val(w, c)
        end
        arr_end(w)
        obj_end(w)
    end
    obj_end(w)
    comma(w)

    write_patches(w, m)
    comma(w)

    key(w, "statistics")
    obj_start(w)
    kv(w, "n_points_total", section.n_points_total);    comma(w)
    kv(w, "n_outliers_removed", section.n_outliers);    comma(w)
    kv(w, "fit_time_ms", section.fit_time_ms)
    obj_end(w)

    obj_end(w)
    write_text(path, text(w) * "\n")
    path
end

function save_sample(out_dir::AbstractString, name::AbstractString,
                     sections::Vector{Csv.SectionModel}, o::SampleOptions = SampleOptions())
    mkpath(joinpath(out_dir, "sections"))
    ordered = sort(sections, by = s -> s.section_id)
    first_model = isempty(ordered) ? nothing : ordered[1].model

    w = Writer()
    obj_start(w)
    kv(w, "format", "pappa-sample");  comma(w)
    kv(w, "version", "1.0");          comma(w)
    kv(w, "name", name);              comma(w)
    kv(w, "created", iso_utc_now());  comma(w)

    key(w, "units")
    obj_start(w)
    kv(w, "angle", "degree");  comma(w)
    kv(w, "length", "mm")
    obj_end(w)
    comma(w)

    key(w, "meta")
    obj_start(w)
    kv(w, "description", o.description)
    obj_end(w)
    comma(w)

    if !isempty(o.input_csv)
        key(w, "input")
        obj_start(w)
        kv(w, "csv", o.input_csv)
        obj_end(w)
        comma(w)
    end

    key(w, "config")
    obj_start(w)
    opt = first_model === nothing ? Model.ModelOptions() : first_model.options
    kv(w, "n_patches", first_model === nothing ? 0 : opt.n_patches);          comma(w)
    kv(w, "phase_deg", first_model === nothing ? 0.0 : opt.phase_deg);        comma(w)
    kv(w, "deg_min", first_model === nothing ? 0 : opt.deg_min);              comma(w)
    kv(w, "deg_max", first_model === nothing ? 0 : opt.deg_max);              comma(w)
    kv(w, "overlap_train", first_model === nothing ? 0.0 : opt.overlap_train); comma(w)
    kv(w, "overlap_use", first_model === nothing ? 0.0 : opt.overlap_use);    comma(w)
    kv(w, "deg_elbow_tol", first_model === nothing ? 0.0 : opt.deg_elbow_tol); comma(w)
    key(w, "cleaner")
    raw(w, "{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", \"baseline_deg\": "
        * json_num(o.cleaner.baseline_deg) * ", \"iqr_k\": " * json_num(o.cleaner.iqr_k) * "}}")
    comma(w)
    kv(w, "pits", o.pits)
    if o.pits && first_model !== nothing
        ps = first_model.pit_shape
        comma(w)
        kv(w, "sigma_deg", ps.sigma_deg);             comma(w)
        kv(w, "pit_core_sigma", ps.core_sigma);       comma(w)
        kv(w, "pit_window_sigma", ps.window_sigma);   comma(w)
        kv(w, "pit_min_amp", ps.pit_min_amp);         comma(w)
        kv(w, "tapering", ps.tapering)
    end
    comma(w)
    key(w, "detector")
    raw(w, "null")
    obj_end(w)
    comma(w)

    key(w, "sections")
    arr_start(w)
    for (i, s) in enumerate(ordered)
        file = "sections/" * lpad(i - 1, 2, '0') * ".pappa.json"
        save_section_document(joinpath(out_dir, file), s)
        raw(w, i > 1 ? ",\n" * ind(w) : "\n" * ind(w))
        obj_start(w)
        kv(w, "index", i - 1);               comma(w)
        kv(w, "section_id", s.section_id);   comma(w)
        kv(w, "height_mm", s.height_mm);     comma(w)
        kv(w, "file", file);                 comma(w)
        kv(w, "n_points", s.n_points_total); comma(w)
        kv(w, "n_outliers", s.n_outliers)
        obj_end(w)
    end
    isempty(ordered) || raw(w, "\n" * ind(w))
    arr_end(w)

    obj_end(w)
    write_text(joinpath(out_dir, "sample.json"), text(w) * "\n")
    out_dir
end

end # module Document
