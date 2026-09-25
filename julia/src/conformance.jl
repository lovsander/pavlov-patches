"""
    Pappa.Conformance

Проверка порта по конформанс-векторам (spec/conformance/vectors).
Допуски — те же, что у C++/Go/C/JS/Java/Kotlin/Rust/Pascal/Swift: контур 1e-6 мм,
коэффициенты max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
"""
module Conformance

using ..Json
using ..Cleaner
using ..Detector
import ..Model            # import, а не using: экспортированный тип Model затеняет модуль

export Outcome, VectorFile, load_vectors, check_vector

struct Outcome
    ok::Bool
    detail::String
    notes::Vector{String}
end

struct VectorFile
    file::String
    data::Any
end

function load_vectors(dir::AbstractString)
    isdir(dir) || error("нет каталога векторов: $dir")
    names = sort(filter(f -> endswith(f, ".json"), readdir(dir)))
    isempty(names) && error("нет каталога векторов: $dir")
    [VectorFile(n, json_parse(read_text(joinpath(dir, n)))) for n in names]
end

near(a, b, rel, flr) = abs(a - b) <= max(flr, rel * abs(b))

function check_vector(v::AbstractDict)
    kind = jtext(v, "kind")
    kind == "model" && return check_model(v)
    kind == "detector" && return check_detector(v)
    check_cleaner(v)
end

function check_detector(v::AbstractDict)
    cfg = jget(v, "config")
    exp = jget(v, "expected")
    input = jget(v, "input")
    angles = jdoubles(input, "angles_deg")
    radii = jdoubles(input, "radii_mm")
    o = Detector.DetectorOptions(; window_deg = jdbl(cfg, "window_deg"),
        wide_deg = jdbl(cfg, "wide_deg"), smooth_deg = jdbl(cfg, "smooth_deg"),
        k = jdbl(cfg, "k"), min_zone_deg = jdbl(cfg, "min_zone_deg"))

    band = Detector.band_indicator(angles, radii, o)
    zs = Detector.zones(angles, band, o)
    exp_zones = jarr(jget(exp, "zones_deg"))
    exp_pits = jdoubles(exp, "pits_deg")
    notes = String[]

    ok = length(zs) == length(exp_zones)
    ok || push!(notes, "зон $(length(zs)) != $(length(exp_zones))")
    dev = 0.0
    for (i, z) in enumerate(exp_zones)
        i > length(zs) && break
        e = Float64[Float64(x) for x in jarr(z)]
        dev = max(dev, max(abs(zs[i].lo - e[1]), abs(zs[i].hi - e[2])))
    end
    if length(zs) != length(exp_pits)
        ok = false
        push!(notes, "ям $(length(zs)) != $(length(exp_pits))")
    end
    for (i, p) in enumerate(exp_pits)
        i > length(zs) && break
        d = abs(Detector.zone_center(zs[i]) - p)
        dev = max(dev, d)
        d > 1e-6 && (ok = false)
    end
    Outcome(ok, "зон $(length(zs))/$(length(exp_zones)), ям $(length(zs))/"
            * "$(length(exp_pits)), max|Δ| $(round(dev, sigdigits=2, base=10))°", notes)
end

function check_cleaner(v::AbstractDict)
    cfg = jget(v, "config")
    exp = jget(v, "expected")
    input = jget(v, "input")
    tol = jget(v, "tolerance")
    angles = jdoubles(input, "angles_deg")
    radii = jdoubles(input, "radii_mm")
    o = Cleaner.CleanerOptions(; baseline_deg = jdbl(cfg, "baseline_deg"),
        iqr_k = jdbl(cfg, "iqr_k"))
    r = Cleaner.clean_iqr(angles, radii, o)

    n = length(radii)
    ref = falses(n)
    for i in jints(exp, "mask_true_indices")
        1 <= i + 1 <= n && (ref[i + 1] = true)
    end
    extra = 0
    missing = 0
    got = 0
    for i in 1:n
        if r.mask[i]
            got += 1
            ref[i] || (extra += 1)
        elseif ref[i]
            missing += 1
        end
    end
    tol_n = max(1, floor(Int, jdbl_or(tol, "frac", 0.02) * n))
    want = jint(exp, "n_outliers")
    ok = extra <= tol_n && missing <= tol_n && abs(got - want) <= tol_n
    Outcome(ok, "выбросов $got (эталон $want), лишних $extra, пропущено $missing",
            String[])
