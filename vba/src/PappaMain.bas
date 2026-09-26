Attribute VB_Name = "PappaMain"
Option Explicit

' PAPPA VBA port -- точка входа «порт грузится» (аналог smoke-блока
' fortran/build_fortran.ps1). build_vba.ps1 вызывает её, когда ключей нет: так
' проверяется вся цепочка COM -> VBE -> VBA до всякой арифметики.

Public Function Smoke() As String
    Dim a() As Double, f() As Double
    Dim i As Long, dev As Double, s As String

    s = "VBA port PAPPA: language " & PORT_LANGUAGE & ", pappa " & PORT_VERSION
    s = s & vbLf & "  modules: PappaKinds, PappaSignal, PappaMain (Excel " & Application.Version & ")"

    ReDim a(1 To 72)
    For i = 1 To 72
        a(i) = 50# + 0.4 * Sin(CDbl(i - 1) * 3.141592653589793 / 36#)
    Next i

    f = sig_median_filter(a, 5)
    dev = 0#
    For i = 1 To 72
        If Abs(a(i) - f(i)) > dev Then dev = Abs(a(i) - f(i))
    Next i

    s = s & vbLf & "  signal: median " & Str(sig_median(a)) & ", iqr " & Str(sig_iqr2(a))
    s = s & vbLf & "  signal: median filter(5) max|d| " & Str(dev)
    s = s & vbLf & "  signal: circ_dist(359, 1) " & Str(sig_circ_dist(359#, 1#)) _
          & ", circ_local(359, 1) " & Str(sig_circ_local(359#, 1#))
    s = s & vbLf & "  signal: round_even 2.5 -> " & Str(sig_round_even(2.5)) _
          & ", 3.5 -> " & Str(sig_round_even(3.5))
    s = s & vbLf & "  signal: window_points(1 deg, step 0.05) " & Str(sig_window_points(a, 1#))
    s = s & vbLf & SmokeFit()

    Smoke = s
End Function

' Дымовой прогон численного ядра: синтетический профиль (как в остальных
' портах), обучение модели и проверка контура. Гоняется обычной сборкой, чтобы
' ошибки в модели/линалге ловились ещё до появления JSON и CSV.
Public Function SmokeFit() As String
    Dim a() As Double, r() As Double, y() As Double, d() As Long
    Dim i As Long, n As Long
    Dim dev As Double, s As String

    n = 360
    ReDim a(1 To n)
    ReDim r(1 To n)
    For i = 1 To n
        a(i) = CDbl(i - 1)
        r(i) = 50# + 0.4 * Sin(a(i) * 3.141592653589793 / 180#)
    Next i

    mdl_new
    mdl_fit a, r, n
    y = mdl_eval(a)
    dev = 0#
    For i = 1 To n
        If Abs(y(i) - r(i)) > dev Then dev = Abs(y(i) - r(i))
    Next i
    d = mdl_degrees()
    s = "smoke fit: " & Str(mdl_npatch()) & " patches, max|d| " & Str(dev) & " mm, degrees"
    For i = 1 To UBound(d)
        s = s & " " & d(i)
    Next i
    SmokeFit = s
End Function
