Attribute VB_Name = "PappaIo"
Option Explicit

' PAPPA VBA port -- текстовый ввод-вывод и метка времени.
'
' ЛОВУШКА: Open ... For Output в VBA пишет файл в ANSI (cp1251), а документы
' остальных портов лежат в UTF-8. Порт поэтому пишет ТОЛЬКО ASCII: все не-ASCII
' символы строк уходят в JSON как \uXXXX (см. json_str), а такие файлы по
' определению валидны и как UTF-8. Входные файлы (CSV, векторы) приходят в
' ASCII или UTF-8; не-ASCII байты в строках описаний не мешают разбору чисел.
'
' ЛОВУШКА: UTC. У VBA есть только Now (местное время), поэтому UTC берётся у
' системы через GetSystemTime из kernel32 -- единственный вызов Win32 в порте
' (в остальных портах ту же роль играет gmtime/Time.utc). Если бы метка писалась
' из Now, документы получили бы сдвиг часового пояса (та же ловушка, что
' в Octave-порте).

Private Type SYSTEMTIME_UTC
    wYear As Integer
    wMonth As Integer
    wDayOfWeek As Integer
    wDay As Integer
    wHour As Integer
    wMinute As Integer
    wSecond As Integer
    wMilliseconds As Integer
End Type

Private Declare PtrSafe Sub GetSystemTime Lib "kernel32" (lpSystemTime As SYSTEMTIME_UTC)

' Метка времени в формате остальных портов: 2026-09-26T12:34:56Z (UTC).
Public Function io_utc_now() As String
    Dim st As SYSTEMTIME_UTC
    GetSystemTime st
    io_utc_now = Format$(st.wYear, "0000") & "-" & Format$(st.wMonth, "00") & "-" & _
                 Format$(st.wDay, "00") & "T" & Format$(st.wHour, "00") & ":" & _
                 Format$(st.wMinute, "00") & ":" & Format$(st.wSecond, "00") & "Z"
End Function

' ЛОВУШКА: параметр (или локальная переменная) с именем `dir` затеняет встроенную
' Dir -- а Dir$ в VBA есть. Компилятор читает dir$(...) как скаляр с суффиксом
' типа и выдаёт "Expected array" (проверено спайком, см. README порта).
'
' ЛОВУШКА: наличие пути проверяется через GetAttr, а не через Dir (проверено
' спайком). Dir(path, vbDirectory) не возвращает скрытые каталоги --
' "C:\Users\<user>\AppData" скрытый, -- поэтому io_make_dir считал существующий
' каталог отсутствующим, вызывал MkDir и падал с ошибкой 75 "Path/File access
' error". Кроме того, у Dir с атрибутами путь с хвостовым "\" даёт ошибку 52
' "Bad file name or number" (у GetAttr -- нет), а Dir(path, vbDirectory) считает
' совпадением и обычный файл. GetAttr возвращает атрибуты (vbDirectory -- бит
' каталога), а отсутствие пути даёт ошибку 53/76 в err_no.
Private Function io_attr(ByVal path As String, ByRef err_no As Long) As Long
    Dim attr As Long
    attr = 0
    err_no = 0
    On Error Resume Next
    Err.Clear
    attr = GetAttr(path)
    err_no = Err.Number
    On Error GoTo 0
    io_attr = attr
End Function

' Файл существует (каталог файлом не считается; скрытые файлы видны).
Public Function io_file_exists(ByVal path As String) As Boolean
    Dim err_no As Long
    Dim attr As Long
    attr = io_attr(path, err_no)
    io_file_exists = (err_no = 0) And ((attr And vbDirectory) = 0)
End Function

' Каталог существует (включая скрытые и системные, в отличие от Dir).
Public Function io_dir_exists(ByVal path As String) As Boolean
    Dim err_no As Long
    Dim attr As Long
    attr = io_attr(path, err_no)
    io_dir_exists = (err_no = 0) And ((attr And vbDirectory) = vbDirectory)
End Function

' Создать каталог со всеми родителями (аналог PP_MKDIR в C-порте).
' UNC-пути не поддерживаются: в порте используются только локальные пути.
Public Sub io_make_dir(ByVal path As String)
    Dim parts() As String
    Dim cur As String
    Dim i As Long

    path = Replace(path, "/", "\")
    parts = Split(path, "\")
    cur = ""
    For i = LBound(parts) To UBound(parts)
        If parts(i) <> "" Then
            If i = LBound(parts) Then
                cur = parts(i)                    ' "C:" или первый каталог
            Else
                cur = cur & "\" & parts(i)
            End If
            If Len(cur) > 2 Then                  ' сам диск ("C:") не создаём
                If Not io_dir_exists(cur) Then MkDir cur
            End If
        End If
    Next i
End Sub

' Трассировка для отладки: пишет строку в файл из переменной окружения
' PAPPA_VBA_TRACE (скрипт сборки ставит туда vba/build/trace.log). Без переменной
' ничего не делает. Нужна потому, что VBA не умеет печатать в консоль, а зависший
' прогон иначе неотличим от медленного.
Public Sub io_trace(ByVal text As String)
    Dim path As String, f As Integer
    path = Environ$("PAPPA_VBA_TRACE")
    If Len(path) = 0 Then Exit Sub
    f = FreeFile
    Open path For Append As #f
    Print #f, text
    Close #f
End Sub

' Прочитать небольшой текстовый файл целиком (документы, векторы).
Public Function io_read_text(ByVal path As String) As String
    Dim f As Integer, s As String, line As String
    If Not io_file_exists(path) Then
        Err.Raise vbObjectError + 20, "Pappa", "нет файла: " & path
    End If
    f = FreeFile
    Open path For Input As #f
    Do While Not EOF(f)
        Line Input #f, line
        s = s & line & vbLf
    Loop
    Close #f
    io_read_text = s
End Function

' Прочитать файл построчно (CSV на 60 000 строк: конкатенация в строку была бы
' квадратичной, поэтому строки возвращаются массивом).
Public Sub io_read_lines(ByVal path As String, ByRef lines() As String, ByRef n As Long)
    Dim f As Integer, line As String
    Dim cap As Long
    If Not io_file_exists(path) Then
        Err.Raise vbObjectError + 20, "Pappa", "нет файла: " & path
    End If
    n = 0
    cap = 1024
    ReDim lines(1 To cap)
    f = FreeFile
    Open path For Input As #f
    Do While Not EOF(f)
        Line Input #f, line
        n = n + 1
        If n > cap Then
            cap = cap * 2
            ReDim Preserve lines(1 To cap)
        End If
        lines(n) = line
    Loop
    Close #f
End Sub

' Записать текст в файл (содержимое обязано быть ASCII -- см. шапку модуля).
Public Sub io_write_text(ByVal path As String, ByVal text As String)
    Dim f As Integer
    f = FreeFile
    Open path For Output As #f
    Print #f, text;
    Close #f
End Sub