end

function check_model(v::AbstractDict)
    cfg = jget(v, "config")
    exp = jget(v, "expected")
    tol = jget(v, "tolerance")
    input = jget(v, "input")
    notes = String[]
    ok = true

    opt = Model.ModelOptions(; n_patches = jint(cfg, "n_patches"),
        phase_deg = jdbl(cfg, "phase_deg"), deg_min = jint(cfg, "deg_min"),
        deg_max = jint(cfg, "deg_max"), overlap_train = jdbl(cfg, "overlap_train"),
        overlap_use = jdbl(cfg, "overlap_use"), deg_elbow_tol = jdbl(cfg, "deg_elbow_tol"),
        amplitude_scale = jdbl_or(cfg, "amplitude_scale", 180.0),
        coord_mode = jtext(cfg, "coord_mode"))
    pits_deg = jdoubles(cfg, "pits_deg")
    m = Model.Model(opt, pits_deg)
    if !isempty(pits_deg)
        m.pit_shape.sigma_deg = jdbl(cfg, "sigma_deg")
        m.pit_shape.core_sigma = jdbl(cfg, "pit_core_sigma")
        m.pit_shape.window_sigma = jdbl(cfg, "pit_window_sigma")
        m.pit_shape.pit_min_amp = jdbl(cfg, "pit_min_amp")
        m.pit_shape.tapering = jbool_or(cfg, "tapering", true)
    end
    Model.fit!(m, jdoubles(input, "angles_deg"), jdoubles(input, "radii_mm"))

    want_deg = jints(exp, "degrees")
    got_deg = Model.degrees(m)
    deg_ok = want_deg == got_deg
    if !deg_ok
        ok = false
        push!(notes, "степени $got_deg != $want_deg")
    end

    rel = jdbl(tol, "coefs_rel")
    flr = jdbl(tol, "coefs_abs_floor")
    max_c = 0.0
    bad_c = 0
    coefs_nodes = jarr(jget(exp, "coefs"))
    for (i, node) in enumerate(coefs_nodes)
        ref = Float64[Float64(x) for x in jarr(node)]
        got = i <= length(m.patches) ? m.patches[i].coefs : Float64[]
        if length(got) != length(ref)
            ok = false
            bad_c += 1
            continue
        end
        for j in eachindex(ref)
            max_c = max(max_c, abs(got[j] - ref[j]))
            if !near(got[j], ref[j], rel, flr)
                ok = false
                bad_c += 1
            end
        end
    end

    max_pit = 0.0
    bad_pit = 0
    for (i, node) in enumerate(jarr(jget(exp, "pit_terms")))
        ref_dx = jdoubles(node, "dx_deg")
        ref_amp = jdoubles(node, "amp")
        got_dx = i <= length(m.patches) ? m.patches[i].pit_offsets_deg : Float64[]
        got_amp = i <= length(m.patches) ? m.patches[i].pit_coefs : Float64[]
        if length(got_dx) != length(ref_dx)
            ok = false
            bad_pit += 1
            continue
        end
        for j in eachindex(ref_dx)
            da = abs(got_dx[j] - ref_dx[j])
            max_pit = max(max_pit, max(da, abs(got_amp[j] - ref_amp[j])))
            if da > 1e-9 || !near(got_amp[j], ref_amp[j], rel, flr)
                ok = false
                bad_pit += 1
            end
        end
    end

    curve = jget(exp, "curve")
    ca = jdoubles(curve, "angles_deg")
    cr = jdoubles(curve, "radii_mm")
    got = Model.eval_model(m, ca)
    max_r = 0.0
    for i in eachindex(cr)
        max_r = max(max_r, abs(got[i] - cr[i]))
    end
    max_r > jdbl(tol, "curve_mm") && (ok = false)

    detail = "степени $(deg_ok ? "совпали" : "РАСХОДЯТСЯ"), "
    detail *= "коэфф. max|Δ| $(round(max_c, sigdigits=2, base=10)) (плохих $bad_c), "
    detail *= "термины ям max|Δ| $(round(max_pit, sigdigits=2, base=10)) "
    detail *= "(плохих $bad_pit), контур max|Δ| $(round(max_r, sigdigits=2, base=10)) мм"
    Outcome(ok, detail, notes)
end

end # module Conformance
