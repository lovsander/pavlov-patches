Attribute VB_Name = "PappaCleaner"
Option Explicit

' PAPPA VBA port -- авто-очистка выбросов (метод "iqr").
'
' Снимаем форму профиля медианным фильтром по кольцу, считаем остаток и его
' робастный масштаб; порог -- усы Тьюки (k * IQR). Повторяет
' AutoOutlierCleaner референса Python (octave/src/cleaner_*.m).
'
' Результата-структуры в VBA нет, поэтому маска и счётчики возвращаются через
' ByRef-аргументы (как pappa.h возвращает mask и n_outliers в C-порте).

Public Sub cln_clean_iqr(angles() As Double, radii() As Double, _
                         ByVal baseline_deg As Double, ByVal iqr_k As Double, _
                         ByVal max_removed_frac As Double, ByVal min_points As Long, _
                         ByRef mask() As Boolean, ByRef n_outliers As Long, _
                         ByRef window As Long)
    Dim base() As Double, r() As Double, sev() As Double, kept() As Double
    Dim n As Long, w As Long, i As Long, k As Long, flagged As Long, cap As Long
    Dim center As Double, spread As Double, denom As Double, level As Double

    n = UBound(radii)
    ReDim mask(1 To n)
    n_outliers = 0
    window = 0
    If n < min_points Then Exit Sub

    w = sig_window_points(angles, baseline_deg)
    window = w
    base = sig_median_filter(radii, w)
    ReDim r(1 To n)
    For i = 1 To n
        r(i) = radii(i) - base(i)
    Next i

    center = sig_median(r)
    spread = sig_iqr2(r)
    If spread > 1E-12 Then
        denom = spread
    Else
        ' Защита референса: при нулевом остатке порог становится 3 мм, то есть
        ' очиститель на идеально гладких данных молча отключается.
        denom = 1#
    End If

    ReDim sev(1 To n)
    flagged = 0
    For i = 1 To n
        sev(i) = Abs(r(i) - center) / denom
        mask(i) = (sev(i) > iqr_k)
        If mask(i) Then flagged = flagged + 1
    Next i

    ' Предохранитель: не выбрасываем больше max_removed_frac точек.
    cap = CLng(Int(max_removed_frac * CDbl(n)))
    If cap > 0 And cap < n And flagged > cap Then
        ReDim kept(1 To flagged)
        k = 0
        For i = 1 To n
            If mask(i) Then
                k = k + 1
                kept(k) = sev(i)
            End If
        Next i
        sig_sort_asc kept
        level = kept(UBound(kept) - cap + 1)
        flagged = 0
        For i = 1 To n
            If mask(i) Then
                mask(i) = (sev(i) >= level)
                If mask(i) Then flagged = flagged + 1
            End If
        Next i
    End If
    n_outliers = flagged
End Sub
