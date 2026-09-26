Attribute VB_Name = "PappaJson"
Option Explicit

' PAPPA VBA port -- свой мини-JSON: разбор, дерево в ПЛОСКОМ массиве, запись.
' Соответствует octave/src/json_*.m и fortran/src/pappa_json.f90.
'
' ЛОВУШКИ VBA, определившие устройство модуля (см. vba/README.md):
'   * Format$/Str печатают не больше 15 значащих цифр (проверено: 1/3 даёт
'     ...3333300), поэтому побайтовый round-trip документа невозможен --
'     числа пишутся с 15 цифрами, а тесты сравнивают с допуском 1e-14 отн.;
'     на приёмку это не влияет (контур 1e-6 мм, коэффициенты 1e-9);
'   * в русской локали Format$ ставит ЗАПЯТУЮ, а CDbl("1.5") даёт ошибку 13 --
'     парсим числа только через Val (он не зависит от локали), а в строках
'     чисел заменяем запятую на точку;
'   * Open For Output пишет файлы в ANSI (cp1251), а документы остальных портов
'     в UTF-8. Поэтому json_str экранирует ВСЁ не-ASCII как \uXXXX: документ
'     получается ASCII, а он же -- валидный UTF-8, и Python читает его как надо;
'   * объектов-словарей (Scripting.Dictionary) у нас нет намеренно: это внешняя
'     зависимость. Дерево живёт в плоских массивах (как арена в Fortran-порте).

' --- арена узлов: id 1..m_n, 0 = «нет узла» ---
Private m_cap As Long
Private m_n As Long
Private m_kind() As String        ' "obj" | "arr" | "str" | "num" | "bool" | "null"
Private m_num() As Double
Private m_str() As String
Private m_bool() As Boolean
Private m_name() As String        ' ключ члена объекта ("" для элементов массива)
Private m_first() As Long         ' первый ребёнок
Private m_last() As Long          ' последний ребёнок (вставка за O(1))
Private m_next() As Long          ' следующий брат

' --- состояние разбора ---
Private m_text As String
Private m_pos As Long
Private m_err As String

Public Sub json_reset()
    m_n = 0
    m_cap = 0
    m_text = ""
    m_pos = 1
    m_err = ""
End Sub

Private Sub js_ensure(ByVal need As Long)
    Dim cap As Long
    If need <= m_cap Then Exit Sub
    cap = m_cap
    If cap < 64 Then cap = 64
    Do While cap < need
        cap = cap * 2
    Loop
    ReDim Preserve m_kind(1 To cap)
    ReDim Preserve m_num(1 To cap)
    ReDim Preserve m_str(1 To cap)
    ReDim Preserve m_bool(1 To cap)
    ReDim Preserve m_name(1 To cap)
    ReDim Preserve m_first(1 To cap)
    ReDim Preserve m_last(1 To cap)
    ReDim Preserve m_next(1 To cap)
    m_cap = cap
End Sub

Public Function json_node(ByVal kind As String) As Long
    m_n = m_n + 1
    js_ensure m_n
    m_kind(m_n) = kind
    m_num(m_n) = 0#
    m_str(m_n) = ""
    m_bool(m_n) = False
    m_name(m_n) = ""
    m_first(m_n) = 0
    m_last(m_n) = 0
    m_next(m_n) = 0
    json_node = m_n
End Function

' Приписать узел ребёнком (для объекта с именем, для массива с именем "").
Private Sub js_link(ByVal parent As Long, ByVal child As Long, ByVal nm As String)
    m_name(child) = nm
    If m_first(parent) = 0 Then
        m_first(parent) = child
    Else
        m_next(m_last(parent)) = child
    End If
    m_last(parent) = child
    m_next(child) = 0
End Sub

' ------------------------------------------------------------- запись чисел

