/// Форматирование чисел и строк — всегда InvariantCulture.
/// Локаль машины не должна влиять ни на документы, ни на диагностику:
/// ru-RU дала бы "8,73e-11" и запятую как разделитель дробной части.
///
/// Ловушка F#: printf-спецификаторы (%f/%e) в F# форматируются по ТЕКУЩЕЙ культуре
/// (FSharp.Core зовёт String.Format без CultureInfo). Поэтому в порте нет ни одного
/// "%f" — все числа идут через явный ToString(spec, InvariantCulture).
module Pappa.Fmt

open System
open System.Globalization

/// Инвариантная культура в одном месте: её используют и парсеры, и форматтеры.
let inv = CultureInfo.InvariantCulture

/// Аналог C-шного "%.{digits}e": строчная 'e', как у numpy/Python.
let e (v: float) (digits: int) : string =
    if Double.IsNaN v || Double.IsInfinity v then v.ToString(inv)
    else
        let spec = if digits <= 0 then "0e+00" else "0." + String('0', digits) + "e+00"
        v.ToString(spec, inv)

/// Аналог "%.2e" — самый частый случай в диагностике.
let e2 (v: float) : string = e v 2

/// Аналог "%.1f".
let f1 (v: float) : string = v.ToString("0.0", inv)

/// Аналог "%.0f" с «половиной к ЧЁТНОМУ» (как Python round), а не к большему по модулю.
/// F#-функция round — это ровно Math.Round(x, MidpointRounding.ToEven).
let f0 (v: float) : string = Math.Round(v, MidpointRounding.ToEven).ToString("0", inv)

/// Строка вида "{0,-46}" с выравниванием по левому краю (как в printf).
let pad (s: string) (width: int) : string =
    if isNull s then "" elif width <= 0 then s else s.PadRight(width)

/// Булево для JSON: нижний регистр (string true в F# даёт "True").
let boolStr (b: bool) : string = if b then "true" else "false"
