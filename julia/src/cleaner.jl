"""
    Pappa.Cleaner

Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py).
"""
module Cleaner

using ..Signal

export CleanerOptions, clean_iqr

Base.@kwdef struct CleanerOptions
    baseline_deg::Float64 = 1.0
    iqr_k::Float64 = 3.0
    max_removed_frac::Float64 = 0.5
    min_points::Int = 20
end

struct CleanResult
    mask::Vector{Bool}
    n_outliers::Int
    window::Int
end

function clean_iqr(angles::AbstractVector{<:Real}, radii::AbstractVector{<:Real},
                   o::CleanerOptions = CleanerOptions())
    n = length(radii)
    mask = falses(n)
    n < o.min_points && return CleanResult(mask, 0, 0)

    w = Signal.window_points(angles, o.baseline_deg)
    base = Signal.median_filter_wrap(radii, w)
    res = [Float64(radii[i]) - base[i] for i in 1:n]

    center = Signal.median2(res)
    spread = Signal.iqr2(res)
    denom = spread > 1e-12 ? spread : 1.0      # защита референса

    sev = [abs(r - center) / denom for r in res]
    flagged = 0
    for i in 1:n
        mask[i] = sev[i] > o.iqr_k
        mask[i] && (flagged += 1)
    end

    # Предохранитель: не выбрасываем больше max_removed_frac точек.
    cap = floor(Int, o.max_removed_frac * n)
    if cap > 0 && cap < n && flagged > cap
        kept = sort([sev[i] for i in 1:n if mask[i]])
        level = kept[end - cap + 1]
        flagged = 0
        for i in 1:n
            mask[i] = mask[i] && sev[i] >= level
            mask[i] && (flagged += 1)
        end
    end
    CleanResult(mask, flagged, w)
end

end # module Cleaner
