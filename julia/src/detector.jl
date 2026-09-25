"""
    Pappa.Detector

Детектор ям (трещин) — повторение python/pappa/analysis/zones.py:
  band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
  нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
  зоны = участки, где индикатор > k, длиной не короче min_zone_deg.
"""
module Detector

using ..Signal

export DetectorOptions, band_indicator, mask_to_zones, zones, pits

Base.@kwdef struct DetectorOptions
    window_deg::Float64 = 1.0
    wide_deg::Float64 = 10.0
    smooth_deg::Float64 = 2.0
    k::Float64 = 5.5
    min_zone_deg::Float64 = 2.0
end

struct Zone
    lo::Float64
    hi::Float64
end

zone_center(z::Zone) = 0.5 * (z.lo + z.hi)

function band_indicator(angles::AbstractVector{<:Real}, radii::AbstractVector{<:Real},
                        o::DetectorOptions = DetectorOptions())
    n = length(radii)
    narrow = Signal.median_filter_wrap(radii, Signal.window_points(angles, o.window_deg))
    wide = Signal.median_filter_wrap(radii, Signal.window_points(angles, o.wide_deg))
    band = [abs(narrow[i] - wide[i]) for i in 1:n]

    out = Signal.smooth_wrap(band, Signal.window_points(angles, o.smooth_deg))
    s = Signal.robust_sigma(out)
    if s > 1e-12
        out ./= s
    else
        out .= 0.0
    end
    out
end

"""Непрерывные зоны по маске (углы — по возрастанию)."""
function mask_to_zones(angles::AbstractVector{<:Real}, mask::AbstractVector{Bool},
                       o::DetectorOptions = DetectorOptions())
    n = length(angles)
    any(mask) || return Zone[]

    diffs = [Float64(angles[i] - angles[i - 1]) for i in 2:n]
    step = isempty(diffs) ? 1.0 : Signal.median2(diffs)

    zones = Zone[]
    i = 1
    while i <= n
        if !mask[i]
            i += 1
            continue
        end
        j = i
        while j + 1 <= n && mask[j + 1]
            j += 1
        end
        push!(zones, Zone(angles[i] - step / 2, angles[j] + step / 2))
        i = j + 1
    end

    # Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
    if length(zones) > 1 && mask[1] && mask[n]
        first_z = zones[1]
        last_z = zones[end]
        merged = Zone[Zone(last_z.lo - 360.0, first_z.hi)]
        append!(merged, zones[2:(end - 1)])
        zones = merged
    end

    filter(z -> z.hi - z.lo >= o.min_zone_deg, zones)
end

function zones(angles::AbstractVector{<:Real}, values::AbstractVector{<:Real},
               o::DetectorOptions = DetectorOptions())
    mask_to_zones(angles, [v > o.k for v in values], o)
end

"""Центры ям (°)."""
function pits(angles::AbstractVector{<:Real}, radii::AbstractVector{<:Real},
              o::DetectorOptions = DetectorOptions())
    band = band_indicator(angles, radii, o)
    [zone_center(z) for z in zones(angles, band, o)]
end

end # module Detector
