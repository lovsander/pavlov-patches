"""
    Pappa.Signal

Сигнальные утилиты — поведение как у numpy и как в остальных портах:
медиана (чётное n — среднее двух центральных), перцентиль с линейной
интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
"""
module Signal

export median2, percentile_linear, iqr2, mad2, robust_sigma, angular_step,
       window_points, median_filter_wrap, smooth_wrap, circ_dist, circ_local, smoothstep

"""Медиана: чётное n — среднее двух центральных (numpy.median)."""
function median2(values::AbstractVector{<:Real})
    n = length(values)
    n == 0 && return 0.0
    v = sort(Float64.(values))
    n % 2 == 1 ? v[(n + 1) ÷ 2] : 0.5 * (v[n ÷ 2] + v[n ÷ 2 + 1])
end

"""Перцентиль с линейной интерполяцией (numpy.percentile)."""
function percentile_linear(values::AbstractVector{<:Real}, q::Real)
    n = length(values)
    n == 0 && return 0.0
    v = sort(Float64.(values))
    pos = (q / 100.0) * (n - 1)
    lo = floor(Int, pos) + 1                 # Julia-индексы с 1
    frac = pos - floor(pos)
    hi = min(lo + 1, n)
    v[lo] + frac * (v[hi] - v[lo])
end

function iqr2(values::AbstractVector{<:Real})
    isempty(values) && return 0.0
    percentile_linear(values, 75.0) - percentile_linear(values, 25.0)
end

function mad2(values::AbstractVector{<:Real})
    isempty(values) && return 0.0
    m = median2(values)
    median2(abs.(Float64.(values) .- m))
end

robust_sigma(values::AbstractVector{<:Real}) = 1.4826 * mad2(values)

"""Медианный шаг сетки по углам (медиана положительных разностей, иначе 1)."""
function angular_step(angles::AbstractVector{<:Real})
    length(angles) < 2 && return 1.0
    d = [angles[i] - angles[i - 1] for i in 2:length(angles)]
    d = filter(s -> s > 0, d)
    isempty(d) ? 1.0 : median2(d)
end

"""
Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная, не шире массива.

Julia `round` по умолчанию — RoundNearest (половина к чётному), то есть ровно как
Python `round()` и `math.RoundToEven` в Go; в остальных портах это приходилось
эмулировать (Math.rint, round_ties_even, RoundTiesEven, toNearestOrEven, Math.rint).
"""
function window_points(angles::AbstractVector{<:Real}, span_deg::Real)
    n = length(angles)
    n < 3 && return max(1, n)
    w = round(Int, span_deg / angular_step(angles))
    iseven(w) && (w += 1)
    w < 3 && (w = 3)
    w > n && (w = isodd(n) ? n : n - 1)
    max(3, w)
end

function _odd_window(window::Integer, n::Integer)
    w = iseven(window) ? window + 1 : window
    w < 3 && (w = 3)
    w > n && (w = isodd(n) ? n : n - 1)
    w
end

"""Медианный фильтр по кольцу (окно в точках)."""
function median_filter_wrap(x::AbstractVector{<:Real}, window::Integer)
    n = length(x)
    w = _odd_window(window, n)
    w < 3 || n < 3 ? fill(median2(x), n) : begin
        h = (w - 1) ÷ 2
        out = Vector{Float64}(undef, n)
        for i in 1:n
            out[i] = median2([x[mod(i - h + k - 1, n) + 1] for k in 0:(w - 1)])
        end
        out
    end
end

"""Скользящее среднее по кольцу (окно в точках)."""
function smooth_wrap(x::AbstractVector{<:Real}, window::Integer)
    n = length(x)
    w = _odd_window(window, n)
    (w < 3 || n < 3) && return Float64.(x)
    h = (w - 1) ÷ 2
    out = Vector{Float64}(undef, n)
    for i in 1:n
        s = 0.0
        for k in (-h):h
            s += x[mod(i + k - 1, n) + 1]
        end
        out[i] = s / w
    end
    out
end

"""Расстояние по кольцу (0..180)."""
circ_dist(a::Real, b::Real) = abs(mod(a - b + 180.0, 360.0) - 180.0)

"""Локальное смещение по кольцу (-180..180)."""
circ_local(a::Real, b::Real) = mod(a - b + 180.0, 360.0) - 180.0

function smoothstep(t::Real)
    t < 0 && return 0.0
    t > 1 && return 1.0
    t * t * (3.0 - 2.0 * t)
end

end # module Signal
