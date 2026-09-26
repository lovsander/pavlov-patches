Attribute VB_Name = "PappaDocument"
Option Explicit

' PAPPA VBA port -- запись папки образца: манифест sample.json и документ
' сечения sections/NN.pappa.json. Формат повторяет поле в поле c/document.c и
' python/pappa/io/model_file.py, поэтому папки разных портов сравниваются
' численно (python/studies/verify_port.py) и проверяются схемами
' (spec/check_schema.py).
'
' Все строки-значения уходят через json_str, то есть в файле оказываются
' ASCII-экранированными (\uXXXX) -- см. шапку PappaJson про ANSI-запись VBA.

' --- маленькие помощники, чтобы текст читался как в C-версии ---

Private Function doc_s(ByVal key As String, ByVal value As String, ByVal ind As String, _
                       ByVal isLast As Boolean) As String
    doc_s = ind & json_str(key) & ": " & json_str(value) & doc_tail(isLast) & vbLf
End Function

Private Function doc_d(ByVal key As String, ByVal value As Double, ByVal ind As String, _
                       ByVal isLast As Boolean) As String
    doc_d = ind & json_str(key) & ": " & json_num(value) & doc_tail(isLast) & vbLf
End Function

Private Function doc_i(ByVal key As String, ByVal value As Long, ByVal ind As String, _
                       ByVal isLast As Boolean) As String
    doc_i = ind & json_str(key) & ": " & json_int(value) & doc_tail(isLast) & vbLf
End Function

Private Function doc_tail(ByVal isLast As Boolean) As String
    If isLast Then
        doc_tail = ""
    Else
        doc_tail = ","
    End If
End Function

' Массив чисел с отступом (коэффициенты, центры ям, dx/amp пар).
' ВАЖНО: массивы в VBA передаются ТОЛЬКО по ссылке -- 'ByVal vals() As Double'
' не компилируется ("Ожидается массив"), поэтому здесь и ниже -- без ByVal.
Private Function doc_num_array(ByVal key As String, vals() As Double, ByVal n As Long, _
                               ByVal ind As String, ByVal isLast As Boolean) As String
    Dim t As String
    Dim i As Long
    t = ind & json_str(key) & ": ["
    For i = 1 To n
        If i > 1 Then t = t & ","
        t = t & vbLf & ind & "  " & json_num(vals(i))
    Next i
    If n > 0 Then t = t & vbLf & ind
    t = t & "]" & doc_tail(isLast) & vbLf
    doc_num_array = t
End Function

' ------------------------------------------------- документ одного сечения

' Документ сечения: раскладка, патчи, статистика. Читает текущее состояние
' модели (PappaModel) -- как C-порт со своим pp_model.
Public Function document_section_text(ByVal section_id As Long, ByVal height_mm As Double, _
                                      ByVal source As String, ByVal description As String, _
                                      ByVal n_points_total As Long, ByVal n_outliers As Long, _
                                      ByVal fit_time_ms As Double) As String
    Dim t As String
    Dim i As Long, k As Long, j As Long
    Dim npt As Long
    Dim vals() As Double
    Dim method As String
    Dim half_sector As Double

    method = "PatchApproximator"
    If mdl_has_pits() Then method = "PitPatchApproximator"
    half_sector = 180# / CDbl(mdl_cfg_n_patches())

    t = "{" & vbLf
    t = t & doc_s("format", "pappa", "  ", False)
    t = t & doc_s("version", "2.0", "  ", False)
    t = t & doc_s("method", method, "  ", False)
    t = t & doc_s("created", io_utc_now(), "  ", False)
    t = t & "  " & json_str("software") & ": {" & json_str("language") & ": " & _
            json_str(PORT_LANGUAGE) & ", " & json_str("pappa_version") & ": " & _
            json_str(PORT_VERSION) & "}," & vbLf

    t = t & "  " & json_str("meta") & ": {" & vbLf
    t = t & doc_i("section_id", section_id, "    ", False)
    t = t & doc_d("height_mm", height_mm, "    ", False)
    t = t & doc_s("source", source, "    ", False)
    t = t & doc_s("description", description, "    ", True)
    t = t & "  }," & vbLf

    t = t & "  " & json_str("global") & ": {" & vbLf
    t = t & "    " & json_str("units") & ": {" & json_str("angle") & ": " & json_str("degree") & _
            ", " & json_str("length") & ": " & json_str("mm") & "}," & vbLf
    t = t & doc_i("n_patches", mdl_cfg_n_patches(), "    ", False)
    t = t & doc_d("half_sector_deg", half_sector, "    ", False)
    t = t & doc_d("phase_deg", mdl_cfg_phase_deg(), "    ", False)
    t = t & doc_d("half_train_deg", half_sector + mdl_cfg_overlap_train(), "    ", False)
    t = t & doc_d("half_use_deg", half_sector + mdl_cfg_overlap_use(), "    ", False)
    t = t & doc_d("overlap_train_deg", mdl_cfg_overlap_train(), "    ", False)
    t = t & doc_d("overlap_use_deg", mdl_cfg_overlap_use(), "    ", False)
    t = t & doc_i("deg_min", mdl_cfg_deg_min(), "    ", False)
    t = t & doc_i("deg_max", mdl_cfg_deg_max(), "    ", False)
    t = t & doc_s("coord_mode", mdl_cfg_coord_mode(), "    ", False)
    t = t & doc_d("deg_elbow_tol", mdl_cfg_deg_elbow_tol(), "    ", False)
    t = t & doc_d("amplitude_scale", mdl_cfg_amplitude_scale(), "    ", Not mdl_has_pits())
    If mdl_has_pits() Then
        t = t & "    " & json_str("pit") & ": {" & vbLf
        t = t & doc_d("sigma_deg", mdl_pit_sigma_deg(), "      ", False)
        t = t & doc_d("core_sigma", mdl_pit_core_sigma(), "      ", False)
        t = t & doc_d("window_sigma", mdl_pit_window_sigma(), "      ", False)
        t = t & doc_d("pit_min_amp", mdl_pit_min_amp(), "      ", False)
        t = t & "      " & json_str("tapering") & ": " & _
                IIf(mdl_pit_tapering(), "true", "false") & "," & vbLf
        npt = mdl_pit_count()
        ReDim vals(1 To npt + 1)
        For i = 1 To npt
            vals(i) = mdl_pit(i)
        Next i
        t = t & doc_num_array("centers_deg", vals, npt, "      ", True)
        t = t & "    }" & vbLf
    End If
    t = t & "  }," & vbLf
