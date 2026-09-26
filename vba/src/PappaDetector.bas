Attribute VB_Name = "PappaDetector"
Option Explicit

' PAPPA VBA port -- детектор ям (трещин): безразмерный индикатор band, зоны
' превышения порога и их центры (octave/src/detector_*.m).
'
' Зоны возвращаются парой массивов lo/hi и счётчиком: массивов записей в VBA нет.

' Безразмерный индикатор ям (в "MAD-ах"):
'   band = |узкая медиана - широкая медиана|, сглаженный,
'   нормированный на свою робастную sigma.
Public Sub det_band(angles() As Double, radii() As Double, _
                    ByVal window_deg As Double, ByVal wide_deg As Double, _
                    ByVal smooth_deg As Double, _
                    ByRef out() As Double, ByRef n As Long)
    Dim narrow() As Double, wide() As Double, band() As Double
    Dim s As Double
    Dim i As Long

    n = UBound(radii)
    narrow = sig_median_filter(radii, sig_window_points(angles, window_deg))
    wide = sig_median_filter(radii, sig_window_points(angles, wide_deg))
    ReDim band(1 To n)
    For i = 1 To n
        band(i) = Abs(narrow(i) - wide(i))
    Next i
    out = sig_smooth_wrap(band, sig_window_points(angles, smooth_deg))
    s = sig_robust_sigma(out)
    If s > 1E-12 Then
        For i = 1 To n
            out(i) = out(i) / s
        Next i
    Else
        ' Гладкий профиль: разницы медиан нет, индикатор без масштаба.
        For i = 1 To n
            out(i) = 0#
        Next i
    End If
End Sub

' Непрерывные зоны по маске; углы -- по возрастанию. Зона -- пара lo/hi.
Public Sub det_mask_to_zones(angles() As Double, mask() As Boolean, ByVal min_zone_deg As Double, _
                             ByRef out_lo() As Double, ByRef out_hi() As Double, ByRef nz As Long)
    Dim d() As Double, tmp_lo() As Double, tmp_hi() As Double
    Dim step_ As Double
    Dim n As Long, i As Long, j As Long, nz0 As Long, k As Long, nkeep As Long
    Dim any_mask As Boolean
    Dim first_hi As Double, last_lo As Double

    n = UBound(angles)
    ReDim out_lo(1 To PP_MAX_ZONES)
    ReDim out_hi(1 To PP_MAX_ZONES)
    nz = 0
    any_mask = False
    For i = 1 To n
        If mask(i) Then any_mask = True
    Next i
    If Not any_mask Then Exit Sub

    If n <= 1 Then
        step_ = 1#
    Else
        ReDim d(1 To n - 1)
        For i = 1 To n - 1
            d(i) = angles(i + 1) - angles(i)
        Next i
        step_ = sig_median(d)
    End If

    ReDim tmp_lo(1 To PP_MAX_ZONES + 1)
    ReDim tmp_hi(1 To PP_MAX_ZONES + 1)
    nz0 = 0
    i = 1
    Do While i <= n
        If Not mask(i) Then
            i = i + 1
        Else
            j = i
            Do While j + 1 <= n
                If Not mask(j + 1) Then Exit Do
                j = j + 1
            Loop
            If nz0 < PP_MAX_ZONES Then
                nz0 = nz0 + 1
                tmp_lo(nz0) = angles(i) - step_ / 2#
                tmp_hi(nz0) = angles(j) + step_ / 2#
            End If
            i = j + 1
        End If
    Loop

    ' Кольцо: зона, доходящая до 360 и начинающаяся с 0, -- это ОДНА зона.
    ' Новый список: [склейка последней и первой] + зоны 2..nz0-1 (последняя
    ' исчезает), поэтому число зон уменьшается на единицу. Сначала сохраняем
    ' оба края, потом перезаписываем первую запись.
    If nz0 > 1 And mask(1) And mask(n) Then
        first_hi = tmp_hi(1)
        last_lo = tmp_lo(nz0) - 360#
        tmp_lo(1) = last_lo
        tmp_hi(1) = first_hi
        nz0 = nz0 - 1
    End If

    ' Отсечка зон уже min_zone_deg.
    nkeep = 0
    For k = 1 To nz0
        If (tmp_hi(k) - tmp_lo(k)) >= min_zone_deg Then
            nkeep = nkeep + 1
            out_lo(nkeep) = tmp_lo(k)
            out_hi(nkeep) = tmp_hi(k)
        End If
    Next k
    nz = nkeep
End Sub

' Зоны, где индикатор превышает порог k.
Public Sub det_zones(angles() As Double, values() As Double, ByVal k As Double, _
                     ByVal min_zone_deg As Double, _
                     ByRef lo() As Double, ByRef hi() As Double, ByRef nz As Long)
    Dim mask() As Boolean
    Dim n As Long, i As Long
    n = UBound(values)
    ReDim mask(1 To n)
    For i = 1 To n
        mask(i) = (values(i) > k)
    Next i
    det_mask_to_zones angles, mask, min_zone_deg, lo, hi, nz
End Sub

' Центры ям (градусы) по индикатору band.
Public Sub det_pits(angles() As Double, radii() As Double, _
                    ByVal window_deg As Double, ByVal wide_deg As Double, _
                    ByVal smooth_deg As Double, ByVal k As Double, _
                    ByVal min_zone_deg As Double, _
                    ByRef pits() As Double, ByRef n As Long)
    Dim band() As Double, lo() As Double, hi() As Double
    Dim nb As Long, nz As Long, i As Long

    det_band angles, radii, window_deg, wide_deg, smooth_deg, band, nb
    det_zones angles, band, k, min_zone_deg, lo, hi, nz
    n = nz
    If n > PP_MAX_PITS Then n = PP_MAX_PITS
    ReDim pits(1 To PP_MAX_PITS + 1)
    For i = 1 To n
        pits(i) = 0.5 * (lo(i) + hi(i))
    Next i
End Sub
