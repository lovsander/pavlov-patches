Attribute VB_Name = "PappaSignal"
Option Explicit

' PAPPA VBA port -- сигнальные помощники: кольцевые фильтры и робастная
' статистика. Точное соответствие Fortran-порту (fortran/src/pappa_signal.f90)
' и Octave-порту (octave/src/signal_*.m).
'
' Соглашения модуля (и всего порта):
'   * массивы ВСЕГДА 1-базные (ReDim a(1 To n)) -- как в Fortran;
'   * длина массива берётся из UBound(a), отдельный аргумент n не нужен;
'   * индексация всегда a(i), i = 1..n (не a(LBound(a) + i - 1)).
'
' ЛОВУШКИ, найденные при переносе (см. vba/README.md):
'   * Mod в VBA усекает к нулю (Mod(-1, 360) = -1), а референс считает
'     по-питоновски (359) -- поэтому весь кольцевой модуль идёт через
'     sig_mod_int/sig_mod_py (x - b * Int(x / b), Int -- это ПОЛ, а не Fix);
'   * Round в VBA банковский (Round(2.5) = 2) и формально совпадает с
'     ties-to-even, но работает по десятичному представлению, поэтому для ширин
'     окон написан свой sig_round_even с floor -- как в Fortran-порте;
'   * NaN/Inf в VBA не появятся никогда: 0/0 и 1E308*10 -- это ошибки времени
'     выполнения (11 и 6), а не значения. Поэтому защитные проверки на NaN
'     заменены явными ветками (например, нулевая сумма весов == ветка Else).

' ------------------------------------------------------------------ утилиты

' Питоновское взятие по модулю для целых: результат всегда в 0..b-1.
Public Function sig_mod_int(ByVal a As Long, ByVal b As Long) As Long
    Dim r As Long
    r = a - b * (a \ b)
    If r < 0 Then r = r + b
    sig_mod_int = r
End Function

' Питоновское взятие по модулю для Double (нужно кольцевым формулам).
Public Function sig_mod_py(ByVal x As Double, ByVal b As Double) As Double
    Dim r As Double
    r = x - b * Int(x / b)
    If r < 0# Then r = r + b
    sig_mod_py = r
End Function