' Число в стиле "%.17g" из C/C++ -- НО VBA печатает максимум 15 значащих цифр
' (проверено: 1/3 даёт 3.3333333333333300E-01), поэтому документ читается
' обратно с точностью ~1e-15 отн., а не побитово. На приёмку это не влияет
' (контур 1e-6 мм, коэффициенты max(1e-8, 1e-9|c|)), но честно записано и
' в README, и в тесте round-trip.
Public Function json_num(ByVal v As Double) As String
    Dim s As String, an As Double
    Dim ep As Long, mant As String, ex As String, sign As String

    If v = 0# Then
        json_num = "0"
        Exit Function
    End If
    an = Abs(v)
    If an >= 0.0001 And an < 1E+15 Then
        s = Format$(an, "0.###############")
        s = Replace(s, ",", ".")            ' локаль может дать запятую
        If InStr(s, ".") > 0 Then
            Do While Right$(s, 1) = "0"
                s = Left$(s, Len(s) - 1)
            Loop
            If Right$(s, 1) = "." Then s = Left$(s, Len(s) - 1)
        End If
    Else
        ' Очень большие/малые -- экспонента (валидный JSON, Python парсит).
        s = Format$(an, "0.##############E+00")
        s = Replace(s, ",", ".")
        ep = InStr(s, "E")
        mant = Left$(s, ep - 1)
        ex = Mid$(s, ep + 1)
        If InStr(mant, ".") > 0 Then
            Do While Right$(mant, 1) = "0"
                mant = Left$(mant, Len(mant) - 1)
            Loop
            If Right$(mant, 1) = "." Then mant = Left$(mant, Len(mant) - 1)
        End If
        sign = Left$(ex, 1)
        If sign = "+" Or sign = "-" Then
            ex = Mid$(ex, 2)
        Else
            sign = "+"
        End If
        Do While Len(ex) > 1 And Left$(ex, 1) = "0"
            ex = Mid$(ex, 2)
        Loop
        s = mant & "e" & sign & ex
    End If
    If v < 0# Then s = "-" & s
    json_num = s
End Function

' Целое без разделителей (в шаблон "0" локаль не подмешивается).
Public Function json_int(ByVal n As Long) As String
    json_int = Format$(n, "0")
End Function

' Строка JSON в кавычках. Всё не-ASCII уходит \uXXXX: файлы документов
' остаются ASCII, а значит корректно читаются как UTF-8 (VBA пишет ANSI).
Public Function json_str(ByVal s As String) As String
    Dim out As String, c As Long
    Dim i As Long
    out = """"
    For i = 1 To Len(s)
        c = AscW(Mid$(s, i, 1))
        If c < 0 Then c = c + 65536
        Select Case c
            Case 34
                out = out & "\"""
            Case 92
                out = out & "\\"
            Case 8
                out = out & "\b"
            Case 9
                out = out & "\t"
            Case 10
                out = out & "\n"
            Case 12
                out = out & "\f"
            Case 13
                out = out & "\r"
            Case Is < 32
                out = out & "\u" & Right$("000" & Hex$(c), 4)
            Case Is > 126
                out = out & "\u" & Right$("000" & Hex$(c), 4)
            Case Else
                out = out & Chr$(c)
        End Select
    Next i
    json_str = out & """"
End Function

' -------------------------------------------------------------------- разбор

' Разбор текста JSON: возвращает id корневого узла, 0 -- ошибка (json_error).
Public Function json_parse(ByVal text As String) As Long
    Dim id As Long
    json_reset
    m_text = text
    m_pos = 1
    id = js_parse_value()
    If id <> 0 Then
        js_skip_ws
        If m_pos <= Len(m_text) Then
            js_fail "лишние данные после значения"
            id = 0
        End If
    End If
    json_parse = id
End Function

Public Function json_error() As String
    json_error = m_err
End Function

Private Sub js_fail(ByVal msg As String)
    If m_err = "" Then m_err = msg & " (позиция " & CStr(m_pos) & ")"
End Sub

Private Sub js_skip_ws()
    Dim c As String
    Do While m_pos <= Len(m_text)
        c = Mid$(m_text, m_pos, 1)
        If c = " " Or c = vbTab Or c = vbCr Or c = vbLf Then
            m_pos = m_pos + 1
        Else
            Exit Do
        End If
    Loop
End Sub

