/// Сигнальные утилиты — поведение как у numpy и как в соседних портах:
/// медиана (чётное n — среднее двух центральных), перцентиль с линейной
/// интерполяцией, MAD/робастная sigma, IQR, окна по кольцу.
module Pappa.Signal

open System
open System.Collections.Generic

let medianOfSorted (sorted: float[]) : float =
    let n = sorted.Length
    if n = 0 then 0.0
    elif n % 2 = 1 then sorted.[n / 2]
    else 0.5 * (sorted.[n / 2 - 1] + sorted.[n / 2])

let median (x: float[]) : float =
    if isNull x || x.Length = 0 then 0.0
    else
        let v = Array.copy x
        Array.Sort v
        medianOfSorted v

/// Медиана, которая портит (сортирует) переданный scratch-массив.
let private medianInPlace (scratch: float[]) : float =
    Array.Sort scratch
    medianOfSorted scratch

/// Перцентиль с линейной интерполяцией (как np.percentile, method="linear").
let percentileLinear (x: float[]) (q: float) : float =
    let n = x.Length
    if n = 0 then 0.0
    else
        let v = Array.copy x
        Array.Sort v
        let pos = (q / 100.0) * float (n - 1)
        let lo = int (Math.Floor pos)
        let frac = pos - float lo
        let hi = Math.Min(lo + 1, n - 1)
        v.[lo] + frac * (v.[hi] - v.[lo])

let iqr (x: float[]) : float =
    if x.Length = 0 then 0.0 else percentileLinear x 75.0 - percentileLinear x 25.0

let mad (x: float[]) : float =
    if isNull x || x.Length = 0 then 0.0
    else
        let m = median x
        x |> Array.map (fun v -> Math.Abs(v - m)) |> median

let robustSigma (x: float[]) : float = 1.4826 * mad x

/// Медианный шаг сетки по углам (медиана положительных разностей, иначе 1).
let angularStep (angles: float[]) : float =
    if angles.Length < 2 then 1.0
    else
        let d = ResizeArray<float>(angles.Length - 1)
        for i in 1 .. angles.Length - 1 do
            let s = angles.[i] - angles.[i - 1]
            if s > 0.0 then d.Add s
        if d.Count = 0 then 1.0 else median (d.ToArray())

/// Ширина окна в точках: round(span/шаг) «половина к ЧЁТНОМУ», нечётная.
/// Ловушка №1 (обратная C#): в F# round — это уже банковское округление
/// (MidpointRounding.ToEven), ровно как Math.Round(x, ToEven) в C#-порте;
/// голый Math.Round(x) в C# округлил бы половину ОТ НУЛЯ и окна разъехались бы
/// (в Python round(2.5) == 2).
let windowPoints (angles: float[]) (spanDeg: float) : int =
    let n = angles.Length
    if n < 3 then Math.Max(1, n)
    else
        let mutable w = int64 (Math.Round(spanDeg / angularStep angles, MidpointRounding.ToEven))
        if w % 2L = 0L then w <- w + 1L
        if w < 3L then w <- 3L
        if w > int64 n then w <- (if n % 2 = 1 then int64 n else int64 (n - 1))
        int (Math.Max(3L, w))

let private oddWindow (window: int) (n: int) : int =
    let mutable w = if window % 2 = 0 then window + 1 else window
    if w < 3 then w <- 3
    if w > n then w <- (if n % 2 = 1 then n else n - 1)
    w

/// Индекс по кольцу. Ловушка №2: и в F#, и в C# (-1 % n) == -1, а не n-1 —
/// у int-остатка знак делимого, поэтому нужна двойная нормализация.
let wrapIndex (i: int) (n: int) : int = ((i % n) + n) % n

/// Медианный фильтр по кольцу (окно в точках).
let medianFilterWrap (x: float[]) (window: int) : float[] =
    let n = x.Length
    let w = oddWindow window n
    let outp = Array.zeroCreate n
    if w < 3 || n < 3 then
        let m = median x
        for i in 0 .. n - 1 do
            outp.[i] <- m
        outp
    else
        let h = (w - 1) / 2
        let win = Array.zeroCreate w
        for i in 0 .. n - 1 do
            for k in 0 .. w - 1 do
                win.[k] <- x.[wrapIndex (i - h + k) n]
            outp.[i] <- medianInPlace win
        outp

/// Скользящее среднее по кольцу (окно в точках).
let smoothWrap (x: float[]) (window: int) : float[] =
    let n = x.Length
    let w = oddWindow window n
    if w < 3 || n < 3 then Array.copy x
    else
        let h = (w - 1) / 2
        let outp = Array.zeroCreate n
        for i in 0 .. n - 1 do
            let mutable s = 0.0
            for k in -h .. h do
                s <- s + x.[wrapIndex (i + k) n]
            outp.[i] <- s / float w
        outp

/// |кратчайшее расстояние по кольцу| (0..180).
let circDist (a: float) (b: float) : float =
    let d = ((a - b + 180.0) % 360.0 + 360.0) % 360.0
    Math.Abs(d - 180.0)

/// Знаковое расстояние по кольцу в (-180, 180].
let circLocal (a: float) (b: float) : float =
    let d = ((a - b + 180.0) % 360.0 + 360.0) % 360.0
    d - 180.0

/// Сглаживание Хермита: 0 вне [0, 1], 1 внутри, между — t²(3−2t).
let smoothstep (t: float) : float =
    if t < 0.0 then 0.0
    elif t > 1.0 then 1.0
    else t * t * (3.0 - 2.0 * t)
