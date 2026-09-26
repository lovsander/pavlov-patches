namespace Pappa

open System
open System.Collections.Generic

/// Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
/// по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
/// Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py) и порты
/// C/C++/Go/JS/Java/Kotlin/Pascal/Swift/Julia/R/C#/VBA.
module Cleaner =

    /// Параметры: значения по умолчанию — как в референсе.
    type Options =
        { BaselineDeg: float
          IqrK: float
          MaxRemovedFrac: float
          MinPoints: int }

    let defaultOptions =
        { BaselineDeg = 1.0
          IqrK = 3.0
          MaxRemovedFrac = 0.5
          MinPoints = 20 }

    type Result =
        { Mask: bool[]
          NOutliers: int
          Window: int }

    let cleanIqr (angles: float[]) (radii: float[]) (o: Options) : Result =
        let n = radii.Length
        let mask = Array.zeroCreate n
        if n < o.MinPoints then
            { Mask = mask; NOutliers = 0; Window = 0 }
        else
            let w = Signal.windowPoints angles o.BaselineDeg
            let baseLine = Signal.medianFilterWrap radii w
            let res = Array.init n (fun i -> radii.[i] - baseLine.[i])

            let center = Signal.median res
            let spread = Signal.iqr res
            // Защита референса: при вырожденном остатке порог Тьюки упирается в 1.0 мм
            // (spec/conformance/README.md, «очиститель молча отключается»).
            let denom = if spread > 1e-12 then spread else 1.0

            let sev = Array.zeroCreate n
            let mutable flagged = 0
            for i in 0 .. n - 1 do
                sev.[i] <- Math.Abs(res.[i] - center) / denom
                mask.[i] <- sev.[i] > o.IqrK
                if mask.[i] then flagged <- flagged + 1

            // Предохранитель: не выбрасываем больше maxRemovedFrac точек.
            let cap = int (Math.Floor(o.MaxRemovedFrac * float n))
            if cap > 0 && cap < n && flagged > cap then
                let kept = ResizeArray<float>(flagged)
                for i in 0 .. n - 1 do
                    if mask.[i] then kept.Add sev.[i]
                let arr = kept.ToArray()
                Array.Sort arr
                let level = arr.[arr.Length - cap]
                flagged <- 0
                for i in 0 .. n - 1 do
                    mask.[i] <- mask.[i] && sev.[i] >= level
                    if mask.[i] then flagged <- flagged + 1
            { Mask = mask; NOutliers = flagged; Window = w }

/// Детектор ям (трещин) — повторение python/pappa/analysis/zones.py и соседних портов:
///   band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
///   нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
///   зоны = участки, где индикатор > k, длиной не короче minZoneDeg.
module Detector =

    type Options =
        { WindowDeg: float
          WideDeg: float
          SmoothDeg: float
          K: float
          MinZoneDeg: float }

    let defaultOptions =
        { WindowDeg = 1.0
          WideDeg = 10.0
          SmoothDeg = 2.0
          K = 5.5
          MinZoneDeg = 2.0 }

    let bandIndicator (angles: float[]) (radii: float[]) (o: Options) : float[] =
        let n = radii.Length
        let wNarrow = Signal.windowPoints angles o.WindowDeg
        let wWide = Signal.windowPoints angles o.WideDeg
        let wSmooth = Signal.windowPoints angles o.SmoothDeg

        let narrow = Signal.medianFilterWrap radii wNarrow
        let wide = Signal.medianFilterWrap radii wWide
        let band = Array.init n (fun i -> Math.Abs(narrow.[i] - wide.[i]))

        let outp = Signal.smoothWrap band wSmooth
        let s = Signal.robustSigma outp
        if s > 1e-12 then Array.map (fun v -> v / s) outp else Array.zeroCreate n

    /// Непрерывные зоны по маске: элемент = (начало, конец) в градусах.
    let maskToZones (angles: float[]) (mask: bool[]) (o: Options) : (float * float)[] =
        let n = angles.Length
        let mutable any = false
        for i in 0 .. n - 1 do
            if mask.[i] then any <- true
        if not any then
            [||]
        else
            let diffs =
                if n > 1 then Array.init (n - 1) (fun i -> angles.[i + 1] - angles.[i])
                else [||]
            let step = if diffs.Length > 0 then Signal.median diffs else 1.0

            let zones = ResizeArray<float * float>()
            let mutable k = 0
            while k < n do
                if not mask.[k] then
                    k <- k + 1
                else
                    let mutable j = k
                    while j + 1 < n && mask.[j + 1] do
                        j <- j + 1
                    zones.Add(angles.[k] - step / 2.0, angles.[j] + step / 2.0)
                    k <- j + 1

            // Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это ОДНА зона.
            let zs =
                if zones.Count > 1 && mask.[0] && mask.[n - 1] then
                    let merged = ResizeArray<float * float>()
                    merged.Add(fst zones.[zones.Count - 1] - 360.0, snd zones.[0])
                    for i in 1 .. zones.Count - 2 do
                        merged.Add zones.[i]
                    merged
                else
                    zones
            zs
            |> Seq.filter (fun (a0, b0) -> b0 - a0 >= o.MinZoneDeg)
            |> Seq.toArray

    let zones (angles: float[]) (values: float[]) (o: Options) : (float * float)[] =
        let mask = Array.init values.Length (fun i -> values.[i] > o.K)
        maskToZones angles mask o

    /// Центры ям (°) — середины найденных зон.
    let pits (angles: float[]) (radii: float[]) (o: Options) : float[] =
        let band = bandIndicator angles radii o
        zones angles band o |> Array.map (fun (a0, b0) -> 0.5 * (a0 + b0))
