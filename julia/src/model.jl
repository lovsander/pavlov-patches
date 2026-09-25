# Pappa.Model
#
# Модель PAPPA на Julia: патчи с адаптивной степенью по нормированной координате,
# smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
# Совпадает с референсом Python и остальными портами: тот же базис, та же политика
# степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней — ОДНИМ накоплением
# Грама в базисе Чебышёва + RMSE по явным остаткам.
#
# ВНИМАНИЕ: докстринги здесь не используются намеренно — имя модуля (Model) совпадает
# с именем типа (Model), и док-система Julia на такой коллизии падает
# (doc!: no method matching doc!(::Type, ::Binding, ::DocStr)).
module Model

using ..Signal
using ..Linalg

export ModelOptions, PitShape, Metrics, Stats, Patch, Model,
       pit_shape_deg, pit_offsets, weight, degrees, fit!, eval_part, eval_model

Base.@kwdef struct ModelOptions
    n_patches::Int = 7
    phase_deg::Float64 = 24.75
    deg_min::Int = 4
    deg_max::Int = 14
    overlap_train::Float64 = 15.0
    overlap_use::Float64 = 5.0
    deg_elbow_tol::Float64 = 0.05
    amplitude_scale::Float64 = 180.0
    coord_mode::String = "normalized"
end

Base.@kwdef mutable struct PitShape
    sigma_deg::Float64 = 3.0
    core_sigma::Float64 = 2.0
    window_sigma::Float64 = 3.2
    pit_min_amp::Float64 = 3e-3
    tapering::Bool = true
end

struct Metrics
    amplitude_mm::Float64
    mean_radius_mm::Float64
    amplitude_norm::Float64
    deg_elbow_tol::Float64
    rmse_selected_mm::Float64
    rmse_best_mm::Float64
    n_train_points::Int
end

struct Stats
    rmse_mm::Float64
    mae_mm::Float64
    max_err_mm::Float64
    correlation::Float64
end

struct Patch
    center_deg::Float64
    degree::Int
    n_points::Int
    coefs::Vector{Float64}
    pit_offsets_deg::Vector{Float64}
    pit_coefs::Vector{Float64}
    metrics::Metrics
    stats::Stats
end

mutable struct Model
    options::ModelOptions
    pit_shape::PitShape
    pits::Vector{Float64}
    patches::Vector{Patch}
    half_sector::Float64
    is_fitted::Bool

    function Model(options::ModelOptions = ModelOptions(),
                   pits_deg::AbstractVector{<:Real} = Float64[])
        new(options, PitShape(), [mod(Float64(c), 360.0) for c in pits_deg],
            Patch[], 0.0, false)
    end
end

has_pits(m::Model) = !isempty(m.pits)
half_train(m::Model) = m.half_sector + m.options.overlap_train
half_use(m::Model) = m.half_sector + m.options.overlap_use
degrees(m::Model) = [p.degree for p in m.patches]

# Оконный гаусс как функция расстояния от центра ямы (pic_shape_deg).
function pit_shape_deg(m::Model, d_deg::Real)
    d = abs(d_deg)
    sigma = m.pit_shape.sigma_deg
    base = exp(-(d * d) / (2 * sigma * sigma))
    m.pit_shape.tapering || return base
    core = m.pit_shape.core_sigma * sigma
    edge = m.pit_shape.window_sigma * sigma
    edge <= core && return base
    t = clamp((edge - d) / (edge - core), 0.0, 1.0)
    base * t * t * (3.0 - 2.0 * t)
end

# Смещения видимых ям в локальной системе патча (°).
function pit_offsets(m::Model, center_deg::Real, half_win_deg::Real)
    filter(dx -> abs(dx) <= half_win_deg,
           [Signal.circ_local(p, center_deg) for p in m.pits])
end

function weight(m::Model, d_deg::Real, half_use_deg::Real)
    d_deg <= m.half_sector && return 1.0
    d_deg <= half_use_deg && return Signal.smoothstep(
        1.0 - (d_deg - m.half_sector) / (half_use_deg - m.half_sector))
    0.0
end

# Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна не хуже
# лучшей более чем на deg_elbow_tol. Быстрая ветка (normalized) — одно накопление
# Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
function estimate_degree(m::Model, xs::AbstractVector{<:Real}, ys::AbstractVector{<:Real})
    n = length(xs)
    n < 5 && return (m.options.deg_min, 0.0, 0.0)

    degs = Int[]
    rmses = Float64[]
    best_deg = m.options.deg_min
    best = Inf

    if m.options.coord_mode == "raw"
        # Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1].
        for deg in m.options.deg_min:2:m.options.deg_max
            a = zeros(n, deg + 1)
            for i in 1:n
                p = 1.0
                for j in 1:(deg + 1)
                    a[i, deg + 2 - j] = p
                    p *= xs[i]
                end
            end
            c = Linalg.lstsq_qr(a, ys)
            sse = 0.0
            for i in 1:n
                e = Linalg.polyval(c, xs[i]) - ys[i]
                sse += e * e
            end
            r = sqrt(sse / n)
            push!(degs, deg); push!(rmses, r)
            if r < best
                best = r; best_deg = deg
            end
        end
    else
        dmax = m.options.deg_max
        p = dmax + 1
        yref = sum(Float64.(ys)) / n
        gram = zeros(p, p)
        rhs = zeros(p)
        for i in 1:n
            t = Linalg.cheb_row(xs[i], dmax)
            yc = ys[i] - yref
            for a in 1:p
                rhs[a] += t[a] * yc
                for c in a:p
                    gram[a, c] += t[a] * t[c]
                end
            end
        end
        for a in 1:p
            for c in (a + 1):p
                gram[c, a] = gram[a, c]
            end
        end
        for deg in m.options.deg_min:2:dmax
            nn = deg + 1
            c = Linalg.lstsq_qr(gram[1:nn, 1:nn], rhs[1:nn])
            sse = 0.0
            for i in 1:n
                e = Linalg.cheb_sum(c, deg, xs[i]) - (ys[i] - yref)
                sse += e * e
            end
            r = sqrt(sse / n)
            push!(degs, deg); push!(rmses, r)
            if r < best
                best = r; best_deg = deg
            end
        end
    end

    limit = best * (1.0 + m.options.deg_elbow_tol)
    sel = best_deg
    rmse_sel = best
    for (k, d) in enumerate(degs)
        if rmses[k] <= limit
            sel = d
            rmse_sel = rmses[k]
            break
        end
    end
    (sel, rmse_sel, best)
end

# Точки обучающего окна патча (локальная координата: нормированная или сырая).
function window_of(m::Model, angles::AbstractVector{<:Real},
                   radii::AbstractVector{<:Real}, center::Real)
    half = half_train(m)
    norm = m.options.coord_mode != "raw"
    xs = Float64[]
    ys = Float64[]
    for shift in (-360.0, 0.0, 360.0)
        for i in eachindex(angles)
            dx = angles[i] + shift - center
            if dx >= -half && dx <= half
                push!(xs, norm ? dx / half : dx)
                push!(ys, Float64(radii[i]))
            end
        end
    end
    (xs, ys)
end

function fit!(m::Model, angles::AbstractVector{<:Real}, radii::AbstractVector{<:Real})
    length(angles) == length(radii) || error("fit: длины не совпадают")
    length(angles) >= 10 || error("fit: слишком мало точек")

    sector = 360.0 / m.options.n_patches
    m.half_sector = sector / 2
    centers = [mod(i * sector + m.half_sector + m.options.phase_deg, 360.0)
               for i in 0:(m.options.n_patches - 1)]
    ht = half_train(m)
    empty!(m.patches)

    for c in centers
        xs, ys = window_of(m, angles, radii, c)
        n = length(xs)
        n < 5 && continue
        deg, rmse_sel, rmse_best = estimate_degree(m, xs, ys)

        offs = pit_offsets(m, c, ht)
        ncol = deg + 1 + length(offs)
        a = zeros(n, ncol)
        for i in 1:n
            p = 1.0
            for k in deg:-1:0
                a[i, k + 1] = p
                p *= xs[i]
            end
            for (j, off) in enumerate(offs)
                a[i, deg + 1 + j] = pit_shape_deg(m, abs(xs[i] * ht - off))
            end
        end
        coef = Linalg.lstsq_qr(a, ys)
        poly_coef = coef[1:(deg + 1)]

        # Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
        kept_offsets = Float64[]
        kept_coefs = Float64[]
        for (j, off) in enumerate(offs)
            max_abs = 0.0
            for i in 1:n
                d_deg = abs(xs[i] * ht - off)
                max_abs = max(max_abs, abs(coef[deg + 1 + j] * pit_shape_deg(m, d_deg)))
            end
            if max_abs >= m.pit_shape.pit_min_amp
                push!(kept_offsets, off)
                push!(kept_coefs, coef[deg + 1 + j])
            end
        end

        push!(m.patches, build_patch(m, c, deg, xs, ys, poly_coef,
                                     kept_offsets, kept_coefs, rmse_sel, rmse_best,
                                     angles, radii))
    end
    m.is_fitted = true
    m
