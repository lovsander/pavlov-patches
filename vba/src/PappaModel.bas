Attribute VB_Name = "PappaModel"
Option Explicit

' PAPPA VBA port -- модель: патчи с адаптивной степенью, smoothstep-смешивание
' (partition of unity) и оконный гауссов фичер ям.
'
' ЛОВУШКА VBA: структуру-значение с динамическими массивами внутри (как
' type(pappa_model) в Fortran или pp_model в C) здесь не сделать -- UDT в VBA не
' может содержать массив, который перераспределяется на элемент массива UDT.
' Поэтому состояние модели живёт в модульных переменных (m_*), а функции читают
' их как глобальную модель: mdl_new = сброс, mdl_fit = обучение, mdl_eval =
' контур. Конформанс-векторы и пайплайн работают с одной моделью за раз, как
' C-порт с его g_models.
'
' Пустых массивов (ReDim a(1 To 0)) в VBA не бывает -- там ошибка времени
' выполнения, поэтому длина везде передаётся отдельным счётчиком (как n в C).

' --- параметры модели (pappa_options в остальных портах) ---
Private m_n_patches As Long
Private m_phase_deg As Double
Private m_deg_min As Long
Private m_deg_max As Long
Private m_overlap_train As Double
Private m_overlap_use As Double
Private m_deg_elbow_tol As Double
Private m_amplitude_scale As Double
Private m_coord_mode As String

' --- форма ямной фичи (pit_shape_options) ---
Private m_sigma_deg As Double
Private m_core_sigma As Double
Private m_window_sigma As Double
Private m_pit_min_amp As Double
Private m_tapering As Boolean

' --- центры ям, градусы ---
Private m_pits() As Double
Private m_n_pits As Long

' --- патчи: по массиву на поле, счётчик m_npatch ---
Private m_npatch As Long
Private m_p_center() As Double
Private m_p_degree() As Long
Private m_p_npoints() As Long
Private m_p_ntrain() As Long
Private m_p_coefs() As Double
Private m_p_off() As Double
Private m_p_pitcoef() As Double
Private m_p_npit() As Long
Private m_p_amplitude() As Double
Private m_p_amp_norm() As Double
Private m_p_mean_r() As Double
Private m_p_rmse_sel() As Double
Private m_p_rmse_best() As Double
Private m_p_rmse() As Double
Private m_p_mae() As Double
Private m_p_maxerr() As Double
Private m_p_corr() As Double
Private m_p_degtol() As Double

Private m_half_sector As Double
Private m_is_fitted As Boolean

' Новая (необученная) модель: параметры по умолчанию.
Public Sub mdl_new()
    m_n_patches = 7
    m_phase_deg = 24.75
    m_deg_min = 4
    m_deg_max = 14
    m_overlap_train = 15#
    m_overlap_use = 5#
    m_deg_elbow_tol = 0.05
    m_amplitude_scale = 180#
    m_coord_mode = "normalized"
    m_sigma_deg = 3#
    m_core_sigma = 2#
    m_window_sigma = 3.2
    m_pit_min_amp = 0.003
    m_tapering = True
    m_n_pits = 0
    ReDim m_pits(1 To 1)
    m_npatch = 0
    m_half_sector = 0#
    m_is_fitted = False
End Sub

' Параметры раскладки (аналог pappa_options/PatchApproximatorOptions).
Public Sub mdl_options(ByVal n_patches As Long, ByVal phase_deg As Double, _
                       ByVal deg_min As Long, ByVal deg_max As Long, _
                       ByVal overlap_train As Double, ByVal overlap_use As Double, _
                       ByVal deg_elbow_tol As Double, ByVal coord_mode As String)
    m_n_patches = n_patches
    m_phase_deg = phase_deg
    m_deg_min = deg_min
    m_deg_max = deg_max
    m_overlap_train = overlap_train
    m_overlap_use = overlap_use
    m_deg_elbow_tol = deg_elbow_tol
    m_coord_mode = coord_mode
End Sub

' Форма ямной фичи (аналог pp_model_set_pit_shape / pit_shape_options).
Public Sub mdl_pit_shape_options(ByVal sigma_deg As Double, ByVal core_sigma As Double, _
                                 ByVal window_sigma As Double, ByVal pit_min_amp As Double, _
                                 ByVal tapering As Boolean)
    m_sigma_deg = sigma_deg
    m_core_sigma = core_sigma
    m_window_sigma = window_sigma
    m_pit_min_amp = pit_min_amp
    m_tapering = tapering