Private Function js_parse_value() As Long
    Dim c As String
    js_skip_ws
    If m_pos > Len(m_text) Then
        js_fail "неожиданный конец текста"
        Exit Function
    End If
    c = Mid$(m_text, m_pos, 1)
    Select Case c
        Case "{"
            js_parse_value = js_parse_object()
        Case "["
            js_parse_value = js_parse_array()
        Case """"
            js_parse_value = js_parse_string_node()
        Case "t"
            js_parse_value = js_parse_literal("true")
        Case "f"
            js_parse_value = js_parse_literal("false")
        Case "n"
            js_parse_value = js_parse_literal("null")
        Case Else
            js_parse_value = js_parse_number()
    End Select
End Function

Private Function js_parse_literal(ByVal lit As String) As Long
    Dim id As Long
    If Mid$(m_text, m_pos, Len(lit)) <> lit Then
        js_fail "ожидалось " & lit
        Exit Function
    End If
    m_pos = m_pos + Len(lit)
    id = json_node("bool")
    If lit = "true" Then
        m_bool(id) = True
    ElseIf lit = "false" Then
        m_bool(id) = False
    Else
        m_kind(id) = "null"
    End If
    js_parse_literal = id
End Function

Private Function js_parse_object() As Long
    Dim id As Long, child As Long, nm As String
    id = json_node("obj")
    m_pos = m_pos + 1                     ' "{"
    js_skip_ws
    If Mid$(m_text, m_pos, 1) = "}" Then
        m_pos = m_pos + 1
        js_parse_object = id
        Exit Function
    End If
    Do
        js_skip_ws
        If Mid$(m_text, m_pos, 1) <> """" Then
            js_fail "ожидался ключ объекта"
            Exit Function
        End If
        nm = js_read_string()
        If m_err <> "" Then Exit Function
        js_skip_ws
        If Mid$(m_text, m_pos, 1) <> ":" Then
            js_fail "ожидалось двоеточие"
            Exit Function
        End If
        m_pos = m_pos + 1
        child = js_parse_value()
        If child = 0 Then Exit Function
        js_link id, child, nm
        js_skip_ws
        If Mid$(m_text, m_pos, 1) = "," Then
            m_pos = m_pos + 1
        ElseIf Mid$(m_text, m_pos, 1) = "}" Then
            m_pos = m_pos + 1
            Exit Do
        Else
            js_fail "ожидалась запятая или закрывающая скобка"
            Exit Function
        End If
    Loop
    js_parse_object = id
End Function

Private Function js_parse_array() As Long
    Dim id As Long, child As Long
    id = json_node("arr")
    m_pos = m_pos + 1                     ' "["
    js_skip_ws
    If Mid$(m_text, m_pos, 1) = "]" Then
        m_pos = m_pos + 1
        js_parse_array = id
        Exit Function
    End If
    Do
        child = js_parse_value()
        If child = 0 Then Exit Function
        js_link id, child, ""
        js_skip_ws
        If Mid$(m_text, m_pos, 1) = "," Then
            m_pos = m_pos + 1
        ElseIf Mid$(m_text, m_pos, 1) = "]" Then
            m_pos = m_pos + 1
            Exit Do
        Else
            js_fail "ожидалась запятая или закрывающая скобка массива"
            Exit Function
        End If
    Loop
    js_parse_array = id
End Function

Private Function js_parse_string_node() As Long
    Dim id As Long
    id = json_node("str")
    m_str(id) = js_read_string()
    If m_err <> "" Then Exit Function
    js_parse_string_node = id
End Function

' Число: символы [0-9+-.eE] в строку, затем Val -- он не зависит от локали
' (CDbl в русской локали падает на "1.5" с ошибкой 13).
Private Function js_parse_number() As Long
    Dim id As Long, s As String, c As String
    s = ""
    Do While m_pos <= Len(m_text)
        c = Mid$(m_text, m_pos, 1)
        If (c >= "0" And c <= "9") Or c = "-" Or c = "+" Or c = "." Or c = "e" Or c = "E" Then
            s = s & c
            m_pos = m_pos + 1
        Else
            Exit Do
        End If
    Loop
    If s = "" Then
        js_fail "ожидалось число"
        Exit Function
    End If
    id = json_node("num")
    m_num(id) = Val(s)
    js_parse_number = id
End Function

