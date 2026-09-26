Attribute VB_Name = "PappaSelftest"
Option Explicit

' PAPPA VBA port -- самопроверка порта: конформанс-векторы, юниты сигнала,
' линалга и JSON, границы очистки/детектора, гладкая синусоида, ямный фичер и
' контракт папки образца (записали -> прочитали -> сверили). Аналог
' octave/src/selftest_run.m и fortran/src/selftest.f90.
'
' Точка входа pappa_selftest_run(<каталог векторов>) -- её зовёт
' vba/build_vba.ps1 -Test через COM. Последняя строка отчёта -- "RESULT: OK"
' или "RESULT: FAIL n": по ней скрипт сборки выставляет код возврата.
'
' Отчёт собирается в строку, а не печатается: в VBA нет консоли (см. PappaIo),
' а упавшая проверка не должна бросать Err -- иначе COM отдал бы только текст
' исключения, и остальные проверки не выполнились бы (как в PappaConformance).

Private Const PI_DEG As Double = 3.141592653589793 / 180#

Private m_pass As Long
Private m_fail As Long
Private m_log As String

Public Function pappa_selftest_run(ByVal vectorDir As String) As String
    Dim t As String, out As String, txt As String, s0 As String
    Dim secFile As String, secPath As String
    Dim a() As Double, b() As Double, pitted() As Double
    Dim mf() As Double, sm() As Double, cy() As Double
    Dim xs() As Double, ys() As Double, co() As Double, row() As Double, c4() As Double
    Dim vals() As Double, pits() As Double
    Dim lo() As Double, hi() As Double
    Dim mask() As Boolean
    Dim secIds() As Long, secH() As Double, secNp() As Long, secNo() As Long
    Dim n As Long, i As Long
    Dim nout As Long, win As Long, nz As Long, npits As Long, kept As Long
    Dim rootJ As Long, rootD As Long, nodeJ As Long
    Dim dev As Double, dd As Double, ripple As Double
    Dim got As Double, want As Double, maxrel As Double
    Dim s1 As Double, s2 As Double
    Dim okn As Boolean, okc As Boolean

    m_pass = 0
    m_fail = 0
    m_log = "VBA SelfTest: " & vectorDir & vbLf

    ' ---------------------------------------------------- конформанс-векторы
    sel_head "конформанс-векторы"
    t = pappa_conformance_run(vectorDir)          ' отчёт порта по всем векторам
    m_log = m_log & t & vbLf
    sel_check (InStr(t, "RESULT: OK") > 0), "все векторы в допуске"
    sel_check (sel_after(t, "conformance: ") >= 4), "векторов не меньше 4"

    ' -------------------------------------------------------- юниты сигнала
    sel_head "сигнал: статистика, кольцо, окна"
    ReDim a(1 To 4)
    a(1) = 1#: a(2) = 2#: a(3) = 3#: a(4) = 4#
    sel_check Abs(sig_median(a) - 2.5) < 1E-15, "медиана чётной длины усредняет середину"
    ReDim b(1 To 3)
    b(1) = 1#: b(2) = 2#: b(3) = 3#
    sel_check Abs(sig_median(b) - 2#) < 1E-15, "медиана нечётной длины -- центральное значение"
    sel_check Abs(sig_percentile(a, 50#) - 2.5) < 1E-15, "перцентиль 50 совпадает с медианой"
    sel_check (Abs(sig_percentile(a, 0#) - 1#) < 1E-15) And _
              (Abs(sig_percentile(a, 100#) - 4#) < 1E-15), _
              "перцентиль 0/100 -- минимум/максимум"
    sel_check Abs(sig_iqr2(a) - 1.5) < 1E-15, "IQR [1..4] = 1.5"
    sel_check sig_mod_int(-1, 360) = 359, "Mod(-1,360) = 359 (в VBA Mod усекает к нулю)"
    sel_check (sig_round_even(0.5) = 0#) And (sig_round_even(2.5) = 2#) And _
              (sig_round_even(1.5) = 2#), "половина к чётному (Round в VBA банковский)"
    sel_check (Abs(sig_circ_dist(359#, 1#) - 2#) < 1E-12) And _
              (Abs(sig_circ_local(1#, 359#) - 2#) < 1E-12) And _
              (Abs(sig_circ_dist(0#, 180#) - 180#) < 1E-12), "расстояния по кольцу"
    sel_check (sig_smoothstep(-1#) = 0#) And (sig_smoothstep(2#) = 1#) And _
              (Abs(sig_smoothstep(0.5) - 0.5) < 1E-15), "smoothstep на краях и посередине"

    n = 360
    ReDim a(1 To n)
    For i = 1 To n
        a(i) = CDbl(i - 1)
    Next i
    sel_check (sig_window_points(a, 1#) = 3) And (sig_window_points(a, 10#) = 11), _
              "окно в точках: 1 град -> 3, 10 град -> 11"
    ReDim b(1 To 9)
    For i = 1 To 9
        b(i) = CDbl(i)
    Next i
    mf = sig_median_filter(b, 3)
    sm = sig_smooth_wrap(b, 3)
    sel_check (mf(5) = 5#) And (mf(1) = 2#), "медианный фильтр центрирован на точке"
    sel_check Abs(sm(5) - 5#) < 1E-12, "кольцевое сглаживание тоже центрировано"

    ' --------------------------------------------------------- линейная алгебра
    sel_head "линейная алгебра"
    ReDim xs(1 To 5)
    ReDim ys(1 To 5)
    For i = 1 To 5
        xs(i) = CDbl(i - 3)                       ' -2, -1, 0, 1, 2
        ys(i) = 2# + 3# * xs(i)
    Next i
    co = lin_polyfit(xs, ys, 5, 1)
    sel_check (Abs(co(1) - 3#) < 1E-10) And (Abs(co(2) - 2#) < 1E-10), _
              "polyfit прямой даёт [3, 2] (по убыванию степени)"
    sel_check Abs(lin_polyval(co, 10#) - 32#) < 1E-10, "polyval по Горнеру: 3*10 + 2 = 32"
    ReDim c4(1 To 4)
    c4(1) = 1#: c4(2) = 2#: c4(3) = 3#: c4(4) = 4#
    row = lin_cheb_row(0.3, 3)
    s1 = lin_cheb_sum(c4, 3, 0.3)
    s2 = 0#
    For i = 1 To 4
        s2 = s2 + c4(i) * row(i)
    Next i
    sel_check Abs(s1 - s2) < 1E-12, "cheb_sum совпадает с суммой по строке базиса"

    ' ------------------------------------------------------------ JSON: запись
    sel_head "JSON: запись и разбор"
    sel_check (json_num(0#) = "0") And (json_num(15#) = "15") And _
              (json_num(24.75) = "24.75"), "json_num: ноль и целые без дробной части"
    ReDim vals(1 To 6)
    vals(1) = 0.1: vals(2) = 24.75: vals(3) = -3.5
    vals(4) = 0.000000000001#: vals(5) = 15#: vals(6) = 1000000000000000#
    okn = True
    For i = 1 To 6
        rootJ = json_parse("[" & json_num(vals(i)) & "]")
        If rootJ = 0 Then
            okn = False
        ElseIf Abs(jp_num(jp_child(rootJ, 1)) - vals(i)) > 1E-14 * Abs(vals(i)) Then
            okn = False
        End If
    Next i
    sel_check okn, "json_num round-trip шести чисел (допуск 1e-14 отн.)"

    ' Строка с кавычкой, обратным слэшем, переводом строки и кириллицей: не-ASCII
    ' уходит в \uXXXX, поэтому файл остаётся ASCII (см. шапку PappaJson).
    s0 = "a""b\c" & vbLf & ChrW$(&H41F) & "ривет"
    rootJ = json_parse(json_str(s0))
    sel_check (rootJ <> 0) And (jp_str(rootJ) = s0), _
              "строка round-trip: кавычка, слэш, перевод строки, кириллица (\uXXXX)"
    rootJ = json_parse("{""a"": [1, 2.5, true, null, ""x\ny""], ""b"": {""c"": -0.5}}")
    sel_check (rootJ <> 0) And (jp_path_count(rootJ, "a") = 5) And _
              (Abs(jp_path_num(rootJ, "b.c") + 0.5) < 1E-15), _
              "вложенный объект и массив разобраны"
    sel_check jp_bool(jp_child(jp_path(rootJ, "a"), 3)), "true внутри массива"
    sel_check jp_is_null(jp_child(jp_path(rootJ, "a"), 4)), "null внутри массива"
    sel_check jp_str(jp_child(jp_path(rootJ, "a"), 5)) = ("x" & vbLf & "y"), _
              "escape \n внутри строки"
    txt = json_render(json_parse("{""z"": 1, ""a"": null}"))
    sel_check InStr(txt, """z"":1,""a"":null") > 0, "json_render сохраняет порядок полей"

    ' ----------------------------------------- границы очистки и детектора
    sel_head "границы очистки и детектора"
    n = 10
    ReDim a(1 To n)
    ReDim b(1 To n)
    For i = 1 To n
        a(i) = CDbl(i - 1)
        b(i) = 40#
    Next i
    cln_clean_iqr a, b, 10#, 3#, 0.5, 20, mask, nout, win
    sel_check (nout = 0) And (win = 0), _
              "точек меньше min_points -- очистка выключена (окно 0), маска без выбросов"
    n = 360
    ReDim a(1 To n)
    ReDim mask(1 To n)
    For i = 1 To n
        a(i) = CDbl(i - 1)
    Next i
    For i = 11 To 21
        mask(i) = True                            ' углы 10..20
    Next i
    det_mask_to_zones a, mask, 1#, lo, hi, nz
    sel_check (nz = 1) And (Abs(lo(1) - 9.5) < 1E-12) And (Abs(hi(1) - 20.5) < 1E-12), _
              "зона из маски: полшага вокруг концов (9.5..20.5)"
    ReDim mask(1 To n)
    For i = 1 To n
        mask(i) = (i <= 3) Or (i >= 358)          ' через 0 градусов
    Next i
    det_mask_to_zones a, mask, 1#, lo, hi, nz
    sel_check nz = 1, "зона через 0 градусов склеивается в одну"

    ' ----------------------------------------- гладкая синусоида -> модель
    sel_head "гладкая синусоида: 7 патчей"
    ReDim b(1 To n)
    For i = 1 To n
        b(i) = 50# + 0.4 * Sin(a(i) * PI_DEG)
    Next i
    mdl_new
    mdl_options 7, 24.75, 4, 14, 15#, 5#, 0.05, "normalized"
    mdl_fit a, b, n
    sel_check mdl_npatch() = 7, "получено 7 патчей"
    cy = mdl_eval(a)
    dev = 0#
    For i = 1 To n
        If Abs(cy(i) - b(i)) > dev Then dev = Abs(cy(i) - b(i))
    Next i
    sel_check dev < 1E-6, _
              "контур воспроизведён лучше 1e-6 мм (max|d| = " & sel_sci(dev) & " мм)"

    ' --------------------------------------- ямный фичер: детектор и термины
    ' Ямы видны только на фоне высокочастотной подложки: на идеально гладком
    ' профиле робастная sigma самого индикатора ~0, и нормировка обнуляет band
    ' (та же ловушка, что у вектора 03 в spec/conformance/README.md).
    sel_head "ямный фичер: детектор и ямные термины"
    ReDim pitted(1 To n)
    For i = 1 To n
        ripple = 0.02 * Sin(2# * 3.141592653589793 * a(i) / 7#)
        dd = 0.5 * Exp(-(((a(i) - 90#) / 1.2) ^ 2)) + _
             0.5 * Exp(-(((a(i) - 210#) / 1.2) ^ 2))
        pitted(i) = b(i) + ripple - dd
    Next i
    det_pits a, pitted, 1#, 10#, 2#, 5.5, 2#, pits, npits
    sel_check npits = 2, "детектор нашёл 2 ямы (найдено " & CStr(npits) & ")"
    okc = False
    If npits = 2 Then
        okc = (sig_circ_dist(pits(1), 90#) <= 2#) Or (sig_circ_dist(pits(2), 90#) <= 2#)
        If okc Then
            okc = (sig_circ_dist(pits(1), 210#) <= 2#) Or (sig_circ_dist(pits(2), 210#) <= 2#)
        End If
    End If
    sel_check okc, "центры ям не дальше 2 градусов от провалов 90 и 210"
    mdl_new
    mdl_pit_shape_options 3#, 2#, 3.2, 0.003, True
    mdl_set_pits pits, npits
    mdl_options 7, 24.75, 4, 14, 15#, 5#, 0.05, "normalized"
    mdl_fit a, pitted, n
    kept = 0
    For i = 1 To mdl_npatch()
        kept = kept + mdl_patch_npit(i)
    Next i
    sel_check kept > 0, _
              "ямные термы прошли отсечку по амплитуде (осталось " & CStr(kept) & ")"
    ' ----------------------- контракт папки образца: записали -> прочитали
    sel_head "контракт документа и манифеста"
    out = sel_temp_dir()
    io_make_dir out
    io_make_dir out & "\sections"
    secFile = document_section_file(0)                       ' sections/00.pappa.json
    secPath = out & "\" & Replace(secFile, "/", "\")
    txt = document_section_text(0, 7.5, "smoke", "selftest", n, 0, 1.5)
    io_write_text secPath, txt
    sel_check io_file_exists(secPath), "документ сечения записан в " & secPath
    sel_check InStr(txt, vbCr) = 0, "в тексте документа нет CR (VBA пишет только LF)"
    rootD = json_parse(io_read_text(secPath))
    sel_check rootD <> 0, "документ разобран обратно (json_error: " & json_error() & ")"
    sel_check jp_path_str(rootD, "format") = "pappa", "документ: format = pappa"
    sel_check jp_path_str(rootD, "method") = "PitPatchApproximator", _
              "документ: method называет ямный вариант"
    sel_check jp_path_str(rootD, "software.language") = PORT_LANGUAGE, _
              "документ: software.language = " & PORT_LANGUAGE
    sel_check jp_path_count(rootD, "patches") = mdl_npatch(), "документ: по записи на патч"
    sel_check jp_path_count(rootD, "global.pit.centers_deg") = npits, _
              "документ: перечислены все центры ям (" & CStr(npits) & ")"
    sel_check Abs(jp_path_num(rootD, "statistics.n_points_total") - CDbl(n)) < 1E-9, _
              "документ: statistics.n_points_total"
    ' ЛОВУШКА VBA: Format$/Str печатают максимум 15 значащих цифр, поэтому
    ' числа читаются обратно не побитово, а с ~1e-15 отн. (PappaJson). На приёмку
    ' это не влияет (контур 1e-6 мм), но проверяем честно: 1e-14 отн.
    maxrel = 0#
    For i = 1 To mdl_npatch()
        nodeJ = jp_child(jp_path(rootD, "patches"), i)
        want = mdl_patch_center(i)
        got = jp_path_num(nodeJ, "center_deg")
        If Abs(want) > 1# Then
            If Abs(got - want) / Abs(want) > maxrel Then maxrel = Abs(got - want) / Abs(want)
        End If
    Next i
    sel_check maxrel < 1E-14, _
              "центры патчей читаются обратно с 1e-14 отн. (" & sel_sci(maxrel) & ")"

    ReDim secIds(1 To 1)
    ReDim secH(1 To 1)
    ReDim secNp(1 To 1)
    ReDim secNo(1 To 1)
    secIds(1) = 0
    secH(1) = 7.5
    secNp(1) = n
    secNo(1) = 0
    io_write_text out & "\sample.json", _
        document_manifest_text("smoke", "pappa vba selftest", "", 1#, 3#, True, _
                               secIds, secH, secNp, secNo, 1)
    txt = io_read_text(out & "\sample.json")
    rootD = json_parse(txt)
    sel_check (rootD <> 0) And (jp_path_str(rootD, "format") = "pappa-sample") And _
              (jp_path_str(rootD, "name") = "smoke"), _
              "манифест: format = pappa-sample, name = smoke"
    sel_check jp_path_count(rootD, "sections") = 1, "манифест: одно сечение"
    sel_check jp_path_str(jp_child(jp_path(rootD, "sections"), 1), "file") = secFile, _
              "манифест: файл сечения по контракту sections/NN.pappa.json"
    sel_check jp_is_null(jp_path(rootD, "config.detector")), "манифест: detector = null"
    sel_check InStr(txt, vbCr) = 0, "в тексте манифеста нет CR"
    sel_check (jp_path_num(rootD, "config.n_patches") = 7) And _
              (Abs(jp_path_num(rootD, "config.phase_deg") - 24.75) < 1E-12), _
              "манифест: конфиг раскладки на месте"

    ' ------------------------------------------------------------------ итог
    m_log = m_log & vbLf & "Total: " & CStr(m_pass) & " OK, " & CStr(m_fail) & " FAIL" & vbLf
    If m_fail = 0 Then
        m_log = m_log & "RESULT: OK"
    Else
        m_log = m_log & "RESULT: FAIL " & CStr(m_fail)
    End If
    pappa_selftest_run = m_log
End Function

' ------------------------------------------------------------------ служебное

' Одна проверка: строка отчёта + счётчики. Ничего не бросаем: упавшая проверка
' должна быть видна в отчёте, а не превратиться в текст исключения COM.
Private Sub sel_check(ByVal ok As Boolean, ByVal what As String)
    If ok Then
        m_pass = m_pass + 1
        m_log = m_log & "  OK   " & what & vbLf
    Else
        m_fail = m_fail + 1
        m_log = m_log & "  FAIL " & what & vbLf
    End If
End Sub

Private Sub sel_head(ByVal title As String)
    m_log = m_log & "== " & title & " ==" & vbLf
End Sub

' Первое число после метки ("VBA conformance: 4 vectors from ..." -> 4).
Private Function sel_after(ByVal text As String, ByVal marker As String) As Long
    Dim p As Long
    p = InStr(text, marker)
    If p = 0 Then Exit Function
    sel_after = CLng(Val(Mid$(text, p + Len(marker))))
End Function

' Число для сообщений отчёта: научная запись с точкой (локаль даёт запятую).
Private Function sel_sci(ByVal v As Double) As String
    sel_sci = Replace(Format$(v, "0.00E+00"), ",", ".")
End Function

' Временный каталог самопроверки (как temp_file в остальных портах).
Private Function sel_temp_dir() As String
    Dim tmp As String
    tmp = Environ$("TEMP")
    If Len(tmp) = 0 Then tmp = Environ$("TMP")
    If Len(tmp) = 0 Then tmp = "."
    sel_temp_dir = tmp & "\pappa_vba_selftest"
End Function

