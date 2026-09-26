/// Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.linalg.lstsq /
/// np.polyfit) + базис Чебышёва для быстрого выбора степени.
module Pappa.Linalg

open System

/// Решение МНК A·x ≈ b (A — m×n, m >= n) через QR Хаусхолдера. Вход не портится.
/// Ловушка F#: массивы — ссылочный тип, копия делается явно (Array.copy), иначе
/// отражения Хаусхолдера испортили бы матрицу вызывающего (в C# там был Clone).
let lstsqQR (aIn: float[][]) (bIn: float[]) : float[] =
    let m = aIn.Length
    if m = 0 then invalidArg "aIn" "LstsqQR: пустая матрица"
    let n = aIn.[0].Length
    if bIn.Length <> m then invalidArg "bIn" "LstsqQR: длины A и b не совпадают"
    if m < n then invalidArg "aIn" "LstsqQR: нужно m >= n"

    let a = Array.init m (fun i -> Array.copy aIn.[i])
    let b = Array.copy bIn

    for k in 0 .. n - 1 do
        let mutable norm = 0.0
        for i in k .. m - 1 do
            norm <- norm + a.[i].[k] * a.[i].[k]
        norm <- Math.Sqrt norm
        if norm >= 1e-300 then
            let alpha = if a.[k].[k] > 0.0 then -norm else norm
            let v = Array.zeroCreate m
            for i in k .. m - 1 do
                v.[i] <- a.[i].[k]
            v.[k] <- v.[k] - alpha
            let mutable vnorm2 = 0.0
            for i in k .. m - 1 do
                vnorm2 <- vnorm2 + v.[i] * v.[i]
            if vnorm2 >= 1e-300 then
                for j in k .. n - 1 do
                    let mutable s = 0.0
                    for i in k .. m - 1 do
                        s <- s + v.[i] * a.[i].[j]
                    let c = 2.0 * s / vnorm2
                    for i in k .. m - 1 do
                        a.[i].[j] <- a.[i].[j] - c * v.[i]
                let mutable sb = 0.0
                for i in k .. m - 1 do
                    sb <- sb + v.[i] * b.[i]
                let cb = 2.0 * sb / vnorm2
                for i in k .. m - 1 do
                    b.[i] <- b.[i] - cb * v.[i]

    let x = Array.zeroCreate n
    for i in n - 1 .. -1 .. 0 do
        let mutable s = b.[i]
        for j in i + 1 .. n - 1 do
            s <- s - a.[i].[j] * x.[j]
        let d = a.[i].[i]
        if Math.Abs d < 1e-300 then failwith "LstsqQR: вырожденная система"
        x.[i] <- s / d
    x

/// Полином: коэффициенты по УБЫВАНИЮ степени (как polyfit/polyval).
let polyval (coefs: float[]) (x: float) : float =
    let mutable r = 0.0
    for c in coefs do
        r <- r * x + c
    r

let polyfit (xs: float[]) (ys: float[]) (deg: int) : float[] =
    let m = xs.Length
    let n = deg + 1
    let a =
        Array.init m (fun i ->
            let row = Array.zeroCreate n
            let mutable p = 1.0
            for j in 0 .. n - 1 do
                row.[n - 1 - j] <- p
                p <- p * xs.[i]
            row)
    lstsqQR a ys

/// T_0(x)..T_degMax(x) — базис Чебышёва (x ∈ [-1, 1]).
let chebRow (x: float) (degMax: int) : float[] =
    let t = Array.zeroCreate (degMax + 1)
    t.[0] <- 1.0
    if degMax >= 1 then t.[1] <- x
    for k in 2 .. degMax do
        t.[k] <- 2.0 * x * t.[k - 1] - t.[k - 2]
    t

/// Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
let chebSum (c: float[]) (deg: int) (x: float) : float =
    let mutable b1 = 0.0
    let mutable b2 = 0.0
    for k in deg .. -1 .. 1 do
        let b0 = 2.0 * x * b1 - b2 + c.[k]
        b2 <- b1
        b1 <- b0
    x * b1 - b2 + c.[0]