End Sub

' Центры ям: приводятся к [0, 360), как modulo(pits, 360) в остальных портах.
Public Sub mdl_set_pits(pits_deg() As Double, ByVal n As Long)
    Dim i As Long
    m_n_pits = n
    If n > PP_MAX_PITS Then m_n_pits = PP_MAX_PITS
    ReDim m_pits(1 To m_n_pits)
    For i = 1 To m_n_pits
        m_pits(i) = sig_mod_py(pits_deg(i), 360#)
    Next i
End Sub

' Полуширина ОБУЧАЮЩЕГО окна патча (полсектора + overlap_train).
Public Function mdl_half_train() As Double
    mdl_half_train = m_half_sector + m_overlap_train
End Function

' Полуширина окна ПРИМЕНЕНИЯ патча (полсектора + overlap_use).
Public Function mdl_half_use() As Double
    mdl_half_use = m_half_sector + m_overlap_use
End Function

' Есть ли в модели ямные термы.
Public Function mdl_has_pits() As Boolean
    mdl_has_pits = (m_n_pits > 0)
End Function

' Вес патча (partition of unity): 1 внутри сектора, smoothstep в перекрытии,
' 0 снаружи окна применения.
Public Function mdl_weight(ByVal d_deg As Double, ByVal half_use_deg As Double) As Double
    If d_deg <= m_half_sector Then
        mdl_weight = 1#
    ElseIf d_deg <= half_use_deg Then
        mdl_weight = sig_smoothstep(1# - (d_deg - m_half_sector) / (half_use_deg - m_half_sector))
    Else
        mdl_weight = 0#
    End If
End Function

' Оконный гаусс ямной фичи как функция расстояния от центра ямы (градусы):
' exp(-d^2/2sigma^2) с опциональной smoothstep-отсечкой на границе окна.
Public Function mdl_pit_shape_deg(ByVal d_deg As Double) As Double
    Dim d As Double, base As Double, core As Double, edge As Double, t As Double
    d = Abs(d_deg)
    base = Exp(-(d * d) / (2# * m_sigma_deg * m_sigma_deg))
    If Not m_tapering Then
        mdl_pit_shape_deg = base
        Exit Function
    End If
    core = m_core_sigma * m_sigma_deg
    edge = m_window_sigma * m_sigma_deg
    If edge <= core Then
        mdl_pit_shape_deg = base
        Exit Function
    End If
    t = (edge - d) / (edge - core)
    If t < 0# Then t = 0#
    If t > 1# Then t = 1#
    mdl_pit_shape_deg = base * t * t * (3# - 2# * t)
End Function

' Смещения ВИДИМЫХ ям в локальной системе патча (градусы): |dx| <= half_win.
' Вызывающий читает dx(1..n); буфер всегда выделяется (пустых массивов нет).
Public Sub mdl_pit_offsets(ByVal center_deg As Double, ByVal half_win_deg As Double, _
                           ByRef dx() As Double, ByRef n As Long)
    Dim i As Long
    Dim d As Double
    ReDim dx(1 To PP_MAX_PITS + 1)
    n = 0
    For i = 1 To m_n_pits
        d = sig_circ_local(m_pits(i), center_deg)
        If Abs(d) <= half_win_deg Then
            n = n + 1
            dx(n) = d
        End If
    Next i
End Sub

' Точки обучающего окна патча в локальной координате (нормированной или сырой).
' Порядок обхода -- как в остальных портах: сдвиги -360, 0, +360, внутри -- по
' возрастанию угла. Вызывающий читает xs(1..n), ys(1..n).
Public Sub mdl_window_of(angles() As Double, radii() As Double, ByVal center As Double, _
                         ByRef xs() As Double, ByRef ys() As Double, ByRef n As Long)
    Dim shifts(1 To 3) As Double
    Dim half As Double, dx As Double
    Dim i As Long, ish As Long, k As Long
    Dim norm As Boolean
    shifts(1) = -360#
    shifts(2) = 0#
    shifts(3) = 360#
    half = mdl_half_train()
    norm = (m_coord_mode <> "raw")
    ReDim xs(1 To PP_MAX_POINTS)
    ReDim ys(1 To PP_MAX_POINTS)
    k = 0
    For ish = 1 To 3
        For i = 1 To UBound(angles)
            dx = angles(i) + shifts(ish) - center
            If dx >= -half And dx <= half Then
                If k < PP_MAX_POINTS Then
                    k = k + 1
                    If norm Then
                        xs(k) = dx / half
                    Else
                        xs(k) = dx
                    End If
                    ys(k) = radii(i)
                End If
            End If
        Next i
    Next ish
    n = k
End Sub

' Правило «локтя»: наименьшая ЧЁТНАЯ степень, на которой RMSE обучающего окна
' не хуже лучшей более чем на deg_elbow_tol. Возвращает степень и две RMSE
' (выбранной и лучшей).
'
' Свип степеней -- ОДНОЙ матрицей Грама в базисе Чебышёва и RMSE по явным
' остаткам (в нормированном режиме); в режиме coord_mode = "raw" базис
' Чебышёва неприменим (x вне [-1, 1]) -- там прямой полиномиальный МНК.
Public Sub mdl_estimate_degree(xs() As Double, ys() As Double, ByVal n As Long, _
                               ByRef sel_deg As Long, ByRef rmse_sel As Double, _
                               ByRef rmse_best As Double)
    Dim degs() As Double, rmses() As Double
    Dim v As Double, r As Double, best As Double, limit As Double, yref As Double
    Dim i As Long, k As Long, l As Long, deg As Long, pw As Long, nd As Long
    Dim dmax As Long, p As Long, nn As Long
    Dim best_deg As Long, sel As Long, best_set As Boolean

    sel_deg = m_deg_min
    rmse_sel = 0#
    rmse_best = 0#
    If n < 5 Then Exit Sub

    ReDim degs(1 To (m_deg_max - m_deg_min) \ 2 + 1)
    ReDim rmses(1 To (m_deg_max - m_deg_min) \ 2 + 1)
    nd = 0
    best_deg = m_deg_min
    best = 0#
    best_set = False

    If m_coord_mode = "raw" Then
        Dim a() As Double, co() As Double
        For deg = m_deg_min To m_deg_max Step 2
            ReDim a(1 To n, 1 To deg + 1)
            For i = 1 To n
                For pw = 0 To deg
                    a(i, deg + 1 - pw) = xs(i) ^ pw
                Next pw
            Next i
            co = lin_lstsq(a, ys, n, deg + 1)
            r = 0#
            For i = 1 To n
                v = 0#
                For k = 1 To deg + 1
                    v = v + a(i, k) * co(k)
                Next k
                r = r + (v - ys(i)) * (v - ys(i))
            Next i
            r = Sqr(r / CDbl(n))
            nd = nd + 1
            degs(nd) = CDbl(deg)
            rmses(nd) = r
            If (Not best_set) Or (r < best) Then
                best = r
                best_deg = deg
                best_set = True
            End If
        Next deg
    Else
        Dim tt() As Double, yc() As Double
        Dim gram() As Double, rhs() As Double, g2() As Double, r2() As Double
        dmax = m_deg_max
        p = dmax + 1
        yref = 0#
        For i = 1 To n
            yref = yref + ys(i)
        Next i
        yref = yref / CDbl(n)
        tt = lin_cheb_matrix(xs, n, dmax)
        ReDim yc(1 To n)
        For i = 1 To n
            yc(i) = ys(i) - yref
        Next i
        ReDim gram(1 To p, 1 To p)
        ReDim rhs(1 To p)
        For k = 1 To p
            For l = 1 To p
                gram(k, l) = 0#
                For i = 1 To n
                    gram(k, l) = gram(k, l) + tt(i, k) * tt(i, l)
                Next i
            Next l
            rhs(k) = 0#
            For i = 1 To n
                rhs(k) = rhs(k) + tt(i, k) * yc(i)
            Next i
        Next k
        For deg = m_deg_min To dmax Step 2
            nn = deg + 1
            ReDim g2(1 To nn, 1 To nn)
            ReDim r2(1 To nn)
            For k = 1 To nn
                For l = 1 To nn
                    g2(k, l) = gram(k, l)
                Next l
                r2(k) = rhs(k)
            Next k
            co = lin_lstsq(g2, r2, nn, nn)
            r = 0#
            For i = 1 To n
                v = 0#
                For k = 1 To nn
                    v = v + tt(i, k) * co(k)
                Next k
                r = r + (v - yc(i)) * (v - yc(i))
            Next i
            r = Sqr(r / CDbl(n))
            nd = nd + 1
            degs(nd) = CDbl(deg)
            rmses(nd) = r
            If (Not best_set) Or (r < best) Then
                best = r
                best_deg = deg
                best_set = True
            End If
        Next deg
    End If

    limit = best * (1# + m_deg_elbow_tol)
    sel = best_deg
    rmse_sel = best
    For k = 1 To nd
        If rmses(k) <= limit Then
            sel = CLng(degs(k))
            rmse_sel = rmses(k)
            Exit For
        End If
    Next k
    sel_deg = sel
    rmse_best = best
End Sub

' Обучение модели: патчи с адаптивной степенью, smoothstep-смешивание и
' оконный гауссов фичер ям.
Public Sub mdl_fit(angles() As Double, radii() As Double, ByVal npts As Long)
    Dim centers() As Double
    Dim xs() As Double, ys() As Double
    Dim offs() As Double, kept_off() As Double, kept_coef() As Double
    Dim poly_coef() As Double, a() As Double, co() As Double
    Dim sector As Double, ht As Double, v As Double, shp As Double, mxamp As Double
    Dim ci As Long, np As Long, n As Long, ncol As Long, deg As Long, pw As Long
    Dim j As Long, nkeep As Long, i As Long, noff As Long
    Dim sel_deg As Long, rmse_sel As Double, rmse_best As Double

    If npts < 10 Then Err.Raise vbObjectError + 3, "Pappa", "mdl_fit: too few points"

    np = m_n_patches
    sector = 360# / CDbl(np)
    m_half_sector = sector / 2#
    ReDim centers(1 To np)
    For ci = 1 To np
        centers(ci) = sig_mod_py(CDbl(ci - 1) * sector + m_half_sector + m_phase_deg, 360#)
    Next ci
    ht = mdl_half_train()

    ' Патчи хранятся в массивах фиксированной длины (в VBA нет массивов
    ' записей с динамическими полями); число записанных -- m_npatch.
    m_npatch = 0
    ReDim m_p_center(1 To PP_MAX_PATCHES)
    ReDim m_p_degree(1 To PP_MAX_PATCHES)
    ReDim m_p_npoints(1 To PP_MAX_PATCHES)
    ReDim m_p_ntrain(1 To PP_MAX_PATCHES)
    ReDim m_p_coefs(1 To PP_MAX_PATCHES, 1 To PP_MAX_DEG + 1)
    ReDim m_p_off(1 To PP_MAX_PATCHES, 1 To PP_MAX_PITS + 1)
    ReDim m_p_pitcoef(1 To PP_MAX_PATCHES, 1 To PP_MAX_PITS + 1)
    ReDim m_p_npit(1 To PP_MAX_PATCHES)
    ReDim m_p_amplitude(1 To PP_MAX_PATCHES)
    ReDim m_p_amp_norm(1 To PP_MAX_PATCHES)
    ReDim m_p_mean_r(1 To PP_MAX_PATCHES)
    ReDim m_p_rmse_sel(1 To PP_MAX_PATCHES)
    ReDim m_p_rmse_best(1 To PP_MAX_PATCHES)
    ReDim m_p_rmse(1 To PP_MAX_PATCHES)
    ReDim m_p_mae(1 To PP_MAX_PATCHES)
    ReDim m_p_maxerr(1 To PP_MAX_PATCHES)
    ReDim m_p_corr(1 To PP_MAX_PATCHES)
    ReDim m_p_degtol(1 To PP_MAX_PATCHES)

    For ci = 1 To np
        mdl_window_of angles, radii, centers(ci), xs, ys, n
        If n >= 5 Then
            mdl_estimate_degree xs, ys, n, sel_deg, rmse_sel, rmse_best
            deg = sel_deg
            mdl_pit_offsets centers(ci), ht, offs, noff

            ncol = deg + 1 + noff
            ReDim a(1 To n, 1 To ncol)
            For i = 1 To n
                For pw = 0 To deg
                    a(i, deg + 1 - pw) = xs(i) ^ pw
                Next pw
                For j = 1 To noff
                    a(i, deg + 1 + j) = mdl_pit_shape_deg(Abs(xs(i) * ht - offs(j)))
                Next j
            Next i
            co = lin_lstsq(a, ys, n, ncol)
            ReDim poly_coef(1 To deg + 1)
            For i = 1 To deg + 1
                poly_coef(i) = co(i)
            Next i

            ' Отсечка ям, которые в окне патча «не видны» (pit_min_amp):
            ' max |coef * shape| по точкам окна.
            ReDim kept_off(1 To PP_MAX_PITS + 1)
            ReDim kept_coef(1 To PP_MAX_PITS + 1)
            nkeep = 0
            For j = 1 To noff
                mxamp = 0#
                For i = 1 To n
                    shp = mdl_pit_shape_deg(Abs(xs(i) * ht - offs(j)))
                    v = Abs(co(deg + 1 + j) * shp)
                    If v > mxamp Then mxamp = v
                Next i
                If mxamp >= m_pit_min_amp Then
                    nkeep = nkeep + 1
                    kept_off(nkeep) = offs(j)
                    kept_coef(nkeep) = co(deg + 1 + j)
                End If
            Next j

            mdl_push_patch centers(ci), deg, xs, ys, n, poly_coef, deg + 1, _
                           kept_off, kept_coef, nkeep, rmse_sel, rmse_best, _
                           angles, radii, npts
        End If
    Next ci
    m_is_fitted = True
End Sub

' Дописать патч к модели: коэффициенты, видимые ямы и метрики обучающего окна.
Private Sub mdl_push_patch(ByVal c0 As Double, ByVal deg As Long, _
                           xs() As Double, ys() As Double, ByVal n As Long, _
                           poly_coef() As Double, ByVal ncoef As Long, _
                           kept_off() As Double, kept_coef() As Double, ByVal nkeep As Long, _
                           ByVal rmse_sel As Double, ByVal rmse_best As Double, _
                           angles() As Double, radii() As Double, ByVal npts As Long)
    Dim fit_vals() As Double, sec() As Double
    Dim idx As Long, i As Long, j As Long, nsec As Long
    Dim v As Double, e As Double, sse As Double, sae As Double, mx As Double
    Dim mf As Double, my As Double, cov As Double, vf As Double, vy As Double, corr As Double
    Dim ht As Double, dist As Double, amp As Double, mean_sec As Double, amp_norm As Double

    idx = m_npatch + 1
    m_npatch = idx
    ht = mdl_half_train()

    ' --- статистика обучения: остатки на обучающем окне ---
    ReDim fit_vals(1 To n)
    sse = 0#
    sae = 0#
    mx = 0#
    For i = 1 To n
        v = lin_polyval(poly_coef, xs(i))
        For j = 1 To nkeep
            v = v + kept_coef(j) * mdl_pit_shape_deg(Abs(xs(i) * ht - kept_off(j)))
        Next j
        fit_vals(i) = v
        e = v - ys(i)
        sse = sse + e * e
        sae = sae + Abs(e)
        If Abs(e) > mx Then mx = Abs(e)
    Next i

    mf = 0#
    my = 0#
    For i = 1 To n
        mf = mf + fit_vals(i)
        my = my + ys(i)
    Next i
    mf = mf / CDbl(n)
    my = my / CDbl(n)
    cov = 0#
    vf = 0#
    vy = 0#
    For i = 1 To n
        cov = cov + (fit_vals(i) - mf) * (ys(i) - my)
        vf = vf + (fit_vals(i) - mf) * (fit_vals(i) - mf)
        vy = vy + (ys(i) - my) * (ys(i) - my)
    Next i
    corr = 0#
    If vf > 0# And vy > 0# Then corr = cov / Sqr(vf * vy)

    ' --- справочные метрики сектора: P95 - P5 и среднее по точкам сектора ---
    ReDim sec(1 To npts)
    nsec = 0
    For i = 1 To npts
        dist = Abs(sig_mod_py(angles(i) - c0 + 180#, 360#) - 180#)
        If dist <= m_half_sector Then
            nsec = nsec + 1
            sec(nsec) = radii(i)
        End If
    Next i
    amp = 0#
    mean_sec = 0#
    If nsec >= 5 Then
        ReDim Preserve sec(1 To nsec)
        amp = sig_percentile(sec, 95#) - sig_percentile(sec, 5#)
        For i = 1 To nsec
            mean_sec = mean_sec + sec(i)
        Next i
        mean_sec = mean_sec / CDbl(nsec)
    End If
    amp_norm = 0#
    If mean_sec > 0# Then amp_norm = amp / mean_sec

    ' --- запись патча ---
    m_p_center(idx) = c0
    m_p_degree(idx) = deg
    m_p_npoints(idx) = n
    m_p_ntrain(idx) = n
    For j = 1 To ncoef
        m_p_coefs(idx, j) = poly_coef(j)
    Next j
    m_p_npit(idx) = nkeep
    For j = 1 To nkeep
        m_p_off(idx, j) = kept_off(j)
        m_p_pitcoef(idx, j) = kept_coef(j)
    Next j
    m_p_amplitude(idx) = amp
    m_p_mean_r(idx) = mean_sec
    m_p_amp_norm(idx) = amp_norm
    m_p_degtol(idx) = m_deg_elbow_tol
    m_p_rmse_sel(idx) = rmse_sel
    m_p_rmse_best(idx) = rmse_best
    m_p_rmse(idx) = Sqr(sse / CDbl(n))
    m_p_mae(idx) = sae / CDbl(n)
    m_p_maxerr(idx) = mx
    m_p_corr(idx) = corr
End Sub

' --- доступ к обученной модели (документ, конформанс, метрики) ---

' Контур с выбором членов: PART_TOTAL | PART_POLY | PART_PIT.
Public Function mdl_eval_part(angles() As Double, ByVal part As Long) As Double()
    Dim out() As Double
    Dim a As Double, w As Double, dx As Double, x As Double, v As Double
    Dim sum_wv As Double, sum_w As Double, hu As Double, ht As Double
    Dim k As Long, p As Long, j As Long

    If Not m_is_fitted Then Err.Raise vbObjectError + 4, "Pappa", "mdl_eval_part: model is not fitted"
    hu = mdl_half_use()
    ht = mdl_half_train()
    ReDim out(1 To UBound(angles))
    For k = 1 To UBound(angles)
        a = angles(k)
        sum_wv = 0#
        sum_w = 0#
        For p = 1 To m_npatch
            w = mdl_weight(sig_circ_dist(a, m_p_center(p)), hu)
            If w > 0# Then
                dx = sig_circ_local(a, m_p_center(p))
                If m_coord_mode = "raw" Then
                    x = dx
                Else
                    x = dx / ht
                End If
                v = 0#
                If part <> PART_PIT Then
                    v = v + lin_polyval_row(m_p_coefs, p, m_p_degree(p) + 1, x)
                End If
                If part <> PART_POLY Then
                    For j = 1 To m_p_npit(p)
                        v = v + m_p_pitcoef(p, j) * mdl_pit_shape_deg(Abs(x * ht - m_p_off(p, j)))
                    Next j
                End If
                sum_wv = sum_wv + w * v
                sum_w = sum_w + w
            End If
        Next p
        If sum_w > 0# Then
            ' В референсе при нулевой сумме весов получается NaN; в VBA NaN не
            ' бывает (0/0 -- ошибка времени выполнения), поэтому ветка Else
            ' повторяет поведение C-порта: 0.
            out(k) = sum_wv / sum_w
        Else
            out(k) = 0#
        End If
    Next k
    mdl_eval_part = out
End Function

' Полный контур модели (градусы -> мм).
Public Function mdl_eval(angles() As Double) As Double()
    mdl_eval = mdl_eval_part(angles, PART_TOTAL)
End Function

' Степени патчей по порядку (диагностика и конформанс-вектор).
Public Function mdl_degrees() As Long()
    Dim d() As Long
    Dim k As Long
    ReDim d(1 To m_npatch)
    For k = 1 To m_npatch
        d(k) = m_p_degree(k)
    Next k
    mdl_degrees = d
End Function

Public Function mdl_npatch() As Long
    mdl_npatch = m_npatch
End Function

Public Function mdl_is_fitted() As Boolean
    mdl_is_fitted = m_is_fitted
End Function

Public Function mdl_patch_degree(ByVal i As Long) As Long
    mdl_patch_degree = m_p_degree(i)
End Function

Public Function mdl_patch_npoints(ByVal i As Long) As Long
    mdl_patch_npoints = m_p_npoints(i)
End Function

Public Function mdl_patch_center(ByVal i As Long) As Double
    mdl_patch_center = m_p_center(i)
End Function

Public Function mdl_patch_coef(ByVal i As Long, ByVal k As Long) As Double
    mdl_patch_coef = m_p_coefs(i, k)
End Function

Public Function mdl_patch_npit(ByVal i As Long) As Long
    mdl_patch_npit = m_p_npit(i)
End Function

Public Function mdl_patch_off(ByVal i As Long, ByVal j As Long) As Double
    mdl_patch_off = m_p_off(i, j)
End Function

Public Function mdl_patch_pitcoef(ByVal i As Long, ByVal j As Long) As Double
    mdl_patch_pitcoef = m_p_pitcoef(i, j)
End Function

' Метрика патча по имени поля документа (как ключи metrics в .pappa.json).
Public Function mdl_patch_metric(ByVal i As Long, ByVal name As String) As Double
    Select Case name
        Case "amplitude_mm": mdl_patch_metric = m_p_amplitude(i)
        Case "mean_radius_mm": mdl_patch_metric = m_p_mean_r(i)
        Case "amplitude_norm": mdl_patch_metric = m_p_amp_norm(i)
        Case "deg_elbow_tol": mdl_patch_metric = m_p_degtol(i)
        Case "rmse_selected_mm": mdl_patch_metric = m_p_rmse_sel(i)
        Case "rmse_best_mm": mdl_patch_metric = m_p_rmse_best(i)
        Case "rmse_mm": mdl_patch_metric = m_p_rmse(i)
        Case "mae_mm": mdl_patch_metric = m_p_mae(i)
        Case "max_err_mm": mdl_patch_metric = m_p_maxerr(i)
        Case "correlation": mdl_patch_metric = m_p_corr(i)
        Case Else: Err.Raise vbObjectError + 5, "Pappa", "mdl_patch_metric: unknown metric " & name
    End Select
End Function

' --- параметры модели (шапка манифеста и документа) ---

Public Function mdl_cfg_n_patches() As Long
    mdl_cfg_n_patches = m_n_patches
End Function

Public Function mdl_cfg_phase_deg() As Double
    mdl_cfg_phase_deg = m_phase_deg
End Function

Public Function mdl_cfg_deg_min() As Long
    mdl_cfg_deg_min = m_deg_min
End Function

Public Function mdl_cfg_deg_max() As Long
    mdl_cfg_deg_max = m_deg_max
End Function

Public Function mdl_cfg_overlap_train() As Double
    mdl_cfg_overlap_train = m_overlap_train
End Function

Public Function mdl_cfg_overlap_use() As Double
    mdl_cfg_overlap_use = m_overlap_use
End Function

Public Function mdl_cfg_deg_elbow_tol() As Double
    mdl_cfg_deg_elbow_tol = m_deg_elbow_tol
End Function

Public Function mdl_cfg_coord_mode() As String
    mdl_cfg_coord_mode = m_coord_mode
End Function

Public Function mdl_cfg_amplitude_scale() As Double
    mdl_cfg_amplitude_scale = m_amplitude_scale
End Function

Public Function mdl_pit_count() As Long
    mdl_pit_count = m_n_pits
End Function

Public Function mdl_pit(ByVal i As Long) As Double
    mdl_pit = m_pits(i)
End Function

Public Function mdl_pit_sigma_deg() As Double
    mdl_pit_sigma_deg = m_sigma_deg
End Function

Public Function mdl_pit_core_sigma() As Double
    mdl_pit_core_sigma = m_core_sigma
End Function

Public Function mdl_pit_window_sigma() As Double
    mdl_pit_window_sigma = m_window_sigma
End Function

Public Function mdl_pit_min_amp() As Double
    mdl_pit_min_amp = m_pit_min_amp
End Function

Public Function mdl_pit_tapering() As Boolean
    mdl_pit_tapering = m_tapering
End Function