' Строка в кавычках: возвращает раскодированный текст, m_pos остаётся сразу
' после закрывающей кавычки.
Private Function js_read_string() As String
    Dim out As String, c As String, hexs As String
    Dim code As Long
    m_pos = m_pos + 1                     ' открывающая кавычка
    out = ""
    Do While m_pos <= Len(m_text)
        c = Mid$(m_text, m_pos, 1)
        m_pos = m_pos + 1
        If c = """" Then
            js_read_string = out
            Exit Function
        ElseIf c = "\" Then
            If m_pos > Len(m_text) Then Exit Do
            c = Mid$(m_text, m_pos, 1)
            m_pos = m_pos + 1
            Select Case c
                Case """"
                    out = out & """"
                Case "\"
                    out = out & "\"
                Case "/"
                    out = out & "/"
                Case "b"
                    out = out & Chr$(8)
                Case "f"
                    out = out & Chr$(12)
                Case "n"
                    out = out & Chr$(10)
                Case "r"
                    out = out & Chr$(13)
                Case "t"
                    out = out & Chr$(9)
                Case "u"
                    hexs = Mid$(m_text, m_pos, 4)
                    m_pos = m_pos + 4
                    code = CLng("&H" & hexs)
                    out = out & ChrW$(code)
                Case Else
                    js_fail "неизвестная escape-последовательность"
                    Exit Function
            End Select
        Else
            out = out & c
        End If
    Loop
    js_fail "незакрытая строка"
End Function

' ----------------------------------------------------------- доступ к дереву

' Член объекта по имени (0 -- нет такого).
Public Function jp_member(ByVal id As Long, ByVal nm As String) As Long
    Dim c As Long
    If id = 0 Then Exit Function
    c = m_first(id)
    Do While c <> 0
        If m_name(c) = nm Then
            jp_member = c
            Exit Function
        End If
        c = m_next(c)
    Loop
End Function

' k-й ребёнок (1..jp_count), 0 -- за пределами.
Public Function jp_child(ByVal id As Long, ByVal k As Long) As Long
    Dim c As Long, i As Long
    If id = 0 Then Exit Function
    c = m_first(id)
    i = 1
    Do While c <> 0
        If i = k Then
            jp_child = c
            Exit Function
        End If
        i = i + 1
        c = m_next(c)
    Loop
End Function

' Число детей (элементов массива, членов объекта).
Public Function jp_count(ByVal id As Long) As Long
    Dim c As Long, i As Long
    If id = 0 Then Exit Function
    c = m_first(id)
    Do While c <> 0
        i = i + 1
        c = m_next(c)
    Loop
    jp_count = i
End Function

Public Function jp_kind(ByVal id As Long) As String
    If id = 0 Then Exit Function
    jp_kind = m_kind(id)
End Function

Public Function jp_is_null(ByVal id As Long) As Boolean
    If id = 0 Then Exit Function
    jp_is_null = (m_kind(id) = "null")
End Function

Public Function jp_num(ByVal id As Long) As Double
    If id = 0 Then Exit Function
    jp_num = m_num(id)
End Function

Public Function jp_str(ByVal id As Long) As String
    If id = 0 Then Exit Function
    jp_str = m_str(id)
End Function

Public Function jp_bool(ByVal id As Long) As Boolean
    If id = 0 Then Exit Function
    jp_bool = m_bool(id)
End Function

' Число по пути "a.b.c": удобно для векторов и документов.
Public Function jp_path_num(ByVal root As Long, ByVal path As String) As Double
    jp_path_num = jp_num(jp_path(root, path))
End Function

Public Function jp_path_str(ByVal root As Long, ByVal path As String) As String
    jp_path_str = jp_str(jp_path(root, path))
End Function

Public Function jp_path_bool(ByVal root As Long, ByVal path As String) As Boolean
    jp_path_bool = jp_bool(jp_path(root, path))
End Function

Public Function jp_path_count(ByVal root As Long, ByVal path As String) As Long
    jp_path_count = jp_count(jp_path(root, path))
End Function

' Массив чисел JSON -> 1-базный Double-массив (для входов векторов).
Public Sub jp_num_array(ByVal node As Long, ByRef out() As Double, ByRef n As Long)
    Dim i As Long
    n = jp_count(node)
    ReDim out(1 To n)
    For i = 1 To n
        out(i) = jp_num(jp_child(node, i))
    Next i
End Sub

Public Function jp_path(ByVal root As Long, ByVal path As String) As Long
    Dim parts() As String
    Dim id As Long
    Dim i As Long
    id = root
    If path = "" Then
        jp_path = id
        Exit Function
    End If
    parts = Split(path, ".")
    For i = LBound(parts) To UBound(parts)
        id = jp_member(id, parts(i))
        If id = 0 Then Exit Function
    Next i
    jp_path = id
End Function

' -------------------------------------------------------------------- запись

' Сборка текста JSON из дерева (round-trip в самопроверке и отладка).
Public Function json_render(ByVal id As Long) As String
    Dim out As String
    js_render_into id, out
    json_render = out
End Function

Private Sub js_render_into(ByVal id As Long, ByRef out As String)
    Dim c As Long, k As Long
    Select Case m_kind(id)
        Case "obj"
            out = out & "{"
            c = m_first(id)
            k = 0
            Do While c <> 0
                If k > 0 Then out = out & ","
                out = out & json_str(m_name(c)) & ":"
                js_render_into c, out
                k = k + 1
                c = m_next(c)
            Loop
            out = out & "}"
        Case "arr"
            out = out & "["
            c = m_first(id)
            k = 0
            Do While c <> 0
                If k > 0 Then out = out & ","
                js_render_into c, out
                k = k + 1
                c = m_next(c)
            Loop
            out = out & "]"
        Case "str"
            out = out & json_str(m_str(id))
        Case "num"
            out = out & json_num(m_num(id))
        Case "bool"
            If m_bool(id) Then
                out = out & "true"
            Else
                out = out & "false"
            End If
        Case Else
            out = out & "null"
    End Select
End Sub
