namespace Pappa

open System
open System.Collections.Generic

/// Модель PAPPA (F#): патчи с адаптивной степенью по нормированной координате,
/// smoothstep-смешивание (partition of unity) и оконный гауссов фичер ям.
/// Совпадает с референсом Python и портами C/C++/Go/JS/Java/Kotlin/Pascal/Swift/
/// Julia/R/C#/VBA: тот же базис, та же политика степени («локоть»), тот же МНК
/// (QR Хаусхолдера). Свип степеней — ОДНИМ накоплением Грама в базисе Чебышёва
/// + RMSE по явным остаткам (схема Кленшоу).
///
/// Ловушка F#: класс с изменяемым состоянием пишется через `let mutable` и
/// `member`, а не через автосвойства; вложенные типы и функции ОБЯЗАНЫ быть
/// объявлены до класса (в F# нет forward-объявлений внутри файла).
module Model =

    /// Параметры модели: значения по умолчанию — как в референсе.
    type Options =
        { NPatches: int
          PhaseDeg: float
          DegMin: int
          DegMax: int
          OverlapTrain: float
          OverlapUse: float
          DegElbowTol: float
          AmplitudeScale: float
          CoordMode: string }

    let defaultOptions =
        { NPatches = 7
          PhaseDeg = 24.75
          DegMin = 4
          DegMax = 14
          OverlapTrain = 15.0
          OverlapUse = 5.0
          DegElbowTol = 0.05
          AmplitudeScale = 180.0
          CoordMode = "normalized" }

    /// Форма ямы: гаусс с обрезкой-сглаживанием (tapering) за core_sigma.
    type PitShapeOptions =
        { SigmaDeg: float
          CoreSigma: float
          WindowSigma: float
          PitMinAmp: float
          Tapering: bool }

    let defaultPitShape =
        { SigmaDeg = 3.0
          CoreSigma = 2.0
          WindowSigma = 3.2
          PitMinAmp = 3e-3
          Tapering = true }

    /// Метрики патча (по его обучающему окну).
    type Metrics =
        { AmplitudeMm: float
          MeanRadiusMm: float
          AmplitudeNorm: float
          DegElbowTol: float
          RmseSelectedMm: float
          RmseBestMm: float
          NTrainPoints: int }

    /// Статистика приближения патча.
    type Stats =
        { RmseMm: float
          MaeMm: float
          MaxErrMm: float
          Correlation: float }

    /// Один патч: полином по нормированной координате + термины ям.
    type Patch =
        { CenterDeg: float
          Degree: int
          NPoints: int
          Coefs: float[]
          PitOffsetsDeg: float[]
          PitCoefs: float[]
          Metrics: Metrics
          Stats: Stats }

    /// Результат выбора степени («локоть»).
    type private DegreeChoice =
        { Deg: int
          RmseSelected: float
          RmseBest: float
          NTrain: int }

    /// Модель: обучается на одном сечении (angles, radii) — точки в градусах и мм.
    type Model(optIn: Options, pitsDeg: float[]) =

        let opt = optIn
        let mutable pitCenters: float[] = [||]
        let patchList = List<Patch>()
        let mutable centersArr: float[] = [||]
        let mutable halfSectorDeg = 0.0
        let mutable isFitted = false
        let mutable pitShape = defaultPitShape

        /// Приведение центра ямы в [0, 360).
        let normed (c: float) = ((c % 360.0) + 360.0) % 360.0

        do pitCenters <- Array.map normed pitsDeg

        member _.OptionsRef = opt

        member _.PitShape
            with get () = pitShape
            and set (v) = pitShape <- v

        member _.Pits = pitCenters

        member _.Patches = patchList

        member _.HasPits = pitCenters.Length > 0

        member _.IsFitted = isFitted

        member _.HalfSector = halfSectorDeg

        member _.HalfTrain = halfSectorDeg + opt.OverlapTrain

        member _.HalfUse = halfSectorDeg + opt.OverlapUse

        member _.SetPits(centersDeg: float[]) = pitCenters <- Array.map normed centersDeg

        /// Оконный гаусс как функция расстояния от центра ямы (pit_shape_deg).
        member _.PitShapeDeg(dDeg: float) =
            let d = Math.Abs dDeg
            let sigma = pitShape.SigmaDeg
            let val0 = Math.Exp(-(d * d) / (2.0 * sigma * sigma))
            if not pitShape.Tapering then
                val0
            else
                let core = pitShape.CoreSigma * sigma
                let edge = pitShape.WindowSigma * sigma
                if edge <= core then
                    val0
                else
                    let t = Math.Min(1.0, Math.Max(0.0, (edge - d) / (edge - core)))
                    val0 * t * t * (3.0 - 2.0 * t)

        /// Смещения видимых ям в локальной системе патча (°), в порядке объявления.
        member _.PitOffsets(centerDeg: float, halfWinDeg: float) : float[] =
            pitCenters
            |> Array.map (fun c -> Signal.circLocal c centerDeg)
            |> Array.filter (fun dx -> Math.Abs dx <= halfWinDeg)

        /// Вес патча: 1 внутри сектора, smoothstep к нулю на перекрытии.
        member _.Weight(dDeg: float, halfUseDeg: float) =
            if dDeg <= halfSectorDeg then 1.0
            elif dDeg <= halfUseDeg then
                Signal.smoothstep (1.0 - (dDeg - halfSectorDeg) / (halfUseDeg - halfSectorDeg))
            else
                0.0

        /// Степени патчей по порядку центров.
        member _.Degrees : int[] =
            patchList |> Seq.map (fun p -> p.Degree) |> Seq.toArray

        /// Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
        /// не хуже лучшей более чем на degElbowTol. Быстрая ветка (normalized) — одно
        /// накопление Грама в базисе Чебышёва + явные остатки (схема Кленшоу).
        member private this.EstimateDegree(xs: float[], ys: float[]) : DegreeChoice =
            let n = xs.Length
            if n < 5 then
                { Deg = opt.DegMin; RmseSelected = 0.0; RmseBest = 0.0; NTrain = n }
            else
                let degs = ResizeArray<int>()
                let rmses = ResizeArray<float>()
                let mutable bestDeg = opt.DegMin
                let mutable best = Double.PositiveInfinity

                if opt.CoordMode = "raw" then
                    // Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1],
                    // поэтому здесь честный полиномиальный МНК на каждом шаге.
                    let mutable deg = opt.DegMin
                    while deg <= opt.DegMax do
                        let a =
                            Array.init n (fun i ->
                                let row = Array.zeroCreate (deg + 1)
                                let mutable p = 1.0
                                for j in 0 .. deg do
                                    row.[deg - j] <- p
                                    p <- p * xs.[i]
                                row)
                        let c = Linalg.lstsqQR a ys
                        let mutable sse = 0.0
                        for i in 0 .. n - 1 do
                            let e = Linalg.polyval c xs.[i] - ys.[i]
                            sse <- sse + e * e
                        let r = Math.Sqrt(sse / float n)
                        degs.Add deg
                        rmses.Add r
                        if r < best then
                            best <- r
                            bestDeg <- deg
                        deg <- deg + 2
                else
                    let dmax = opt.DegMax
                    let p = dmax + 1
                    let mutable yref = 0.0
                    for v in ys do
                        yref <- yref + v
                    yref <- yref / float n

                    let gram = Array.init p (fun _ -> Array.zeroCreate p)
                    let rhs = Array.zeroCreate p
                    for i in 0 .. n - 1 do
                        let t = Linalg.chebRow xs.[i] dmax
                        let yc = ys.[i] - yref
                        for a0 in 0 .. p - 1 do
                            rhs.[a0] <- rhs.[a0] + t.[a0] * yc
                            for c0 in a0 .. p - 1 do
                                gram.[a0].[c0] <- gram.[a0].[c0] + t.[a0] * t.[c0]
                    for a0 in 0 .. p - 1 do
                        for c0 in a0 + 1 .. p - 1 do
                            gram.[c0].[a0] <- gram.[a0].[c0]

                    let mutable deg = opt.DegMin
                    while deg <= dmax do
                        let nn = deg + 1
                        let a = Array.init nn (fun r0 -> Array.sub gram.[r0] 0 nn)
                        let b = Array.sub rhs 0 nn
                        let c = Linalg.lstsqQR a b
                        let mutable sse = 0.0
                        for i in 0 .. n - 1 do
                            let e = Linalg.chebSum c deg xs.[i] - (ys.[i] - yref)
                            sse <- sse + e * e
                        let r = Math.Sqrt(sse / float n)
                        degs.Add deg
                        rmses.Add r
                        if r < best then
                            best <- r
                            bestDeg <- deg
                        deg <- deg + 2

                let limit = best * (1.0 + opt.DegElbowTol)
                let mutable sel = bestDeg
                let mutable rmseSel = best
                let mutable found = false
                for k in 0 .. degs.Count - 1 do // степени по возрастанию
                    if not found && rmses.[k] <= limit then
                        sel <- degs.[k]
                        rmseSel <- rmses.[k]
                        found <- true
                { Deg = sel; RmseSelected = rmseSel; RmseBest = best; NTrain = n }

        /// Точки обучающего окна патча (локальная координата: нормированная или сырая).
        member private this.WindowOf(angles: float[], radii: float[], center: float) : float[] * float[] =
            let half = this.HalfTrain
            let norm = opt.CoordMode <> "raw"
            let xl = ResizeArray<float>()
            let yl = ResizeArray<float>()
            for shift in [ -360.0; 0.0; 360.0 ] do
                for i in 0 .. angles.Length - 1 do
                    let dx = angles.[i] + shift - center
                    if dx >= -half && dx <= half then
                        xl.Add(if norm then dx / half else dx)
                        yl.Add radii.[i]
            xl.ToArray(), yl.ToArray()

        /// Обучение модели на одном сечении: центры патчей, окна, степени, МНК.
        /// Возвращает unit: в F# цепочка вызовов вида m.Fit(..).Eval(..) из порта
        /// не нужна, а «вернуть this» из класса без явного параметра нельзя.
        member this.Fit(angles: float[], radii: float[]) =
            if angles.Length <> radii.Length then failwith "fit: длины не совпадают"
            if angles.Length < 10 then failwith "fit: слишком мало точек"

            let sector = 360.0 / float opt.NPatches
            halfSectorDeg <- sector / 2.0
            centersArr <-
                Array.init opt.NPatches (fun i ->
                    let c = (float i * sector + halfSectorDeg + opt.PhaseDeg) % 360.0
                    if c < 0.0 then c + 360.0 else c)
            let halfTrain = this.HalfTrain
            patchList.Clear()

            for c in centersArr do
                let xs, ys = this.WindowOf(angles, radii, c)
                let n = xs.Length
                if n >= 5 then
                    let est = this.EstimateDegree(xs, ys)
                    let deg = est.Deg

                    let offs = this.PitOffsets(c, halfTrain)
                    let ncol = deg + 1 + offs.Length
                    let a =
                        Array.init n (fun i ->
                            let row = Array.zeroCreate ncol
                            let mutable p = 1.0
                            for k in deg .. -1 .. 0 do
                                row.[k] <- p
                                p <- p * xs.[i]
                            for j in 0 .. offs.Length - 1 do
                                row.[deg + 1 + j] <- this.PitShapeDeg(Math.Abs(xs.[i] * halfTrain - offs.[j]))
                            row)
                    let coef = Linalg.lstsqQR a ys
                    let polyCoef = Array.sub coef 0 (deg + 1)

                    // Отсечка ям, которые в окне патча «не видны» (pitMinAmp).
                    let keptOffsets = ResizeArray<float>()
                    let keptCoefs = ResizeArray<float>()
                    for j in 0 .. offs.Length - 1 do
                        let mutable maxAbs = 0.0
                        for i in 0 .. n - 1 do
                            let dDeg = Math.Abs(xs.[i] * halfTrain - offs.[j])
                            maxAbs <- Math.Max(maxAbs, Math.Abs(coef.[deg + 1 + j] * this.PitShapeDeg(dDeg)))
                        if maxAbs >= pitShape.PitMinAmp then
                            keptOffsets.Add offs.[j]
                            keptCoefs.Add coef.[deg + 1 + j]

                    patchList.Add(
                        this.BuildPatch(
                            c, deg, xs, ys, polyCoef,
                            keptOffsets.ToArray(), keptCoefs.ToArray(), est, angles, radii
                        )
                    )
            isFitted <- true

        /// Метрики и статистика патча по его обучающему окну (полный базис).
        member private this.BuildPatch(c: float, deg: int, xs: float[], ys: float[], polyCoef: float[],
                                       keptOffsets: float[], keptCoefs: float[], est: DegreeChoice,
                                       angles: float[], radii: float[]) : Patch =
            let n = xs.Length
            let mutable sse = 0.0
            let mutable sae = 0.0
            let mutable mx = 0.0
            let fitVals = Array.zeroCreate n
            for i in 0 .. n - 1 do
                let mutable v = Linalg.polyval polyCoef xs.[i]
                for j in 0 .. keptOffsets.Length - 1 do
                    v <- v + keptCoefs.[j] * this.PitShapeDeg(Math.Abs(xs.[i] * this.HalfTrain - keptOffsets.[j]))
                fitVals.[i] <- v
                let e = v - ys.[i]
                sse <- sse + e * e
                sae <- sae + Math.Abs e
                mx <- Math.Max(mx, Math.Abs e)

            let mutable mf = 0.0
            let mutable my = 0.0
            for i in 0 .. n - 1 do
                mf <- mf + fitVals.[i]
                my <- my + ys.[i]
            mf <- mf / float n
            my <- my / float n
            let mutable cov = 0.0
            let mutable vf = 0.0
            let mutable vy = 0.0
            for i in 0 .. n - 1 do
                let df = fitVals.[i] - mf
                let dy = ys.[i] - my
                cov <- cov + df * dy
                vf <- vf + df * df
                vy <- vy + dy * dy
            let corr = if vf > 0.0 && vy > 0.0 then cov / Math.Sqrt(vf * vy) else 0.0

            // Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
            let sec = ResizeArray<float>()
            for i in 0 .. angles.Length - 1 do
                if Signal.circDist angles.[i] c <= this.HalfSector then
                    sec.Add radii.[i]
            let mutable amp = 0.0
            let mutable meanSec = 0.0
            if sec.Count >= 5 then
                let arr = sec.ToArray()
                amp <- Signal.percentileLinear arr 95.0 - Signal.percentileLinear arr 5.0
                for v in arr do
                    meanSec <- meanSec + v
                meanSec <- meanSec / float arr.Length

            { CenterDeg = c
              Degree = deg
              NPoints = n
              Coefs = polyCoef
              PitOffsetsDeg = keptOffsets
              PitCoefs = keptCoefs
              Metrics =
                { AmplitudeMm = amp
                  MeanRadiusMm = meanSec
                  AmplitudeNorm = if meanSec > 0.0 then amp / meanSec else 0.0
                  DegElbowTol = opt.DegElbowTol
                  RmseSelectedMm = est.RmseSelected
                  RmseBestMm = est.RmseBest
                  NTrainPoints = n }
              Stats =
                { RmseMm = Math.Sqrt(sse / float n)
                  MaeMm = sae / float n
                  MaxErrMm = mx
                  Correlation = corr } }

        /// Контур: нормированное smoothstep-смешивание патчей (partition of unity).
        /// part = "total" (полином + ямы), "poly" (только полином), "pit" (только ямы).
        member this.EvalPart(angles: float[], part: string) : float[] =
            if not isFitted then failwith "Сначала вызовите Fit()"
            let halfUse = this.HalfUse
            let halfTrain = this.HalfTrain
            Array.init angles.Length (fun k ->
                let a = angles.[k]
                let mutable sumWv = 0.0
                let mutable sumW = 0.0
                for p in patchList do
                    let w = this.Weight(Signal.circDist a p.CenterDeg, halfUse)
                    if w > 0.0 then
                        let dx = Signal.circLocal a p.CenterDeg
                        let x = if opt.CoordMode = "raw" then dx else dx / halfTrain
                        let mutable v = 0.0
                        if part <> "pit" then
                            v <- v + Linalg.polyval p.Coefs x
                        if part <> "poly" then
                            for j in 0 .. p.PitOffsetsDeg.Length - 1 do
                                v <-
                                    v
                                    + p.PitCoefs.[j]
                                      * this.PitShapeDeg(Math.Abs(x * halfTrain - p.PitOffsetsDeg.[j]))
                        sumWv <- sumWv + w * v
                        sumW <- sumW + w
                if sumW > 0.0 then sumWv / sumW else 0.0)

        member this.Eval(angles: float[]) : float[] = this.EvalPart(angles, "total")