' >>> PATHS
    ' --- patches ---
    t = t & "  " & json_str("patches") & ": [" & vbLf
    For i = 1 To mdl_npatch()
        t = t & "    {" & vbLf
        t = t & doc_d("center_deg", mdl_patch_center(i), "      ", False)
        t = t & doc_i("degree", mdl_patch_degree(i), "      ", False)
        t = t & doc_i("n_points", mdl_patch_npoints(i), "      ", False)
        ReDim vals(1 To mdl_patch_degree(i) + 1)
        For k = 1 To mdl_patch_degree(i) + 1
            vals(k) = mdl_patch_coef(i, k)
        Next k
        t = t & doc_num_array("coefs", vals, mdl_patch_degree(i) + 1, "      ", False)
        t = t & "      " & json_str("metrics") & ": {" & vbLf
        t = t & doc_d("amplitude_mm", mdl_patch_metric(i, "amplitude_mm"), "        ", False)
        t = t & doc_d("mean_radius_mm", mdl_patch_metric(i, "mean_radius_mm"), "        ", False)
        t = t & doc_d("amplitude_norm", mdl_patch_metric(i, "amplitude_norm"), "        ", False)
        t = t & doc_d("deg_elbow_tol", mdl_patch_metric(i, "deg_elbow_tol"), "        ", False)
        t = t & doc_d("rmse_selected_mm", mdl_patch_metric(i, "rmse_selected_mm"), "        ", False)
        t = t & doc_d("rmse_best_mm", mdl_patch_metric(i, "rmse_best_mm"), "        ", False)
        t = t & doc_i("n_train_points", mdl_patch_npoints(i), "        ", True)
        t = t & "      }," & vbLf
        t = t & "      " & json_str("stats") & ": {" & vbLf
        t = t & doc_d("rmse_mm", mdl_patch_metric(i, "rmse_mm"), "        ", False)
        t = t & doc_d("mae_mm", mdl_patch_metric(i, "mae_mm"), "        ", False)
        t = t & doc_d("max_err_mm", mdl_patch_metric(i, "max_err_mm"), "        ", False)
        t = t & doc_d("correlation", mdl_patch_metric(i, "correlation"), "        ", True)
        t = t & "      }"
        If mdl_has_pits() Then
            ' pit_terms пишется у КАЖДОГО патча модели с ямами (включая пустой
            ' список) -- как в остальных портах.
            t = t & "," & vbLf
            t = t & "      " & json_str("pit_terms") & ": ["
            For j = 1 To mdl_patch_npit(i)
                If j > 1 Then t = t & ", "
                t = t & "{" & json_str("dx_deg") & ": " & json_num(mdl_patch_off(i, j)) & _
                        ", " & json_str("amp") & ": " & json_num(mdl_patch_pitcoef(i, j)) & "}"
            Next j
            t = t & "]" & vbLf
        Else
            t = t & vbLf
        End If
        If i < mdl_npatch() Then
            t = t & "    }," & vbLf
        Else
            t = t & "    }" & vbLf
        End If
    Next i
    t = t & "  ]," & vbLf

    ' --- statistics ---
    t = t & "  " & json_str("statistics") & ": {" & vbLf
    t = t & doc_i("n_points_total", n_points_total, "    ", False)
    t = t & doc_i("n_outliers_removed", n_outliers, "    ", False)
    t = t & doc_d("fit_time_ms", fit_time_ms, "    ", True)
    t = t & "  }" & vbLf
    t = t & "}" & vbLf
    document_section_text = t
