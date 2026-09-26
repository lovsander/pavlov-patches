Attribute VB_Name = "PappaConformance"
Option Explicit

' PAPPA VBA port -- проверка по конформанс-векторам (spec/conformance/vectors).
'
' Допуски -- те же, что у C++/Go/C/Fortran: контур 1e-6 мм, коэффициенты
' max(coefs_abs_floor, coefs_rel*|c_ожид|), отступы фичера ям 1e-9 градуса,
' центры ям 1e-6 градуса, детектор/очистка -- доля (frac) от числа точек.
'
' Отчёт возвращается строкой, последняя строка -- "RESULT: OK" или
' "RESULT: FAIL n": скрипт сборки по ней выставляет код возврата (ошибку VBA не
' бросаем, иначе COM показал бы только её текст, а отчёт бы потерялся).

Public Function pappa_conformance_run(ByVal vectorDir As String) As String
    Dim names() As String
    Dim n As Long, i As Long, bad As Long
    Dim t As String, kind As String
    Dim ok As Boolean, detail As String
    Dim root As Long

    If Not io_dir_exists(vectorDir) Then
        Err.Raise vbObjectError + 50, "Pappa", "нет каталога векторов: " & vectorDir
    End If
    n = conf_list_json(vectorDir, names)
    If n = 0 Then Err.Raise vbObjectError + 51, "Pappa", "в каталоге нет *.json: " & vectorDir

    t = "VBA conformance: " & CStr(n) & " vectors from " & vectorDir
    io_trace "conformance: " & CStr(n) & " vectors"
    For i = 1 To n
        io_trace "vector " & names(i)
        root = json_parse(io_read_text(vectorDir & "\" & names(i)))
        If root = 0 Then
            ok = False
            detail = "JSON не разобран: " & json_error()
            io_trace "  json error: " & json_error()
        Else
            kind = jp_path_str(root, "kind")
            io_trace "  kind=" & kind
            If kind = "model" Then
                ok = conf_model(root, detail)
            ElseIf kind = "detector" Then
                ok = conf_detector(root, detail)
            ElseIf kind = "cleaner" Then
                ok = conf_cleaner(root, detail)
            Else
                ok = False
                detail = "неизвестный kind: " & kind
            End If
        End If
        If Not ok Then bad = bad + 1
        t = t & vbLf & "  " & names(i) & "  " & IIf(ok, "OK  ", "FAIL") & " " & detail
    Next i
    If bad = 0 Then
        t = t & vbLf & "RESULT: OK"
    Else
        t = t & vbLf & "RESULT: FAIL " & CStr(bad)
    End If
    pappa_conformance_run = t
End Function

' Список *.json каталога, отсортированный по имени (Dir отдаёт как попало).
' ЛОВУШКА: имя параметра `dir` затеняет встроенную функцию Dir (Dir$ в VBA есть,
' но затеняется так же) -- компилятор читает dir$( ... ) как скаляр с суффиксом
' типа и выдаёт "Expected array". Поэтому параметр называется folder.
Private Function conf_list_json(ByVal folder As String, ByRef names() As String) As Long
    Dim nm As String, tmp As String
    Dim n As Long, i As Long, j As Long
    Dim cap As Long

    n = 0
    cap = 16
    ReDim names(1 To cap)
    nm = Dir(folder & "\*.json")
    Do While Len(nm) > 0
        n = n + 1
        If n > cap Then
            cap = cap * 2
            ReDim Preserve names(1 To cap)
        End If
        names(n) = nm
        nm = Dir
    Loop
    For i = 2 To n
        tmp = names(i)
        j = i - 1
        Do While j >= 1
            If names(j) <= tmp Then Exit Do
            names(j + 1) = names(j)
            j = j - 1
        Loop
        names(j + 1) = tmp
    Next i
    conf_list_json = n
End Function

' Короткая научная запись для отчёта (в русской локали Format$ даёт запятую).
Private Function conf_sci(ByVal v As Double) As String
    Dim s As String
    If v = 0# Then
        conf_sci = "0"
        Exit Function
    End If
    s = Format$(v, "0.0E+00")
    conf_sci = Replace(s, ",", ".")
End Function

' --------------------------------------------------------------- детектор

Private Function conf_detector(ByVal root As Long, ByRef detail As String) As Boolean
    Dim cfg As Long, exp As Long, inp As Long
    Dim angles() As Double, radii() As Double, band() As Double
    Dim lo() As Double, hi() As Double, pits() As Double
    Dim n As Long, nz As Long, nb As Long, npits As Long
    Dim want_zones As Long, want_pits As Long
    Dim dev As Double, d As Double, pits_dev As Double
    Dim ok As Boolean
    Dim i As Long
    Dim znode As Long, pnode As Long, pair As Long

    cfg = jp_member(root, "config")
    exp = jp_member(root, "expected")
    inp = jp_member(root, "input")
    If cfg = 0 Or exp = 0 Or inp = 0 Then
        detail = "в векторе нет config/expected/input"
        Exit Function
    End If

    jp_num_array jp_path(inp, "angles_deg"), angles, n
    jp_num_array jp_path(inp, "radii_mm"), radii, n

    det_band angles, radii, jp_path_num(cfg, "window_deg"), jp_path_num(cfg, "wide_deg"), _
             jp_path_num(cfg, "smooth_deg"), band, nb
    det_zones angles, band, jp_path_num(cfg, "k"), jp_path_num(cfg, "min_zone_deg"), _
              lo, hi, nz

    znode = jp_path(exp, "zones_deg")
    pnode = jp_path(exp, "pits_deg")
    want_zones = jp_count(znode)
    want_pits = jp_count(pnode)

    ok = (nz = want_zones)
    dev = 0#
    For i = 1 To want_zones
        If i <= nz Then
            pair = jp_child(znode, i)
            d = Abs(lo(i) - jp_num(jp_child(pair, 1)))
            If d > dev Then dev = d
            d = Abs(hi(i) - jp_num(jp_child(pair, 2)))
            If d > dev Then dev = d
        End If
    Next i

    ' Центры ям -- середины зон (как det_pits), допуск 1e-6 градуса.
    ReDim pits(1 To PP_MAX_PITS + 1)
    npits = nz
    If npits > PP_MAX_PITS Then npits = PP_MAX_PITS
    For i = 1 To npits
        pits(i) = 0.5 * (lo(i) + hi(i))
    Next i
    pits_dev = 0#
    ok = ok And (npits = want_pits)
    For i = 1 To want_pits
        If i <= npits Then
            d = Abs(pits(i) - jp_num(jp_child(pnode, i)))
            If d > pits_dev Then pits_dev = d
            If d > 0.000001 Then ok = False
        End If
    Next i

    detail = "зон " & CStr(nz) & "/" & CStr(want_zones) & ", ям " & CStr(npits) & "/" & _
             CStr(want_pits) & ", max|d| зон " & conf_sci(dev) & "гр, ям " & _
             conf_sci(pits_dev) & "гр"
    conf_detector = ok
End Function

' ---------------------------------------------------------------- очистка

Private Function conf_cleaner(ByVal root As Long, ByRef detail As String) As Boolean
    Dim cfg As Long, exp As Long, tol As Long, inp As Long
    Dim angles() As Double, radii() As Double
    Dim mask() As Boolean, ref() As Boolean
    Dim n As Long, i As Long, idx As Long, idxs As Long
    Dim n_out As Long, win As Long
    Dim want_n As Long, frac As Double, tol_n As Long
    Dim extra As Long, missing As Long

    cfg = jp_member(root, "config")
    exp = jp_member(root, "expected")
    tol = jp_member(root, "tolerance")
    inp = jp_member(root, "input")
    If cfg = 0 Or exp = 0 Or tol = 0 Or inp = 0 Then
        detail = "в векторе нет config/expected/tolerance/input"
        Exit Function
    End If

    jp_num_array jp_path(inp, "angles_deg"), angles, n
    jp_num_array jp_path(inp, "radii_mm"), radii, n

    cln_clean_iqr angles, radii, jp_path_num(cfg, "baseline_deg"), jp_path_num(cfg, "iqr_k"), _
                  0.5, 20, mask, n_out, win

    want_n = CLng(jp_path_num(exp, "n_outliers"))
    frac = jp_path_num(tol, "frac")
    If frac <= 0# Then frac = 0.02
    tol_n = CLng(frac * CDbl(n))
    If tol_n < 1 Then tol_n = 1

    ' Эталонная маска из индексов (в векторе они 0-based).
    ReDim ref(1 To n)
    idxs = jp_count(jp_path(exp, "mask_true_indices"))
    For i = 1 To idxs
        idx = CLng(jp_num(jp_child(jp_path(exp, "mask_true_indices"), i)))
        If idx >= 0 And idx < n Then ref(idx + 1) = True
    Next i

    extra = 0
    missing = 0
    For i = 1 To n
        If mask(i) Then
            If Not ref(i) Then extra = extra + 1
        Else
            If ref(i) Then missing = missing + 1
        End If
    Next i

    detail = "выбросов " & CStr(n_out) & " (эталон " & CStr(want_n) & "), лишних " & _
             CStr(extra) & ", пропущено " & CStr(missing) & ", допуск " & CStr(tol_n)
    conf_cleaner = (extra <= tol_n) And (missing <= tol_n) And (Abs(n_out - want_n) <= tol_n)
End Function

' ------------------------------------------------------------------ модель

Private Function conf_model(ByVal root As Long, ByRef detail As String) As Boolean
    Dim cfg As Long, exp As Long, tol As Long, inp As Long
    Dim angles() As Double, radii() As Double, pits() As Double
    Dim d() As Long
    Dim n As Long, npits As Long, i As Long, p As Long, k As Long, nc As Long
    Dim rel As Double, flr As Double, tol_curve As Double, allowed As Double
    Dim max_c As Double, max_pit As Double, max_r As Double, max_dx As Double
    Dim got As Double, want As Double
    Dim ok As Boolean, deg_ok As Boolean
    Dim coefsNode As Long, ptNode As Long, curveNode As Long, arr As Long
    Dim dxarr As Long, amparr As Long
    Dim bad_c As Long, bad_pit As Long, bad_deg As Long
    Dim ca() As Double, cy() As Double, wr() As Double

    cfg = jp_member(root, "config")
    exp = jp_member(root, "expected")
    tol = jp_member(root, "tolerance")
    inp = jp_member(root, "input")
    If cfg = 0 Or exp = 0 Or tol = 0 Or inp = 0 Then
        detail = "в векторе нет config/expected/tolerance/input"
        Exit Function
    End If

    jp_num_array jp_path(inp, "angles_deg"), angles, n
    jp_num_array jp_path(inp, "radii_mm"), radii, n

    mdl_new
    mdl_options CLng(jp_path_num(cfg, "n_patches")), jp_path_num(cfg, "phase_deg"), _
                CLng(jp_path_num(cfg, "deg_min")), CLng(jp_path_num(cfg, "deg_max")), _
                jp_path_num(cfg, "overlap_train"), jp_path_num(cfg, "overlap_use"), _
                jp_path_num(cfg, "deg_elbow_tol"), jp_path_str(cfg, "coord_mode")

    npits = jp_path_count(cfg, "pits_deg")
    If npits > 0 Then
        ReDim pits(1 To npits)
        For i = 1 To npits
            pits(i) = jp_num(jp_child(jp_path(cfg, "pits_deg"), i))
        Next i
        mdl_pit_shape_options jp_path_num(cfg, "sigma_deg"), jp_path_num(cfg, "pit_core_sigma"), _
                              jp_path_num(cfg, "pit_window_sigma"), jp_path_num(cfg, "pit_min_amp"), _
                              jp_path_bool(cfg, "tapering")
        mdl_set_pits pits, npits
    End If

    mdl_fit angles, radii, n
    io_trace "  fitted: patches=" & CStr(mdl_npatch())

    rel = jp_path_num(tol, "coefs_rel")
    If rel <= 0# Then rel = 0.000000001
    flr = jp_path_num(tol, "coefs_abs_floor")
    If flr <= 0# Then flr = 0.00000001
    tol_curve = jp_path_num(tol, "curve_mm")
    If tol_curve <= 0# Then tol_curve = 0.000001

    ok = True
    max_c = 0#
    max_pit = 0#
    max_dx = 0#
    max_r = 0#
    bad_c = 0
    bad_pit = 0
    bad_deg = 0

    ' --- степени патчей (обязаны совпасть точно) ---
    d = mdl_degrees()
    deg_ok = (jp_path_count(exp, "degrees") = mdl_npatch())
    If deg_ok Then
        For p = 1 To mdl_npatch()
            If CLng(jp_num(jp_child(jp_path(exp, "degrees"), p))) <> d(p) Then
                deg_ok = False
                bad_deg = bad_deg + 1
            End If
        Next p
    End If
    If Not deg_ok Then ok = False

    ' --- коэффициенты: |d| <= max(floor, rel*|c_ожид|) ---
    coefsNode = jp_path(exp, "coefs")
    For p = 1 To mdl_npatch()
        arr = jp_child(coefsNode, p)
        If arr <> 0 Then
            nc = jp_count(arr)
            For k = 1 To nc
                If k > mdl_patch_degree(p) + 1 Then
                    ok = False
                    bad_c = bad_c + 1
                Else
                    want = jp_num(jp_child(arr, k))
                    got = mdl_patch_coef(p, k)
                    allowed = flr
                    If rel * Abs(want) > allowed Then allowed = rel * Abs(want)
                    If Abs(got - want) > allowed Then
                        ok = False
                        bad_c = bad_c + 1
                    End If
                    If Abs(got - want) > max_c Then max_c = Abs(got - want)
                End If
            Next k
        End If
    Next p

    ' --- ямные термины: отступы 1e-9 градуса, амплитуды как коэффициенты ---
    ptNode = jp_path(exp, "pit_terms")
    For p = 1 To mdl_npatch()
        arr = jp_child(ptNode, p)
        If arr <> 0 Then
            dxarr = jp_member(arr, "dx_deg")
            amparr = jp_member(arr, "amp")
            If jp_count(dxarr) <> mdl_patch_npit(p) Then
                ok = False
                bad_pit = bad_pit + 1
            Else
                For k = 1 To jp_count(dxarr)
                    want = jp_num(jp_child(dxarr, k))
                    got = mdl_patch_off(p, k)
                    If Abs(got - want) > max_dx Then max_dx = Abs(got - want)
                    If Abs(got - want) > 0.000000001 Then
                        ok = False
                        bad_pit = bad_pit + 1
                    End If
                    want = jp_num(jp_child(amparr, k))
                    got = mdl_patch_pitcoef(p, k)
                    allowed = flr
                    If rel * Abs(want) > allowed Then allowed = rel * Abs(want)
                    If Abs(got - want) > allowed Then
                        ok = False
                        bad_pit = bad_pit + 1
                    End If
                    If Abs(got - want) > max_pit Then max_pit = Abs(got - want)
                Next k
            End If
        End If
    Next p
' >>> CURVE
    ' --- контур на сетке вектора: главный критерий (1e-6 мм) ---
    curveNode = jp_path(exp, "curve")
    If curveNode <> 0 Then
        jp_num_array jp_member(curveNode, "angles_deg"), ca, nc
        jp_num_array jp_member(curveNode, "radii_mm"), wr, nc
        cy = mdl_eval(ca)
        For i = 1 To nc
            If Abs(cy(i) - wr(i)) > max_r Then max_r = Abs(cy(i) - wr(i))
        Next i
        If max_r > tol_curve Then ok = False
    End If

    detail = "степени " & IIf(deg_ok, "совпали", "РАЗОШЛИСЬ") & _
             ", коэфф max|d| " & conf_sci(max_c) & " (вне допуска " & CStr(bad_c) & ")" & _
             ", ямные термины " & conf_sci(max_pit) & " амп / " & conf_sci(max_dx) & " гр" & _
             " (вне допуска " & CStr(bad_pit) & ")" & _
             ", контур " & conf_sci(max_r) & " мм"
    conf_model = ok
End Function
