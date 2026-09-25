"""
    Pappa.Linalg

Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени.
"""
module Linalg

export lstsq_qr, polyval, polyfit, cheb_row, cheb_sum

"""Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится."""
function lstsq_qr(a_in::AbstractMatrix{<:Real}, b_in::AbstractVector{<:Real})
    m, n = size(a_in)
    m == 0 && error("lstsq: пустая матрица")
    length(b_in) == m || error("lstsq: длины A и b не совпадают")
    m >= n || error("lstsq: нужно m >= n")

    a = Matrix{Float64}(a_in)
    b = Float64.(b_in)

    for k in 1:n
        norm = 0.0
        for i in k:m
            norm += a[i, k]^2
        end
        norm = sqrt(norm)
        norm < 1e-300 && continue

        alpha = a[k, k] > 0 ? -norm : norm
        v = zeros(m)
        for i in k:m
            v[i] = a[i, k]
        end
        v[k] -= alpha
        vnorm2 = 0.0
        for i in k:m
            vnorm2 += v[i]^2
        end
        vnorm2 < 1e-300 && continue

        for j in k:n
            s = 0.0
            for i in k:m
                s += v[i] * a[i, j]
            end
            c = 2 * s / vnorm2
            for i in k:m
                a[i, j] -= c * v[i]
            end
        end
        sb = 0.0
        for i in k:m
            sb += v[i] * b[i]
        end
        cb = 2 * sb / vnorm2
        for i in k:m
            b[i] -= cb * v[i]
        end
    end

    x = zeros(n)
    for i in n:-1:1
        s = b[i]
        for j in (i + 1):n
            s -= a[i, j] * x[j]
        end
        d = a[i, i]
        abs(d) < 1e-300 && error("lstsq: вырожденная система")
        x[i] = s / d
    end
    x
end

"""Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval)."""
function polyval(coefs::AbstractVector{<:Real}, x::Real)
    r = 0.0
    for c in coefs
        r = r * x + c
    end
    r
end

function polyfit(xs::AbstractVector{<:Real}, ys::AbstractVector{<:Real}, deg::Integer)
    m = length(xs)
    n = deg + 1
    a = zeros(m, n)
    for i in 1:m
        p = 1.0
        for j in 1:n
            a[i, n - j + 1] = p
            p *= xs[i]
        end
    end
    lstsq_qr(a, ys)
end

"""T_0(x)..T_deg_max(x) — базис Чебышёва (x ∈ [-1, 1])."""
function cheb_row(x::Real, deg_max::Integer)
    t = zeros(deg_max + 1)
    t[1] = 1.0
    deg_max >= 1 && (t[2] = x)
    for k in 3:(deg_max + 1)
        t[k] = 2 * x * t[k - 1] - t[k - 2]
    end
    t
end

"""Σ c_k·T_k(x) по схеме Кленшоу (устойчиво)."""
function cheb_sum(c::AbstractVector{<:Real}, deg::Integer, x::Real)
    b1 = 0.0
    b2 = 0.0
    for k in deg:-1:1
        b0 = 2 * x * b1 - b2 + c[k + 1]
        b2 = b1
        b1 = b0
    end
    x * b1 - b2 + c[1]
end

end # module Linalg