End Function

' Имя файла документа сечения в манифесте (sections/NN.pappa.json).
Public Function document_section_file(ByVal i As Long) As String
    document_section_file = "sections/" & Format$(i, "00") & ".pappa.json"
End Function

' ------------------------------------------------------------ манифест папки

' Манифест sample.json: единицы, конфиг метода, список сечений, след входного
' CSV. Значения конфига берутся из текущего состояния модели (все сечения
' обучаются с одним конфигом), счётчики сечений -- из переданных массивов.
Public Function document_manifest_text(ByVal sample_name As String, ByVal description As String, _
                                       ByVal input_csv As String, ByVal cl_base As Double, _
                                       ByVal cl_k As Double, ByVal pits As Boolean, _
                                       sec_id() As Long, sec_height() As Double, _
                                       sec_npoints() As Long, sec_nout() As Long, _
                                       ByVal nsec As Long) As String
    Dim t As String
    Dim i As Long

    t = "{" & vbLf
    t = t & doc_s("format", "pappa-sample", "  ", False)
    t = t & doc_s("version", "1.0", "  ", False)
    t = t & doc_s("name", sample_name, "  ", False)
    t = t & doc_s("created", io_utc_now(), "  ", False)
    t = t & "  " & json_str("units") & ": {" & json_str("angle") & ": " & json_str("degree") & _
            ", " & json_str("length") & ": " & json_str("mm") & "}," & vbLf
    t = t & "  " & json_str("meta") & ": {" & json_str("description") & ": " & _
            json_str(description) & "}," & vbLf
    If Len(input_csv) > 0 Then
        t = t & "  " & json_str("input") & ": {" & json_str("csv") & ": " & _
                json_str(input_csv) & "}," & vbLf
    End If

    t = t & "  " & json_str("config") & ": {" & vbLf
    t = t & doc_i("n_patches", mdl_cfg_n_patches(), "    ", False)
    t = t & doc_d("phase_deg", mdl_cfg_phase_deg(), "    ", False)
    t = t & doc_i("deg_min", mdl_cfg_deg_min(), "    ", False)
    t = t & doc_i("deg_max", mdl_cfg_deg_max(), "    ", False)
    t = t & doc_d("overlap_train", mdl_cfg_overlap_train(), "    ", False)
    t = t & doc_d("overlap_use", mdl_cfg_overlap_use(), "    ", False)
    t = t & doc_d("deg_elbow_tol", mdl_cfg_deg_elbow_tol(), "    ", False)
    t = t & "    " & json_str("cleaner") & ": {" & json_str("mode") & ": " & json_str("auto") & _
            ", " & json_str("auto") & ": {" & json_str("method") & ": " & json_str("iqr") & _
            ", " & json_str("baseline_deg") & ": " & json_num(cl_base) & _
            ", " & json_str("iqr_k") & ": " & json_num(cl_k) & "}}," & vbLf
    t = t & "    " & json_str("pits") & ": " & IIf(pits, "true", "false")
    If pits Then
        t = t & "," & vbLf
        t = t & doc_d("sigma_deg", mdl_pit_sigma_deg(), "    ", False)
        t = t & doc_d("pit_core_sigma", mdl_pit_core_sigma(), "    ", False)
        t = t & doc_d("pit_window_sigma", mdl_pit_window_sigma(), "    ", False)
        t = t & doc_d("pit_min_amp", mdl_pit_min_amp(), "    ", False)
        t = t & "    " & json_str("tapering") & ": " & _
                IIf(mdl_pit_tapering(), "true", "false") & "," & vbLf
        ' Детектор в манифесте этого порта не сохраняется (как в C-порте):
        ' конфиг детектора уходит в параметры пайплайна, а не в документ.
        t = t & "    " & json_str("detector") & ": null" & vbLf
    Else
        t = t & "," & vbLf
        t = t & "    " & json_str("detector") & ": null" & vbLf
    End If
    t = t & "  }," & vbLf

    t = t & "  " & json_str("sections") & ": [" & vbLf
    For i = 1 To nsec
        t = t & "    {" & vbLf
        t = t & doc_i("index", i - 1, "      ", False)
        t = t & doc_i("section_id", sec_id(i), "      ", False)
        t = t & doc_d("height_mm", sec_height(i), "      ", False)
        t = t & doc_s("file", document_section_file(i - 1), "      ", False)
        t = t & doc_i("n_points", sec_npoints(i), "      ", False)
        t = t & doc_i("n_outliers", sec_nout(i), "      ", True)
        If i < nsec Then
            t = t & "    }," & vbLf
        Else
            t = t & "    }" & vbLf
        End If
    Next i
    t = t & "  ]" & vbLf
    t = t & "}" & vbLf
    document_manifest_text = t
End Function