end

# Метрики и статистика патча по его обучающему окну (полный базис).
function build_patch(m::Model, c::Real, deg::Int, xs::Vector{Float64}, ys::Vector{Float64},
                     poly_coef::Vector{Float64}, kept_offsets::Vector{Float64},
                     kept_coefs::Vector{Float64}, rmse_sel::Float64, rmse_best::Float64,
                     angles::AbstractVector{<:Real}, radii::AbstractVector{<:Real})
    n = length(xs)
    ht = half_train(m)
    sse = 0.0
    sae = 0.0
    mx = 0.0
    fit_vals = zeros(n)
    for i in 1:n
        v = Linalg.polyval(poly_coef, xs[i])
        for (j, off) in enumerate(kept_offsets)
            v += kept_coefs[j] * pit_shape_deg(m, abs(xs[i] * ht - off))
        end
        fit_vals[i] = v
        e = v - ys[i]
        sse += e * e
        sae += abs(e)
        mx = max(mx, abs(e))
    end
    nf = Float64(n)
    mf = sum(fit_vals) / nf
    my = sum(ys) / nf
    cov = 0.0
    vf = 0.0
    vy = 0.0
    for i in 1:n
        df = fit_vals[i] - mf
        dy = ys[i] - my
        cov += df * dy
        vf += df * df
        vy += dy * dy
    end
    corr = (vf > 0 && vy > 0) ? cov / sqrt(vf * vy) : 0.0

    # Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
    sec = [Float64(radii[i]) for i in eachindex(angles)
           if Signal.circ_dist(angles[i], c) <= m.half_sector]
    amp = 0.0
    mean_sec = 0.0
    if length(sec) >= 5
        amp = Signal.percentile_linear(sec, 95.0) - Signal.percentile_linear(sec, 5.0)
        mean_sec = sum(sec) / length(sec)
    end

    metrics = Metrics(amp, mean_sec, mean_sec > 0 ? amp / mean_sec : 0.0,
                      m.options.deg_elbow_tol, rmse_sel, rmse_best, n)
    stats = Stats(sqrt(sse / nf), sae / nf, mx, corr)
    Patch(c, deg, n, poly_coef, kept_offsets, kept_coefs, metrics, stats)
end

# Контур: нормированное smoothstep-смешивание патчей (partition of unity).
function eval_part(m::Model, angles::AbstractVector{<:Real}, part::String = "total")
    m.is_fitted || error("Сначала вызовите fit!")
    hu = half_use(m)
    ht = half_train(m)
    raw = m.options.coord_mode == "raw"
    out = zeros(length(angles))
    for k in eachindex(angles)
        a = angles[k]
        sum_wv = 0.0
        sum_w = 0.0
        for p in m.patches
            w = weight(m, Signal.circ_dist(a, p.center_deg), hu)
            w <= 0 && continue
            dx = Signal.circ_local(a, p.center_deg)
            x = raw ? dx : dx / ht
            v = 0.0
            part != "pit" && (v += Linalg.polyval(p.coefs, x))
            if part != "poly"
                for (j, off) in enumerate(p.pit_offsets_deg)
                    v += p.pit_coefs[j] * pit_shape_deg(m, abs(x * ht - off))
                end
            end
            sum_wv += w * v
            sum_w += w
        end
        out[k] = sum_w > 0 ? sum_wv / sum_w : 0.0
    end
    out
end

eval_model(m::Model, angles::AbstractVector{<:Real}) = eval_part(m, angles, "total")

end # module Model