' Округление половины К ЧЁТНОМУ (IEC 60559) -- как Python round() и C rint().
Public Function sig_round_even(ByVal x As Double) As Double
    Dim f As Double, d As Double
    f = Int(x)                       ' Int -- пол (Fix -- усечение к нулю)
    d = x - f
    If d > 0.5 Then
        sig_round_even = f + 1#
    ElseIf d < 0.5 Then
        sig_round_even = f
    ElseIf Int(f / 2#) = f / 2# Then ' f чётное -- ничья уходит вниз
        sig_round_even = f
    Else
        sig_round_even = f + 1#      ' ничья уходит вверх
    End If
End Function

' Ширина окна в точках: нечётная, не меньше 3 и не шире массива.
Public Function sig_odd_window(ByVal window As Long, ByVal n As Long) As Long
    Dim w As Long
    w = window
    If w Mod 2 = 0 Then w = w + 1
    If w < 3 Then w = 3
    If w > n Then
        If n Mod 2 = 1 Then
            w = n
        Else
            w = n - 1
        End If
    End If
    sig_odd_window = w
End Function

' ---------------------------------------------------------------- статистика

' Сортировка по возрастанию (Шелл) прямо в массиве: в Fortran встроенной нет,
' а в VBA нет и подходящей -- медиане важен порядок значений, не устойчивость.
Public Sub sig_sort_asc(ByRef a() As Double)
    Dim n As Long, gap As Long, i As Long, j As Long
    Dim t As Double
    n = UBound(a)
    gap = n \ 2
    Do While gap > 0
        For i = gap + 1 To n
            t = a(i)
            j = i
            Do While j > gap
                If a(j - gap) <= t Then Exit Do
                a(j) = a(j - gap)
                j = j - gap
            Loop
            a(j) = t
        Next i
        gap = gap \ 2
    Loop
End Sub

' Медиана УЖЕ отсортированного массива: для чётного n -- среднее двух
' центральных значений (как numpy.median).
Public Function sig_median_sorted(v() As Double) As Double
    Dim n As Long
    n = UBound(v)
    If n = 0 Then
        sig_median_sorted = 0#
    ElseIf n Mod 2 = 1 Then
        sig_median_sorted = v((n + 1) \ 2)
    Else
        sig_median_sorted = 0.5 * (v(n \ 2) + v(n \ 2 + 1))
    End If
End Function

' Медиана как numpy.median: сортируем копию, вход не портим.
Public Function sig_median(values() As Double) As Double
    Dim v() As Double
    v = values
    sig_sort_asc v
    sig_median = sig_median_sorted(v)
End Function

' Перцентиль с линейной интерполяцией (numpy.percentile / тип 7 у R).
' Позиция 0-based, как в numpy: pos = q/100 * (n-1).
Public Function sig_percentile(values() As Double, ByVal q As Double) As Double
    Dim v() As Double
    Dim n As Long, lo As Long, hi As Long
    Dim pos As Double, fr As Double
    n = UBound(values)
    If n = 0 Then
        sig_percentile = 0#
        Exit Function
    End If
    v = values
    sig_sort_asc v
    pos = (q / 100#) * CDbl(n - 1)
    lo = CLng(Int(pos))
    fr = pos - CDbl(lo)
    hi = lo + 1
    If hi > n - 1 Then hi = n - 1
    sig_percentile = v(lo + 1) + fr * (v(hi + 1) - v(lo + 1))
End Function

' Межквартильный размах (P75 - P25).
Public Function sig_iqr2(values() As Double) As Double
    If UBound(values) = 0 Then
        sig_iqr2 = 0#
    Else
        sig_iqr2 = sig_percentile(values, 75#) - sig_percentile(values, 25#)
    End If
End Function

' Робастная оценка масштаба: 1.4826 * MAD.
Public Function sig_robust_sigma(values() As Double) As Double
    Dim dev() As Double
    Dim n As Long, i As Long
    Dim med As Double
    n = UBound(values)
    If n = 0 Then
        sig_robust_sigma = 0#
        Exit Function
    End If
    med = sig_median(values)
    ReDim dev(1 To n)
    For i = 1 To n
        dev(i) = Abs(values(i) - med)
    Next i
    sig_robust_sigma = 1.4826 * sig_median(dev)
End Function

' Медианный шаг сетки по углам (медиана ПОЛОЖИТЕЛЬНЫХ разностей в том порядке,
' в каком они идут в массиве, иначе 1).
Public Function sig_angular_step(angles() As Double) As Double
    Dim d() As Double
    Dim n As Long, i As Long, k As Long
    n = UBound(angles)
    If n < 2 Then
        sig_angular_step = 1#
        Exit Function
    End If
    ReDim d(1 To n - 1)
    k = 0
    For i = 1 To n - 1
        If angles(i + 1) - angles(i) > 0# Then
            k = k + 1
            d(k) = angles(i + 1) - angles(i)
        End If
    Next i
    If k = 0 Then
        sig_angular_step = 1#
    Else
        ReDim Preserve d(1 To k)
        sig_angular_step = sig_median(d)
    End If
End Function

' Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная,
' не шире массива (минимум 3).
Public Function sig_window_points(angles() As Double, ByVal span_deg As Double) As Long
    Dim n As Long, w As Long
    n = UBound(angles)
    If n < 3 Then
        If n > 1 Then
            sig_window_points = n
        Else
            sig_window_points = 1
        End If
        Exit Function
    End If
    w = CLng(sig_round_even(span_deg / sig_angular_step(angles)))
    w = sig_odd_window(w, n)
    If w < 3 Then w = 3
    sig_window_points = w
End Function

' Скользящее среднее по кольцу (аналог sig_smooth_wrap): сумма делится на w
' (не mean() -- чтобы порядок суммирования совпал с остальными портами).
Public Function sig_smooth_wrap(x() As Double, ByVal window As Long) As Double()
    Dim out() As Double
    Dim n As Long, w As Long, h As Long, i As Long, j As Long, idx As Long
    Dim s As Double
    n = UBound(x)
    w = sig_odd_window(window, n)
    ReDim out(1 To n)
    If w < 3 Or n < 3 Then
        For i = 1 To n
            out(i) = x(i)
        Next i
    Else
        h = (w - 1) \ 2
        For i = 1 To n
            s = 0#
            For j = 0 To w - 1
                idx = sig_mod_int(i - h - 1 + j, n) + 1
                s = s + x(idx)
            Next j
            out(i) = s / CDbl(w)
        Next i
    End If
    sig_smooth_wrap = out
End Function

' Медианный фильтр по КОЛЬЦУ (окно в точках).
'
' Формула окна для точки i: mod(i - h - 1 + (0..w-1), n) + 1. «Минус единица»
' здесь обязательна: без неё окно съезжает на точку вправо, а с ним и весь
' детектор (конформанс-вектор vector_03 ловил сдвиг на 2 градуса).
Public Function sig_median_filter(x() As Double, ByVal window As Long) As Double()
    Dim out() As Double, buf() As Double
    Dim n As Long, w As Long, h As Long, i As Long, j As Long, idx As Long
    n = UBound(x)
    w = sig_odd_window(window, n)
    ReDim out(1 To n)
    If w < 3 Or n < 3 Then
        Dim m As Double
        m = sig_median(x)
        For i = 1 To n
            out(i) = m
        Next i
    Else
        h = (w - 1) \ 2
        ReDim buf(1 To w)
        For i = 1 To n
            For j = 0 To w - 1
                idx = sig_mod_int(i - h - 1 + j, n) + 1
                buf(j + 1) = x(idx)
            Next j
            sig_sort_asc buf
            out(i) = sig_median_sorted(buf)
        Next i
    End If
    sig_median_filter = out
End Function

' Расстояние по кольцу (0..180 градусов).
Public Function sig_circ_dist(ByVal a As Double, ByVal b As Double) As Double
    sig_circ_dist = Abs(sig_mod_py(a - b + 180#, 360#) - 180#)
End Function

' Локальное смещение по кольцу (-180..180 градусов).
Public Function sig_circ_local(ByVal a As Double, ByVal b As Double) As Double
    sig_circ_local = sig_mod_py(a - b + 180#, 360#) - 180#
End Function

' Сглаживающая ступенька 3t^2 - 2t^3 с насыщением на краях.
Public Function sig_smoothstep(ByVal t As Double) As Double
    If t < 0# Then
        sig_smoothstep = 0#
    ElseIf t > 1# Then
        sig_smoothstep = 1#
    Else
        sig_smoothstep = t * t * (3# - 2# * t)
    End If
End Function
