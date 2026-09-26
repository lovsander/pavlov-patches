Attribute VB_Name = "PappaLinalg"
Option Explicit

' PAPPA VBA port -- линейная алгебра: базис Чебышёва, МНК через QR
' отражениями Хаусхолдера, полиномы. Соответствует octave/src/linalg_*.m.
'
' Соглашения: матрицы -- Double (1 To m, 1 To n), векторы 1-базные.
'
' Почему не LAPACK/встроенные решатели Excel: у них своё упорядочивание
' (pivoting) и своя псевдообработка вырожденных столбцов -- коэффициенты
' разошлись бы с остальными портами сильнее, чем допускает вектор модели
' (1e-9 отн.). Здесь МНК ровно тот же, что в C/Fortran/Octave.

' Столбцы T_0(x)..T_deg_max(x) -- базис Чебышёва (x в [-1, 1]).
' n -- сколько точек массива x реально заполнено (массивы-буферы в VBA длиннее
' числа данных, поэтому размер всегда передаётся явно, как в C/Fortran).
Public Function lin_cheb_matrix(x() As Double, ByVal n As Long, ByVal deg_max As Long) As Double()
    Dim t() As Double
    Dim i As Long, k As Long
    ReDim t(1 To n, 1 To deg_max + 1)
    For i = 1 To n
        t(i, 1) = 1#
        If deg_max >= 1 Then t(i, 2) = x(i)
    Next i
    For k = 3 To deg_max + 1
        For i = 1 To n
            t(i, k) = 2# * x(i) * t(i, k - 1) - t(i, k - 2)
        Next i
    Next k
    lin_cheb_matrix = t
End Function

' Строка T_0(x)..T_deg_max(x) -- тот же рекуррентный ряд, что и в матрице.
Public Function lin_cheb_row(ByVal x As Double, ByVal deg_max As Long) As Double()
    Dim t() As Double
    Dim k As Long
    ReDim t(1 To deg_max + 1)
    t(1) = 1#
    If deg_max >= 1 Then t(2) = x
    For k = 3 To deg_max + 1
        t(k) = 2# * x * t(k - 1) - t(k - 2)
    Next k
    lin_cheb_row = t
End Function

' Сумма c_k*T_k(x) по схеме Кленшоу (устойчива к накоплению ошибки).
Public Function lin_cheb_sum(co() As Double, ByVal deg As Long, ByVal x As Double) As Double
    Dim b0 As Double, b1 As Double, b2 As Double
    Dim k As Long
    b1 = 0#
    b2 = 0#
    For k = deg To 1 Step -1
        b0 = 2# * x * b1 - b2 + co(k + 1)
        b2 = b1
        b1 = b0
    Next k
    lin_cheb_sum = x * b1 - b2 + co(1)
End Function

' Полином по схеме Горнера; коэффициенты по УБЫВАНИЮ степени (как polyfit).
Public Function lin_polyval(coefs() As Double, ByVal x As Double) As Double
    Dim k As Long
    Dim y As Double
    y = 0#
    For k = 1 To UBound(coefs)
        y = y * x + coefs(k)
    Next k
    lin_polyval = y
End Function

' Полином по строке матрицы коэффициентов (схема Горнера): coefs(row, 1..ncoef).
' Нужен там, где коэффициенты патчей лежат в общей двумерной таблице.
Public Function lin_polyval_row(coefs() As Double, ByVal row As Long, _
                                ByVal ncoef As Long, ByVal x As Double) As Double
    Dim k As Long
    Dim y As Double
    y = 0#
    For k = 1 To ncoef
        y = y * x + coefs(row, k)
    Next k
    lin_polyval_row = y
End Function

' Вход не портится (работаем с копиями a и b); m и n передаются явно, так как
' массивы-буферы в VBA длиннее числа данных.
Public Function lin_lstsq(a_in() As Double, b_in() As Double, _
                          ByVal m As Long, ByVal n As Long) As Double()
    Dim a() As Double, b() As Double, v() As Double, x() As Double
    Dim k As Long, j As Long, i As Long
    Dim nrm As Double, alpha As Double, vnorm2 As Double, cc As Double, cb As Double
    Dim s As Double, d As Double

    If m < n Then Err.Raise vbObjectError + 1, "Pappa", "lin_lstsq: need m >= n"
    a = a_in
    ReDim b(1 To m)
    For i = 1 To m
        b(i) = b_in(i)
    Next i
    ReDim v(1 To m)

    For k = 1 To n
        nrm = 0#
        For i = k To m
            nrm = nrm + a(i, k) * a(i, k)
        Next i
        nrm = Sqr(nrm)
        If nrm >= 1E-300 Then
            If a(k, k) > 0# Then
                alpha = -nrm
            Else
                alpha = nrm
            End If
            For i = 1 To m
                v(i) = 0#
            Next i
            For i = k To m
                v(i) = a(i, k)
            Next i
            v(k) = v(k) - alpha
            vnorm2 = 0#
            For i = k To m
                vnorm2 = vnorm2 + v(i) * v(i)
            Next i
            If vnorm2 >= 1E-300 Then
                For j = k To n
                    s = 0#
                    For i = k To m
                        s = s + v(i) * a(i, j)
                    Next i
                    cc = 2# * s / vnorm2
                    For i = k To m
                        a(i, j) = a(i, j) - cc * v(i)
                    Next i
                Next j
                s = 0#
                For i = k To m
                    s = s + v(i) * b(i)
                Next i
                cb = 2# * s / vnorm2
                For i = k To m
                    b(i) = b(i) - cb * v(i)
                Next i
            End If
        End If
    Next k

    ReDim x(1 To n)
    For i = 1 To n
        x(i) = 0#
    Next i
    For i = n To 1 Step -1
        s = b(i)
        For j = i + 1 To n
            s = s - a(i, j) * x(j)
        Next j
        d = a(i, i)
        If Abs(d) < 1E-300 Then Err.Raise vbObjectError + 2, "Pappa", "lin_lstsq: singular system"
        x(i) = s / d
    Next i
    lin_lstsq = x
End Function

' МНК-полином степени deg: коэффициенты по УБЫВАНИЮ степени (как np.polyfit).
Public Function lin_polyfit(xs() As Double, ys() As Double, ByVal n As Long, _
                            ByVal deg As Long) As Double()
    Dim a() As Double
    Dim i As Long, pw As Long
    ReDim a(1 To n, 1 To deg + 1)
    For i = 1 To n
        For pw = 0 To deg
            a(i, deg + 1 - pw) = xs(i) ^ pw
        Next pw
    Next i
    lin_polyfit = lin_lstsq(a, ys, n, deg + 1)
End Function
