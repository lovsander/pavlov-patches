Attribute VB_Name = "PappaCsv"
Option Explicit

' PAPPA VBA port -- чтение пайплайн-CSV по заголовку (как python/synthetic_data.csv):
' колонки section_id, height_mm, angle_deg, radius_mm.
'
' Точки группируются по section_id в порядке ПОЯВЛЕНИЯ в файле (как в c/emit.c),
' а не по порядку сортировки; внутри сечения сортировка по углу идёт отдельно
' (устойчивая вставка, как sort_section в C).
'
' Как и в C, точка сверх PP_MAX_POINTS молча отбрасывается, а сечений больше 64
' не заводится. Возврата структур в VBA нет, поэтому разделы живут в модульных
' массивах, а наружу торчат аксессоры.

Private Const CSV_MAX_SECTIONS As Long = 64

Private m_nsec As Long
Private m_id() As Long
Private m_height() As Double
Private m_n() As Long
Private m_angles() As Double            ' (1 To nsec, 1 To PP_MAX_POINTS)
Private m_radii() As Double

Public Function csv_load_sections(ByVal path As String) As Long
    Dim lines() As String
    Dim fields() As String
    Dim nlines As Long, ncol As Long
    Dim i_sec As Long, i_h As Long, i_a As Long, i_r As Long
    Dim i As Long, k As Long, idx As Long
    Dim sid As Long

    io_read_lines path, lines, nlines
    If nlines < 2 Then Err.Raise vbObjectError + 30, "Pappa", "CSV пустой: " & path

    fields = Split(lines(1), ",")
    ncol = UBound(fields) - LBound(fields) + 1
    i_sec = -1
    i_h = -1
    i_a = -1
    i_r = -1
    For k = 0 To ncol - 1
        If Left$(fields(k), 10) = "section_id" Then i_sec = k
        If Left$(fields(k), 9) = "height_mm" Then i_h = k
        If Left$(fields(k), 9) = "angle_deg" Then i_a = k
        If Left$(fields(k), 9) = "radius_mm" Then i_r = k
    Next k
    If i_sec < 0 Or i_h < 0 Or i_a < 0 Or i_r < 0 Then
        Err.Raise vbObjectError + 31, "Pappa", _
            "в заголовке нет колонок section_id/height_mm/angle_deg/radius_mm: " & path
    End If

    m_nsec = 0
    ReDim m_id(1 To CSV_MAX_SECTIONS)
    ReDim m_height(1 To CSV_MAX_SECTIONS)
    ReDim m_n(1 To CSV_MAX_SECTIONS)
    ReDim m_angles(1 To CSV_MAX_SECTIONS, 1 To PP_MAX_POINTS)
    ReDim m_radii(1 To CSV_MAX_SECTIONS, 1 To PP_MAX_POINTS)

    For i = 2 To nlines
        If Len(Trim$(lines(i))) > 0 Then
            fields = Split(lines(i), ",")
            ncol = UBound(fields) - LBound(fields) + 1
            If i_sec < ncol And i_h < ncol And i_a < ncol And i_r < ncol Then
                If Len(fields(i_sec)) > 0 Then
                    sid = CLng(Val(fields(i_sec)))
                    idx = 0
                    For k = 1 To m_nsec
                        If m_id(k) = sid Then
                            idx = k
                            Exit For
                        End If
                    Next k
                    If idx = 0 Then
                        If m_nsec < CSV_MAX_SECTIONS Then
                            m_nsec = m_nsec + 1
                            idx = m_nsec
                            m_id(idx) = sid
                            m_height(idx) = Val(fields(i_h))
                            m_n(idx) = 0
                        End If
                    End If
                    If idx > 0 Then
                        If m_n(idx) < PP_MAX_POINTS Then
                            m_n(idx) = m_n(idx) + 1
                            m_angles(idx, m_n(idx)) = Val(fields(i_a))
                            m_radii(idx, m_n(idx)) = Val(fields(i_r))
                        End If
                    End If
                End If
            End If
        End If
    Next i
    csv_load_sections = m_nsec
End Function

Public Function csv_nsec() As Long
    csv_nsec = m_nsec
End Function

Public Function csv_section_id(ByVal i As Long) As Long
    csv_section_id = m_id(i)
End Function

Public Function csv_section_height(ByVal i As Long) As Double
    csv_section_height = m_height(i)
End Function

Public Function csv_section_n(ByVal i As Long) As Long
    csv_section_n = m_n(i)
End Function

' Точки сечения в отдельные массивы (1-базные, длина = число точек).
Public Sub csv_section_points(ByVal i As Long, ByRef angles() As Double, ByRef radii() As Double)
    Dim j As Long
    ReDim angles(1 To m_n(i))
    ReDim radii(1 To m_n(i))
    For j = 1 To m_n(i)
        angles(j) = m_angles(i, j)
        radii(j) = m_radii(i, j)
    Next j
End Sub

' Сортировка точек сечения по углу (устойчивая вставка, как sort_section в C):
' для равных углов сохраняется исходный порядок строк CSV.
Public Sub csv_sort_section(ByVal i As Long)
    Dim j As Long, k As Long
    Dim ka As Double, kr As Double
    For j = 2 To m_n(i)
        ka = m_angles(i, j)
        kr = m_radii(i, j)
        k = j - 1
        Do While k >= 1
            If m_angles(i, k) <= ka Then Exit Do
            m_angles(i, k + 1) = m_angles(i, k)
            m_radii(i, k + 1) = m_radii(i, k)
            k = k - 1
        Loop
        m_angles(i, k + 1) = ka
        m_radii(i, k + 1) = kr
    Next j
End Sub
