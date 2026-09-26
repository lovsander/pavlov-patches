Attribute VB_Name = "PappaPipeline"
Option Explicit

' PAPPA VBA port -- пайплайн: CSV -> папка образца (как c/emit.c + c/document.c).
'
' Параметры метода зафиксированы теми же числами, что в остальных портах:
'   7 патчей, phase 24.75, степени 4..14, overlap_train 15, overlap_use 5,
'   deg_elbow_tol 0.05, очистка iqr (baseline 1, k 3, не больше половины точек),
'   детектор band (окна 1/10/2, k 5.5, min_zone 2),
'   форма ям (sigma 3, core 2, window 3.2, pit_min_amp 3e-3, tapering).

Public Function pappa_pipeline_run(ByVal inputCsv As String, ByVal outDir As String, ByVal sampleName As String) As String
    Const N_PATCHES As Long = 7
    Const DEG_MIN As Long = 4
    Const DEG_MAX As Long = 14
    Const PHASE_DEG As Double = 24.75
    Const OVERLAP_TRAIN As Double = 15#
    Const OVERLAP_USE As Double = 5#
    Const ELBOW_TOL As Double = 0.05
    Const CL_BASE As Double = 1#
    Const CL_K As Double = 3#
    Const CL_MAX_REMOVE As Double = 0.5
    Const CL_MIN_POINTS As Long = 20
    Const DET_WIN As Double = 1#
    Const DET_WIDE As Double = 10#
    Const DET_SMOOTH As Double = 2#
    Const DET_K As Double = 5.5
    Const DET_MINZONE As Double = 2#
    Const PIT_SIGMA As Double = 3#
    Const PIT_CORE As Double = 2#
    Const PIT_WINDOW As Double = 3.2
    Const PIT_MINAMP As Double = 0.003

    Dim nsec As Long, si As Long, cn As Long, npits As Long, npts As Long
    Dim angles() As Double, radii() As Double, ca() As Double, cr() As Double
    Dim mask() As Boolean, pits() As Double, d() As Long
    Dim n_out As Long, win As Long
    Dim sec_dir As String, s As String
    Dim t0 As Double, fit_ms As Double
    Dim any_pits As Boolean
    Dim sec_id() As Long, sec_h() As Double, sec_np() As Long, sec_no() As Long
    Dim i As Long

    nsec = csv_load_sections(inputCsv)
    If nsec = 0 Then Err.Raise vbObjectError + 40, "Pappa", "в CSV нет сечений: " & inputCsv

    io_make_dir outDir
    sec_dir = outDir & "\sections"
    io_make_dir sec_dir

    ReDim sec_id(1 To nsec)
    ReDim sec_h(1 To nsec)
    ReDim sec_np(1 To nsec)
    ReDim sec_no(1 To nsec)

    s = "VBA pipeline: " & CStr(nsec) & " sections from " & inputCsv

    For si = 1 To nsec
        csv_sort_section si
        csv_section_points si, angles, radii
        npts = UBound(radii)

        ' --- авто-очистка выбросов (как в C-порте: iqr, baseline 1 градус) ---
        cln_clean_iqr angles, radii, CL_BASE, CL_K, CL_MAX_REMOVE, CL_MIN_POINTS, _
                      mask, n_out, win
        cn = 0
        ReDim ca(1 To npts)
        ReDim cr(1 To npts)
        For i = 1 To npts
            If Not mask(i) Then
                If cn < PP_MAX_POINTS Then
                    cn = cn + 1
                    ca(cn) = angles(i)
                    cr(cn) = radii(i)
                End If
            End If
        Next i
        If cn < 10 Then
            Err.Raise vbObjectError + 41, "Pappa", _
                "после очистки в сечении " & CStr(csv_section_id(si)) & " осталось " & CStr(cn) & " точек"
        End If
        ReDim Preserve ca(1 To cn)
        ReDim Preserve cr(1 To cn)

        ' --- ямы: детектор band по очищенным данным ---
        det_pits ca, cr, DET_WIN, DET_WIDE, DET_SMOOTH, DET_K, DET_MINZONE, pits, npits

        ' --- модель ---
        mdl_new
        mdl_options N_PATCHES, PHASE_DEG, DEG_MIN, DEG_MAX, OVERLAP_TRAIN, OVERLAP_USE, _
                    ELBOW_TOL, "normalized"
        If npits > 0 Then
            mdl_pit_shape_options PIT_SIGMA, PIT_CORE, PIT_WINDOW, PIT_MINAMP, True
            mdl_set_pits pits, npits
            any_pits = True
        End If

        t0 = Timer
        mdl_fit ca, cr, cn
        fit_ms = (Timer - t0) * 1000#
        If fit_ms < 0# Then fit_ms = 0#       ' Timer сбрасывается в полночь

        io_write_text sec_dir & "\" & Format$(si - 1, "00") & ".pappa.json", _
            document_section_text(csv_section_id(si), csv_section_height(si), "csv", _
                                  "сечение из CSV", npts, n_out, fit_ms)

        sec_id(si) = csv_section_id(si)
        sec_h(si) = csv_section_height(si)
        sec_np(si) = npts
        sec_no(si) = n_out

        d = mdl_degrees()
        s = s & vbLf & "  section " & CStr(sec_id(si)) & ": n=" & CStr(npts) & _
                " used=" & CStr(cn) & " outliers=" & CStr(n_out) & " pits=" & CStr(npits) & _
                " deg=" & mdl_deg_list(d)
    Next si

    io_write_text outDir & "\sample.json", _
        document_manifest_text(sampleName, "PAPPA VBA port", inputCsv, CL_BASE, CL_K, any_pits, _
                               sec_id, sec_h, sec_np, sec_no, nsec)

    pappa_pipeline_run = s & vbLf & "sample written: " & outDir & " (" & CStr(nsec) & " sections)"
End Function

Private Function mdl_deg_list(d() As Long) As String
    Dim t As String
    Dim i As Long
    For i = 1 To UBound(d)
        If i > 1 Then t = t & ","
        t = t & CStr(d(i))
    Next i
    mdl_deg_list = t
End Function
