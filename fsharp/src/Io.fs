namespace Pappa

open System
open System.Collections.Generic
open System.Diagnostics
open System.Globalization
open System.IO
open System.Text

/// Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go).
module Csv =

    type Row =
        { SectionId: int
          HeightMm: float
          AngleDeg: float
          RadiusMm: float }

    /// Сечение + обученная модель + метаданные для документа.
    type SectionModel =
        { SectionId: int
          HeightMm: float
          Model: Model.Model
          NPointsTotal: int
          NOutliers: int
          FitTimeMs: float
          Description: string
          Pits: float[]
          NUsed: int }

    /// Параметры посекционного расчёта: значения по умолчанию — как в референсе.
    type PipelineOptions =
        { ModelOptions: Model.Options
          Cleaner: Cleaner.Options
          Detector: Detector.Options
          Pits: bool
          Verbose: bool }

    let defaultPipelineOptions =
        { ModelOptions = Model.defaultOptions
          Cleaner = Cleaner.defaultOptions
          Detector = Detector.defaultOptions
          Pits = true
          Verbose = true }

    /// Чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок).
    let load (path: string) : Row list =
        let lines =
            File.ReadAllLines(path, Encoding.UTF8) |> Array.filter (fun l -> l.Trim().Length > 0)
        if lines.Length = 0 then failwith ("пустой CSV: " + path)

        let head = lines.[0].Split(',')
        let index = Dictionary<string, int>()
        for i in 0 .. head.Length - 1 do
            index.[head.[i].Trim()] <- i
        for need in [ "section_id"; "height_mm"; "angle_deg"; "radius_mm" ] do
            if not (index.ContainsKey need) then
                failwith ("в CSV нет колонки \"" + need + "\"")

        let iSec = index.["section_id"]
        let ih = index.["height_mm"]
        let ia = index.["angle_deg"]
        let ir = index.["radius_mm"]
        let needCol = max (max iSec ih) (max ia ir)

        let rows = ResizeArray<Row>(lines.Length - 1)
        for k in 1 .. lines.Length - 1 do
            let f = lines.[k].Split(',')
            if f.Length > needCol then
                rows.Add(
                    { SectionId = Int32.Parse(f.[iSec].Trim(), NumberStyles.Integer, Fmt.inv)
                      HeightMm = Double.Parse(f.[ih].Trim(), NumberStyles.Float, Fmt.inv)
                      AngleDeg = Double.Parse(f.[ia].Trim(), NumberStyles.Float, Fmt.inv)
                      RadiusMm = Double.Parse(f.[ir].Trim(), NumberStyles.Float, Fmt.inv) }
                )
        if rows.Count = 0 then failwith "в CSV нет строк с данными"
        List.ofSeq rows

    /// Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение.
    let processSections (rows: Row list) (opt: PipelineOptions) : SectionModel list =
        let bySection = Dictionary<int, ResizeArray<Row>>()
        for r in rows do
            let list =
                match bySection.TryGetValue r.SectionId with
                | true, l -> l
                | _ ->
                    let l = ResizeArray<Row>()
                    bySection.[r.SectionId] <- l
                    l
            list.Add r

        let ids = List<int>(bySection.Keys)
        ids.Sort()

        let outp = ResizeArray<SectionModel>(ids.Count)
        for sid in ids do
            // Сортировка по углу обязана быть УСТОЙЧИВОЙ: при равных углах сохраняется
            // порядок файла, а от него зависит height_mm «первой» строки. В F#
            // List.sortBy/Seq.sortBy — устойчивая сортировка (это важно: Array.Sort
            // в .NET неустойчив, поэтому в C#-порте пришлось брать OrderBy).
            let group = bySection.[sid] |> Seq.sortBy (fun r -> r.AngleDeg) |> List.ofSeq
            let n = group.Length
            let angles = group |> List.map (fun r -> r.AngleDeg) |> List.toArray
            let radii = group |> List.map (fun r -> r.RadiusMm) |> List.toArray

            let cl = Cleaner.cleanIqr angles radii opt.Cleaner
            let aClean = ResizeArray<float>(n)
            let rClean = ResizeArray<float>(n)
            for i in 0 .. n - 1 do
                if not cl.Mask.[i] then
                    aClean.Add angles.[i]
                    rClean.Add radii.[i]
            let ang = aClean.ToArray()
            let rad = rClean.ToArray()

            let pits = if opt.Pits then Detector.pits ang rad opt.Detector else [||]
            let model = Model.Model(opt.ModelOptions, pits)

            let sw = Stopwatch.StartNew()
            model.Fit(ang, rad)
            sw.Stop()
            let fitMs = sw.Elapsed.TotalMilliseconds

            let height = if group.Length > 0 then group.Head.HeightMm else 0.0
            let sec =
                { SectionId = sid
                  HeightMm = height
                  Model = model
                  NPointsTotal = n
                  NOutliers = cl.NOutliers
                  FitTimeMs = fitMs
                  Description = "сечение " + string sid + ", h=" + Fmt.f0 height + " мм"
                  Pits = pits
                  NUsed = ang.Length }
            if opt.Verbose then
                printfn
                    "  секция %d (h=%s мм): точек %d, выброшено %d, ям найдено %d, степени [%s], обучение %s мс"
                    sid
                    (Fmt.f0 height)
                    n
                    cl.NOutliers
                    pits.Length
                    (model.Degrees |> Array.map string |> String.concat ", ")
                    (fitMs.ToString("0.0", Fmt.inv))
            outp.Add sec
        List.ofSeq outp

/// Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin:
///   <out_dir>/sample.json              манифест (format pappa-sample v1.0)
///   <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
/// Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
/// сравниваются численно (python/studies/verify_port.py).
module Document =

    let portVersion = "0.1.0"

    type SampleOptions =
        { Name: string
          InputCsv: string
          Pits: bool
          Description: string
          Cleaner: Cleaner.Options
          Detector: Detector.Options }

    let defaultSampleOptions =
        { Name = "sample"
          InputCsv = ""
          Pits = true
          Description = "PAPPA F# port"
          Cleaner = Cleaner.defaultOptions
          Detector = Detector.defaultOptions }

    let isoUtcNow () = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", Fmt.inv)

    /// Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++.
    /// Ловушка F#: члены класса ссылаются друг на друга только через явный
    /// self-идентификатор (member this.X), поэтому методы оформлены как this.*.
    type private W() =
        let sb = StringBuilder()
        let mutable depth = 0

        member _.Sb = sb

        /// Отступ текущего уровня.
        member _.Indent() = String(' ', 2 * max 0 depth)

        member this.ObjStart() =
            sb.Append('{') |> ignore
            depth <- depth + 1
            sb.Append('\n').Append(this.Indent()) |> ignore

        member this.ObjEnd() =
            depth <- depth - 1
            sb.Append('\n').Append(this.Indent()).Append('}') |> ignore

        member this.ArrStart() =
            sb.Append('[') |> ignore
            depth <- depth + 1
            sb.Append('\n').Append(this.Indent()) |> ignore

        member this.ArrEnd() =
            depth <- depth - 1
            sb.Append('\n').Append(this.Indent()).Append(']') |> ignore

        member this.Comma() = sb.Append(',').Append('\n').Append(this.Indent()) |> ignore

        member this.Key(k: string) =
            sb.Append(this.Indent()).Append('"').Append(k).Append("\": ") |> ignore

        member _.Str(v: string) = sb.Append('"').Append(Json.escape v).Append('"') |> ignore

        member _.Num(v: float) = sb.Append(Json.num v) |> ignore

        member _.Raw(v: string) = sb.Append(v) |> ignore

        member this.Kv(k: string, v: string) =
            this.Key k
            this.Str v

        member this.Kv(k: string, v: float) =
            this.Key k
            this.Num v

        member this.Kv(k: string, v: int) =
            this.Key k
            sb.Append(v.ToString(Fmt.inv)) |> ignore

        // ВАЖНО: string true в F# печатает "True"/"False" — в JSON нужен нижний регистр.
        member this.Kv(k: string, v: bool) =
            this.Key k
            sb.Append(Fmt.boolStr v) |> ignore

    /// Патчи модели: центр, степень, точки, коэффициенты, метрики, статистика.
    let private writePatches (w: W) (m: Model.Model) =
        w.Key "patches"
        w.ArrStart()
        let patches = m.Patches
        for i in 0 .. patches.Count - 1 do
            let p = patches.[i]
            w.Sb.Append(if i > 0 then ",\n" + w.Indent() else "\n" + w.Indent()) |> ignore
            w.ObjStart()
            w.Kv("center_deg", p.CenterDeg)
            w.Comma()
            w.Kv("degree", p.Degree)
            w.Comma()
            w.Kv("n_points", p.NPoints)
            w.Comma()
            w.Key "coefs"
            w.ArrStart()
            for j in 0 .. p.Coefs.Length - 1 do
                if j > 0 then w.Raw ", "
                w.Num p.Coefs.[j]
            w.ArrEnd()
            w.Comma()

            w.Key "metrics"
            w.ObjStart()
            w.Kv("amplitude_mm", p.Metrics.AmplitudeMm)
            w.Comma()
            w.Kv("mean_radius_mm", p.Metrics.MeanRadiusMm)
            w.Comma()
            w.Kv("amplitude_norm", p.Metrics.AmplitudeNorm)
            w.Comma()
            w.Kv("deg_elbow_tol", p.Metrics.DegElbowTol)
            w.Comma()
            w.Kv("rmse_selected_mm", p.Metrics.RmseSelectedMm)
            w.Comma()
            w.Kv("rmse_best_mm", p.Metrics.RmseBestMm)
            w.Comma()
            w.Kv("n_train_points", p.Metrics.NTrainPoints)
            w.ObjEnd()
            w.Comma()

            w.Key "stats"
            w.ObjStart()
            w.Kv("rmse_mm", p.Stats.RmseMm)
            w.Comma()
            w.Kv("mae_mm", p.Stats.MaeMm)
            w.Comma()
            w.Kv("max_err_mm", p.Stats.MaxErrMm)
            w.Comma()
            w.Kv("correlation", p.Stats.Correlation)
            w.ObjEnd()

            // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
            // (включая пустой список): этого ждёт загрузчик Python-референса.
            if m.HasPits then
                w.Comma()
                w.Key "pit_terms"
                w.ArrStart()
                for j in 0 .. p.PitOffsetsDeg.Length - 1 do
                    if j > 0 then w.Raw ", "
                    w.ObjStart()
                    w.Kv("dx_deg", p.PitOffsetsDeg.[j])
                    w.Comma()
                    w.Kv("amp", p.PitCoefs.[j])
                    w.ObjEnd()
                w.ArrEnd()
            w.ObjEnd()
        w.Raw "\n"
        w.Raw(w.Indent())
        w.ArrEnd()

    /// Документ сечения: pappa v2.0 (ключи и порядок — как в cpp/sample_writer.cpp).
    let saveSectionDocument (path: string) (section: Csv.SectionModel) : string =
        let m = section.Model
        if not m.IsFitted then failwith "SaveSectionDocument: модель не обучена"
        let w = W()
        w.ObjStart()
        w.Kv("format", "pappa")
        w.Comma()
        w.Kv("version", "2.0")
        w.Comma()
        w.Kv("method", if m.HasPits then "PitPatchApproximator" else "PatchApproximator")
        w.Comma()
        w.Kv("created", isoUtcNow ())
        w.Comma()

        w.Key "software"
        w.ObjStart()
        w.Kv("language", "fsharp")
        w.Comma()
        w.Kv("pappa_version", portVersion)
        w.ObjEnd()
        w.Comma()

        w.Key "meta"
        w.ObjStart()
        w.Kv("section_id", section.SectionId)
        w.Comma()
        w.Kv("height_mm", section.HeightMm)
        w.Comma()
        w.Kv("source", "csv")
        w.Comma()
        w.Kv("description", section.Description)
        w.ObjEnd()
        w.Comma()

        w.Key "global"
        w.ObjStart()
        w.Key "units"
        w.ObjStart()
        w.Kv("angle", "degree")
        w.Comma()
        w.Kv("length", "mm")
        w.ObjEnd()
        w.Comma()
        let opt = m.OptionsRef
        w.Kv("n_patches", opt.NPatches)
        w.Comma()
        w.Kv("half_sector_deg", m.HalfSector)
        w.Comma()
        w.Kv("phase_deg", opt.PhaseDeg)
        w.Comma()
        w.Kv("half_train_deg", m.HalfTrain)
        w.Comma()
        w.Kv("half_use_deg", m.HalfUse)
        w.Comma()
        w.Kv("overlap_train_deg", opt.OverlapTrain)
        w.Comma()
        w.Kv("overlap_use_deg", opt.OverlapUse)
        w.Comma()
        w.Kv("deg_min", opt.DegMin)
        w.Comma()
        w.Kv("deg_max", opt.DegMax)
        w.Comma()
        w.Kv("coord_mode", opt.CoordMode)
        w.Comma()
        w.Kv("deg_elbow_tol", opt.DegElbowTol)
        w.Comma()
        w.Kv("amplitude_scale", opt.AmplitudeScale)
        if m.HasPits then
            let ps = m.PitShape
            w.Comma()
            w.Key "pit"
            w.ObjStart()
            w.Kv("sigma_deg", ps.SigmaDeg)
            w.Comma()
            w.Kv("core_sigma", ps.CoreSigma)
            w.Comma()
            w.Kv("window_sigma", ps.WindowSigma)
            w.Comma()
            w.Kv("pit_min_amp", ps.PitMinAmp)
            w.Comma()
            w.Kv("tapering", ps.Tapering)
            w.Comma()
            w.Key "centers_deg"
            w.ArrStart()
            for i in 0 .. m.Pits.Length - 1 do
                if i > 0 then w.Raw ", "
                w.Num m.Pits.[i]
            w.ArrEnd()
            w.ObjEnd()
        w.ObjEnd()
        w.Comma()

        writePatches w m
        w.Comma()

        w.Key "statistics"
        w.ObjStart()
        w.Kv("n_points_total", section.NPointsTotal)
        w.Comma()
        w.Kv("n_outliers_removed", section.NOutliers)
        w.Comma()
        w.Kv("fit_time_ms", section.FitTimeMs)
        w.ObjEnd()

        w.ObjEnd()
        File.WriteAllText(path, w.Sb.ToString() + "\n", UTF8Encoding(false))
        path

    /// Папка образца целиком: манифест pappa-sample v1.0 + документы сечений.
    /// Возвращает полный путь к корню образца.
    let saveSample (outDir: string) (name: string) (sections: Csv.SectionModel list)
                   (so: SampleOptions) : string =
        let root = Path.GetFullPath(outDir)
        Directory.CreateDirectory(Path.Combine(root, "sections")) |> ignore

        let ordered = sections |> List.sortBy (fun s -> s.SectionId) |> List.toArray
        let first = if ordered.Length > 0 then Some ordered.[0].Model else None
        let oopt = first |> Option.map (fun (m: Model.Model) -> m.OptionsRef)
        let pick (f: Model.Options -> 'a) (def: 'a) = defaultArg (Option.map f oopt) def

        let w = W()
        w.ObjStart()
        w.Kv("format", "pappa-sample")
        w.Comma()
        w.Kv("version", "1.0")
        w.Comma()
        w.Kv("name", name)
        w.Comma()
        w.Kv("created", isoUtcNow ())
        w.Comma()

        w.Key "units"
        w.ObjStart()
        w.Kv("angle", "degree")
        w.Comma()
        w.Kv("length", "mm")
        w.ObjEnd()
        w.Comma()

        w.Key "meta"
        w.ObjStart()
        w.Kv("description", so.Description)
        w.ObjEnd()
        w.Comma()

        if not (String.IsNullOrEmpty so.InputCsv) then
            w.Key "input"
            w.ObjStart()
            w.Kv("csv", so.InputCsv)
            w.ObjEnd()
            w.Comma()

        w.Key "config"
        w.ObjStart()
        w.Kv("n_patches", pick (fun o -> o.NPatches) 0)
        w.Comma()
        w.Kv("phase_deg", pick (fun o -> o.PhaseDeg) 0.0)
        w.Comma()
        w.Kv("deg_min", pick (fun o -> o.DegMin) 0)
        w.Comma()
        w.Kv("deg_max", pick (fun o -> o.DegMax) 0)
        w.Comma()
        w.Kv("overlap_train", pick (fun o -> o.OverlapTrain) 0.0)
        w.Comma()
        w.Kv("overlap_use", pick (fun o -> o.OverlapUse) 0.0)
        w.Comma()
        w.Kv("deg_elbow_tol", pick (fun o -> o.DegElbowTol) 0.0)
        w.Comma()
        w.Key "cleaner"
        w.Raw(
            "{\"mode\": \"auto\", \"auto\": {\"method\": \"iqr\", \"baseline_deg\": "
            + Json.num so.Cleaner.BaselineDeg
            + ", \"iqr_k\": "
            + Json.num so.Cleaner.IqrK
            + "}}"
        )
        w.Comma()
        w.Kv("pits", so.Pits)
        if so.Pits && first.IsSome then
            let ps = first.Value.PitShape
            w.Comma()
            w.Kv("sigma_deg", ps.SigmaDeg)
            w.Comma()
            w.Kv("pit_core_sigma", ps.CoreSigma)
            w.Comma()
            w.Kv("pit_window_sigma", ps.WindowSigma)
            w.Comma()
            w.Kv("pit_min_amp", ps.PitMinAmp)
            w.Comma()
            w.Kv("tapering", ps.Tapering)
        w.Comma()
        w.Key "detector"
        w.Raw "null"
        w.ObjEnd()
        w.Comma()

        w.Key "sections"
        w.ArrStart()
        for i in 0 .. ordered.Length - 1 do
            let s = ordered.[i]
            let file = "sections/" + i.ToString("D2", Fmt.inv) + ".pappa.json"
            saveSectionDocument (Path.Combine(root, file)) s |> ignore
            w.Raw(if i > 0 then ",\n" + w.Indent() else "\n" + w.Indent())
            w.ObjStart()
            w.Kv("index", i)
            w.Comma()
            w.Kv("section_id", s.SectionId)
            w.Comma()
            w.Kv("height_mm", s.HeightMm)
            w.Comma()
            w.Kv("file", file)
            w.Comma()
            w.Kv("n_points", s.NPointsTotal)
            w.Comma()
            w.Kv("n_outliers", s.NOutliers)
            w.ObjEnd()
        w.Raw "\n"
        w.Raw(w.Indent())
        w.ArrEnd()

        w.ObjEnd()
        File.WriteAllText(Path.Combine(root, "sample.json"), w.Sb.ToString() + "\n", UTF8Encoding(false))
        root



