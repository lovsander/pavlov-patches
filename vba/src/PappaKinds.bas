Attribute VB_Name = "PappaKinds"
Option Explicit

' PAPPA VBA port -- общие константы (аналог fortran/src/pappa_kinds.f90).
'
' Видов у VBA нет: всё считается в Double (это и есть float64 референса), счётчики
' и индексы -- Long (32 бита, как int32 в остальных портах).

Public Const PORT_VERSION As String = "0.1.0"
Public Const PORT_LANGUAGE As String = "vba"

' Емкости как в хостовой сборке C-порта (-DPP_MAX_POINTS=8192, ...):
' сечение 6000 точек требует окна обучения ~1357 точек, а кольцо разворачивается
' на +-360 градусов, поэтому запаса хватает с избытком. Порт пока эти границы
' только проверяет (массивы в VBA динамические), но числа должны совпадать
' с C/Fortran, где точка сверх лимита молча отбрасывается.
Public Const PP_MAX_POINTS As Long = 8192
Public Const PP_MAX_WINDOW As Long = 4096
Public Const PP_MAX_PATCHES As Long = 32
Public Const PP_MAX_PITS As Long = 16
Public Const PP_MAX_ZONES As Long = 64
Public Const PP_MAX_DEG As Long = 20

' Точка по умолчанию: значение, к которому приводятся вырожденные случаи.
Public Const PP_NAN_FALLBACK As Double = 0#

' Выбор членов при вычислении контура (как PART_* в остальных портах):
' весь контур, только полином патча, только ямные термы.
Public Const PART_TOTAL As Long = 0
Public Const PART_POLY As Long = 1
Public Const PART_PIT As Long = 2
