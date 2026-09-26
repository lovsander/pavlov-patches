namespace Pappa

open System
open System.Collections.Generic
open System.Globalization
open System.IO
open System.Text

/// Проверка порта по конформанс-векторам (spec/conformance/vectors).
/// Допуски — те же, что у C++/C/Go/JS/Java/Kotlin/C#/VBA: контур 1e-6 мм,
/// коэффициенты max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac).
module Conformance =

    type Vector =
        { File: string
          Data: Dictionary<string, Json.JVal> }

    type Result =
        { Ok: bool
          Detail: string
          Notes: string list }

    let load (dir: string) : Vector list =
        let files = Directory.GetFiles(dir, "*.json", SearchOption.TopDirectoryOnly)
        Array.sortInPlaceWith (fun a b -> String.CompareOrdinal(a, b)) files
        files
        |> Array.map (fun f ->
            { File = Path.GetFileName(f)
              Data = Json.parseObject (File.ReadAllText(f, Encoding.UTF8)) }
        )
        |> List.ofArray

    /// |a − b| <= max(floor, rel·|b|) — допуск как у остальных портов.
    let private near (a: float) (b: float) (rel: float) (floor: float) =
        Math.Abs(a - b) <= Math.Max(floor, rel * Math.Abs b)

    let private nums (v: Json.JVal) : float[] =
        Json.arrOf v
        |> List.map (fun x ->
            match x with
            | Json.JOfNum d -> d
            | _ -> nan)
        |> List.toArray

    let private checkDetector (v: Dictionary<string, Json.JVal>) : Result =
        let cfg = Json.objOf (Json.get v "config")
        let exp = Json.objOf (Json.get v "expected")
        let input = Json.objOf (Json.get v "input")
        let angles = Json.doubles input "angles_deg"
        let radii = Json.doubles input "radii_mm"

        let o =
            { Detector.WindowDeg = Json.dbl cfg "window_deg" 0.0
              Detector.WideDeg = Json.dbl cfg "wide_deg" 0.0
              Detector.SmoothDeg = Json.dbl cfg "smooth_deg" 0.0
              Detector.K = Json.dbl cfg "k" 0.0
              Detector.MinZoneDeg = Json.dbl cfg "min_zone_deg" 0.0 }

        let band = Detector.bandIndicator angles radii o
        let zn = Detector.zones angles band o
        let expZones = Json.arrOf (Json.get exp "zones_deg") |> List.map nums |> List.toArray
        let expPits = Json.doubles exp "pits_deg"
        let notes = ResizeArray<string>()

        let mutable ok = zn.Length = expZones.Length
        if not ok then
            notes.Add("зон " + string zn.Length + " != " + string expZones.Length)

        let mutable dev = 0.0
        for i in 0 .. min expZones.Length zn.Length - 1 do
            let e = expZones.[i]
            dev <- Math.Max(dev, Math.Max(Math.Abs(fst zn.[i] - e.[0]), Math.Abs(snd zn.[i] - e.[1])))

        if zn.Length <> expPits.Length then
            ok <- false
            notes.Add("ям " + string zn.Length + " != " + string expPits.Length)

        for i in 0 .. min expPits.Length zn.Length - 1 do
            let d = Math.Abs(0.5 * (fst zn.[i] + snd zn.[i]) - expPits.[i])
            dev <- Math.Max(dev, d)
            if d > 1e-6 then ok <- false

        { Ok = ok
          Detail =
            "зон "
            + string zn.Length
            + "/"
            + string expZones.Length
            + ", ям "
            + string zn.Length
            + "/"
            + string expPits.Length
            + ", max|Δ| "
            + Fmt.e2 dev
            + "°"
          Notes = List.ofSeq notes }

    let private checkCleaner (v: Dictionary<string, Json.JVal>) : Result =
        let cfg = Json.objOf (Json.get v "config")
        let exp = Json.objOf (Json.get v "expected")
        let input = Json.objOf (Json.get v "input")
        let tol = Json.objOf (Json.get v "tolerance")
        let angles = Json.doubles input "angles_deg"
        let radii = Json.doubles input "radii_mm"

        let o =
            { Cleaner.BaselineDeg = Json.dbl cfg "baseline_deg" 0.0
              Cleaner.IqrK = Json.dbl cfg "iqr_k" 0.0
              Cleaner.MaxRemovedFrac = 0.5
              Cleaner.MinPoints = 20 }

        let r = Cleaner.cleanIqr angles radii o

        let refMask = Array.zeroCreate radii.Length
        for i in Json.ints exp "mask_true_indices" do
            refMask.[i] <- true

        let n = radii.Length
        let mutable extra = 0
        let mutable missing = 0
        let mutable got = 0
        for i in 0 .. n - 1 do
            if r.Mask.[i] then
                got <- got + 1
                if not refMask.[i] then extra <- extra + 1
            elif refMask.[i] then
                missing <- missing + 1

        let tolN = Math.Max(1, int (Math.Floor(Json.dbl tol "frac" 0.02 * float n)))
        let want = Json.intOf exp "n_outliers" 0
        let ok = extra <= tolN && missing <= tolN && Math.Abs(got - want) <= tolN
        { Ok = ok
          Detail =
            "выбросов "
            + string got
            + " (эталон "
            + string want
            + "), лишних "
            + string extra
            + ", пропущено "
            + string missing
          Notes = [] }

    let private checkModel (v: Dictionary<string, Json.JVal>) : Result =
        let cfg = Json.objOf (Json.get v "config")
        let exp = Json.objOf (Json.get v "expected")
        let tol = Json.objOf (Json.get v "tolerance")
        let input = Json.objOf (Json.get v "input")
        let notes = ResizeArray<string>()
        let mutable ok = true

        let opt =
            { Model.NPatches = Json.intOf cfg "n_patches" 7
              Model.PhaseDeg = Json.dbl cfg "phase_deg" 24.75
              Model.DegMin = Json.intOf cfg "deg_min" 4
              Model.DegMax = Json.intOf cfg "deg_max" 14
              Model.OverlapTrain = Json.dbl cfg "overlap_train" 15.0
              Model.OverlapUse = Json.dbl cfg "overlap_use" 5.0
              Model.DegElbowTol = Json.dbl cfg "deg_elbow_tol" 0.05
              Model.AmplitudeScale = Json.dbl cfg "amplitude_scale" 180.0
              Model.CoordMode = Json.strOf cfg "coord_mode" "normalized" }

        let pitsDeg = Json.doubles cfg "pits_deg"
        let m = Model.Model(opt, pitsDeg)
        if pitsDeg.Length > 0 then
            m.PitShape <-
                { Model.SigmaDeg = Json.dbl cfg "sigma_deg" 3.0
                  Model.CoreSigma = Json.dbl cfg "pit_core_sigma" 2.0
                  Model.WindowSigma = Json.dbl cfg "pit_window_sigma" 3.2
                  Model.PitMinAmp = Json.dbl cfg "pit_min_amp" 3e-3
                  Model.Tapering = Json.boolOf cfg "tapering" true }

        m.Fit(Json.doubles input "angles_deg", Json.doubles input "radii_mm")

        let wantDeg = Json.ints exp "degrees"
        let gotDeg = m.Degrees
        let mutable degOk = wantDeg.Length = gotDeg.Length
        if degOk then
            for i in 0 .. wantDeg.Length - 1 do
                if wantDeg.[i] <> gotDeg.[i] then degOk <- false
        if not degOk then
            ok <- false
            notes.Add(
                "степени ["
                + String.concat ", " (gotDeg |> Array.map string)
                + "] != ["
                + String.concat ", " (wantDeg |> Array.map string)
                + "]"
            )

        let rel = Json.dbl tol "coefs_rel" 0.0
        let floorV = Json.dbl tol "coefs_abs_floor" 0.0
        let coefs = Json.arrOf (Json.get exp "coefs")
        let mutable maxC = 0.0
        let mutable badC = 0
        for i in 0 .. coefs.Length - 1 do
            let refC = nums coefs.[i]
            let got = if i < m.Patches.Count then m.Patches.[i].Coefs else [||]
            if got.Length <> refC.Length then
                ok <- false
                badC <- badC + 1
            else
                for j in 0 .. refC.Length - 1 do
                    maxC <- Math.Max(maxC, Math.Abs(got.[j] - refC.[j]))
                    if not (near got.[j] refC.[j] rel floorV) then
                        ok <- false
                        badC <- badC + 1

        let pitTerms = Json.arrOf (Json.get exp "pit_terms")
        let mutable maxPit = 0.0
        let mutable badPit = 0
        for i in 0 .. pitTerms.Length - 1 do
            let refTerm = Json.objOf pitTerms.[i]
            let refDx = Json.doubles refTerm "dx_deg"
            let refAmp = Json.doubles refTerm "amp"
            let gotDx = if i < m.Patches.Count then m.Patches.[i].PitOffsetsDeg else [||]
            let gotAmp = if i < m.Patches.Count then m.Patches.[i].PitCoefs else [||]
            if gotDx.Length <> refDx.Length then
                ok <- false
                badPit <- badPit + 1
            else
                for j in 0 .. refDx.Length - 1 do
                    let da = Math.Abs(gotDx.[j] - refDx.[j])
                    maxPit <- Math.Max(maxPit, Math.Max(da, Math.Abs(gotAmp.[j] - refAmp.[j])))
                    if da > 1e-9 || not (near gotAmp.[j] refAmp.[j] rel floorV) then
                        ok <- false
                        badPit <- badPit + 1

        let curve = Json.objOf (Json.get exp "curve")
        let ca = Json.doubles curve "angles_deg"
        let cr = Json.doubles curve "radii_mm"
        let gotCurve = m.Eval ca
        let mutable maxR = 0.0
        for i in 0 .. cr.Length - 1 do
            maxR <- Math.Max(maxR, Math.Abs(gotCurve.[i] - cr.[i]))
        if maxR > Json.dbl tol "curve_mm" 1e-6 then ok <- false

        { Ok = ok
          Detail =
            String.concat
                ""
                [ "степени "
                  (if degOk then "совпали" else "РАСХОДЯТСЯ")
                  ", коэфф. max|Δ| "
                  Fmt.e2 maxC
                  " (плохих "
                  string badC
                  "), термины ям max|Δ| "
                  Fmt.e2 maxPit
                  " (плохих "
                  string badPit
                  "), контур max|Δ| "
                  Fmt.e2 maxR
                  " мм" ]
          Notes = List.ofSeq notes }

    /// Разбор вектора по полю kind: model / detector / cleaner.
    let check (v: Dictionary<string, Json.JVal>) : Result =
        match Json.strOf v "kind" "" with
        | "model" -> checkModel v
        | "detector" -> checkDetector v
        | _ -> checkCleaner v

/// Самопроверка без внешних зависимостей (xUnit/NUnit не тащим): конформанс-векторы,
/// дымовой тест пайплайна и round-trip документа. Запуск:
///   pappa selftest [каталог с векторами]
/// Код возврата: 0 — всё прошло, 1 — расхождения.
module SelfTest =

    /// Допуск для гладкого синтетического контура (у C#/Kotlin тот же 1e-6).
    let private smoothedTol = 1e-6

    /// Проверка формы документов сечений: формат, метод, число патчей, pit_terms, coefs.
    let private checkDocs (check: bool -> string -> unit) (dir: string) (secList: Json.JVal list) =
        let mutable docsChecked = 0
        for entry in secList do
            let e = Json.objOf entry
            let file = Json.strOf e "file" ""
            let doc = Json.parseObject (File.ReadAllText(Path.Combine(dir, file)))
            check
                (Json.strOf doc "format" "" = "pappa" && Json.strOf doc "version" "" = "2.0")
                (file + ": format=pappa version=2.0")
            check
                (Json.strOf doc "method" "" = "PitPatchApproximator")
                (file + ": method=PitPatchApproximator")
            let patches = Json.arrOf (Json.get doc "patches")
            check (patches.Length = 7) (file + ": патчей " + string patches.Length)
            let mutable withPitTerms = 0
            let mutable coefsOk = 0
            for po in patches do
                let p = Json.objOf po
                if Json.has p "pit_terms" then withPitTerms <- withPitTerms + 1
                if (Json.doubles p "coefs").Length = Json.intOf p "degree" 0 + 1 then
                    coefsOk <- coefsOk + 1
            check
                (withPitTerms = patches.Length)
                (file + ": pit_terms у каждого патча (" + string withPitTerms + "/" + string patches.Length + ")")
            check
                (coefsOk = patches.Length)
                (file + ": len(coefs) = degree+1 у каждого патча (" + string coefsOk + "/" + string patches.Length + ")")
            docsChecked <- docsChecked + 1
        check (docsChecked = 2) ("прочитано документов: " + string docsChecked)
    /// Папка образца пишется и тут же читается обратно: контракт документа — это
    /// не только «числа как у Python», но и форма (ключи, length(coefs) = degree+1,
    /// pit_terms у КАЖДОГО патча модели с ямами — этого ждёт загрузчик Python).
    let private runDocumentRoundTrip (check: bool -> string -> unit) =
        let dir =
            Path.Combine(Path.GetTempPath(), "pappa_fsharp_sample_" + Guid.NewGuid().ToString("N"))
        try
            try
                let sections = ResizeArray<Csv.SectionModel>()
                let opt = { Csv.defaultPipelineOptions with Verbose = false }
                for s in 0 .. 1 do
                    let rows = ResizeArray<Csv.Row>()
                    for i in 0 .. 359 do
                        // Профиль ровно как в конформанс-векторе детектора (шаг 1°):
                        // гладкая основа + шумовая подложка 47°/13° + ДВЕ резкие ямы-«ступени».
                        // Ямы обязаны быть «ступенями»: разницу узкой (1°) и широкой (10°)
                        // медиан даёт только резкий перепад, на плавном гауссе детектор ничего
                        // не найдёт и pit_terms не проверится. Шумовая подложка даёт
                        // индикатору масштаб (MAD).
                        let a = float i
                        let rad = a * Math.PI / 180.0
                        let mutable r =
                            15.0
                            + 0.4 * Math.Sin(2.0 * rad)
                            + 0.2 * Math.Cos(3.0 * rad)
                            + 0.03 * Math.Sin(47.0 * rad)
                            + 0.02 * Math.Sin(13.0 * rad)
                            + 0.01 * Math.Sin(37.0 * rad)
                        if Math.Abs(a - 90.0) <= 1.5 then r <- r - 1.1
                        if Math.Abs(a - 210.0) <= 1.0 then r <- r - 0.8
                        rows.Add(
                            { Csv.SectionId = s
                              Csv.HeightMm = 10.0 * float s
                              Csv.AngleDeg = a
                              Csv.RadiusMm = r }
                        )
                    let models = Csv.processSections (List.ofSeq rows) opt
                    check (models.Length = 1) ("сечение " + string s + ": посчитано " + string models.Length)
                    if models.Length > 0 then
                        let sm = models.Head
                        check
                            (sm.Pits.Length >= 1)
                            ("сечение " + string s + ": детектор нашёл ям " + string sm.Pits.Length)
                        let mutable kept = 0
                        for p in sm.Model.Patches do
                            if p.PitOffsetsDeg.Length > 0 then kept <- kept + 1
                        check (kept >= 1) ("сечение " + string s + ": патчей с терминами ям " + string kept)
                    sections.AddRange models

                Document.saveSample
                    dir
                    "selftest"
                    (List.ofSeq sections)
                    { Document.defaultSampleOptions with
                        Name = "selftest"
                        InputCsv = "selftest.csv"
                        Pits = true
                        Description = "F# SelfTest" }
                |> ignore

                let manifest = Json.parseObject (File.ReadAllText(Path.Combine(dir, "sample.json")))
                check (Json.strOf manifest "format" "" = "pappa-sample") "манифест: format=pappa-sample"
                let secList = Json.arrOf (Json.get manifest "sections")
                check (secList.Length = 2) ("манифест: секций " + string secList.Length)
                check
                    (File.Exists(Path.Combine(dir, "sections", "00.pappa.json")))
                    "сечения пишутся как sections/NN.pappa.json"
                checkDocs check dir secList
            with ex ->
                check false ("round-trip упал: " + ex.GetType().Name + ": " + ex.Message)
        finally
            try
                if Directory.Exists dir then Directory.Delete(dir, true)
            with _ ->
                ()

    /// Полная самопроверка; код возврата: 0 — всё прошло, 1 — расхождения.
    let run (vecDir: string) : int =
        let mutable failures = 0

        let check (ok: bool) (what: string) =
            Console.WriteLine("  " + (if ok then "[ok]" else "[FAIL]") + " " + what)
            if not ok then failures <- failures + 1

        Console.WriteLine(
            "F# SelfTest (.NET " + Environment.Version.ToString() + "): " + Path.GetFullPath(vecDir)
        )

        if not (Directory.Exists vecDir) then
            Console.WriteLine("[FAIL] нет каталога векторов: " + vecDir)
            1
        else
            // --- 1. конформанс-векторы ---
            let vectors = Conformance.load vecDir
            Console.WriteLine("векторы конформанса (" + string vectors.Length + "):")
            check (vectors.Length >= 4) "не меньше 4 векторов"
            for v in vectors do
                let r = Conformance.check v.Data
                check r.Ok (v.File + " — " + r.Detail)
                for note in r.Notes do
                    Console.WriteLine("       -> " + note)

            // --- 2. дымовой тест пайплайна: гладкая синусоида, 360 точек ---
            Console.WriteLine("дымовой тест пайплайна (гладкая синусоида, 360 точек):")
            let csv = StringBuilder("section_id,height_mm,angle_deg,radius_mm\n")
            for i in 0 .. 359 do
                csv.Append("0,0,") |> ignore
                csv.Append(i.ToString(Fmt.inv)) |> ignore
                csv.Append(',') |> ignore
                csv
                    .Append((50.0 + 0.4 * Math.Sin(float i * Math.PI / 180.0)).ToString("0.000000", Fmt.inv))
                |> ignore
                csv.Append('\n') |> ignore

            let tmp =
                Path.Combine(
                    Path.GetTempPath(),
                    "pappa_fsharp_selftest_" + Guid.NewGuid().ToString("N") + ".csv"
                )
            File.WriteAllText(tmp, csv.ToString(), UTF8Encoding(false))
            let rows = Csv.load tmp
            File.Delete tmp
            check (rows.Length = 360) "разбор CSV: 360 точек"

            let angles = rows |> List.map (fun r -> r.AngleDeg) |> List.toArray
            let radii = rows |> List.map (fun r -> r.RadiusMm) |> List.toArray
            let m = Model.Model(Model.defaultOptions, [||])
            m.Fit(angles, radii)
            check (m.Patches.Count = 7) ("патчей " + string m.Patches.Count)
            let curve = m.Eval angles
            let mutable maxErr = 0.0
            for i in 0 .. radii.Length - 1 do
                maxErr <- Math.Max(maxErr, Math.Abs(curve.[i] - radii.[i]))
            check
                (maxErr < smoothedTol)
                ("контур гладкой синусоиды: max|Δ| = "
                 + Fmt.e2 maxErr
                 + " мм (нужно < "
                 + Fmt.e2 smoothedTol
                 + ")")

            // --- 3. round-trip документа: папка образца -> разбор -> инварианты ---
            Console.WriteLine("round-trip документа (2 сечения, ямы включены):")
            runDocumentRoundTrip check

            Console.WriteLine(
                if failures = 0 then "ВЫВОД: SelfTest пройден"
                else "ВЫВОД: провалов " + string failures
            )
            (if failures = 0 then 0 else 1)

/// Точка входа F#-порта: pappa <команда> [ключи].
///
///   pappa conformance [каталог-векторов]    проверка по конформанс-векторам (0/1/2)
///   pappa selftest    [каталог-векторов]    векторы + дымовой тест + round-trip (0/1)
///   pappa pipeline    --input F.csv --out-dir DIR [--name N] [--description ТЕКСТ]
///                     [--no-pits] [--quiet]   CSV с сечениями -> папка образца
///
/// Почему подкоманды, а не три exe: .NET-проект с несколькими EntryPoint собирается
/// только через StartupObject, а один exe с командами читается ровно так же, как
/// pappa_conformance/pappa_pipeline у C++ и pappa.exe у C#-порта.
module Program =

    let private vecDir (args: string[]) =
        if args.Length > 0 && args.[0].Length > 0 then args.[0] else "../spec/conformance/vectors"

    let private usage () =
        Console.WriteLine("PAPPA (F#) — Piecewise Adaptive Poly-Patch Approximation.")
        Console.WriteLine()
        Console.WriteLine("  pappa conformance [каталог-векторов]")
        Console.WriteLine("  pappa selftest    [каталог-векторов]")
        Console.WriteLine("  pappa pipeline    --input FILE.csv --out-dir DIR [--name NAME]")
        Console.WriteLine("                    [--description ТЕКСТ] [--no-pits] [--quiet]")
        Console.WriteLine()
        Console.WriteLine("Каталог векторов по умолчанию: ../spec/conformance/vectors")

    let private runConformance (args: string[]) : int =
        let dir = vecDir args
        if not (Directory.Exists dir) then
            Console.WriteLine("нет каталога векторов: " + dir)
            2
        else
            let vectors = Conformance.load dir
            Console.WriteLine(
                "F# порт PAPPA: "
                + string vectors.Length
                + " векторов (.NET "
                + Environment.Version.ToString()
                + ", зависимостей из NuGet: 0)"
            )

            let mutable bad = 0
            for v in vectors do
                let r = Conformance.check v.Data
                if not r.Ok then bad <- bad + 1
                Console.WriteLine(
                    Fmt.pad v.File 46 + " " + Fmt.pad (if r.Ok then "OK" else "FAIL") 5 + " " + r.Detail
                )
                if not r.Ok then
                    for note in r.Notes |> List.truncate 4 do
                        Console.WriteLine(String(' ', 52) + "-> " + note)

            Console.WriteLine(
                if bad = 0 then "ВЫВОД: F#-порт проходит все векторы"
                else "ВЫВОД: расхождений " + string bad
            )
            (if bad = 0 then 0 else 1)

    let private runPipeline (args: string[]) : int =
        let mutable input = ""
        let mutable outDir = ""
        let mutable name = "sample"
        let mutable description = "PAPPA F# port"
        let mutable pits = true
        let mutable quiet = false
        let mutable badArgs = false

        let next (i: int) : string option =
            if i + 1 < args.Length then Some args.[i + 1] else None

        let mutable i = 0
        while i < args.Length && not badArgs do
            match args.[i] with
            | "--input" ->
                match next i with
                | Some v ->
                    input <- v
                    i <- i + 1
                | None -> badArgs <- true
            | "--out-dir" ->
                match next i with
                | Some v ->
                    outDir <- v
                    i <- i + 1
                | None -> badArgs <- true
            | "--name" ->
                match next i with
                | Some v ->
                    name <- v
                    i <- i + 1
                | None -> badArgs <- true
            | "--description" ->
                match next i with
                | Some v ->
                    description <- v
                    i <- i + 1
                | None -> badArgs <- true
            | "--no-pits" -> pits <- false
            | "--quiet" -> quiet <- true
            | _ -> badArgs <- true
            i <- i + 1

        if badArgs || String.IsNullOrEmpty input || String.IsNullOrEmpty outDir then
            usage ()
            2
        else
            let rows = Csv.load input
            Console.WriteLine("PAPPA (F#): " + string rows.Length + " точек, вход " + input)

            let opt =
                { Csv.defaultPipelineOptions with
                    Pits = pits
                    Verbose = not quiet }
            let sections = Csv.processSections rows opt
            let root =
                Document.saveSample
                    outDir
                    name
                    sections
                    { Document.defaultSampleOptions with
                        Name = name
                        InputCsv = input
                        Pits = pits
                        Description = description
                        Cleaner = opt.Cleaner
                        Detector = opt.Detector }

            Console.WriteLine()
            Console.WriteLine("Образец записан: " + root)
            Console.WriteLine("  манифест: " + Path.Combine(root, "sample.json"))
            Console.WriteLine("  сечений:  " + string sections.Length + " (sections/*.pappa.json)")
            Console.WriteLine()
            Console.WriteLine("Сверка с референсом Python:")
            Console.WriteLine(
                "  python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir "
                + root
            )
            0

    /// Точка входа: 0/1 — результат команды, 2 — неверные аргументы.
    [<EntryPoint>]
    let main argv =
        // Локаль машины не должна влиять ни на числа, ни на разделители.
        CultureInfo.DefaultThreadCurrentCulture <- Fmt.inv
        CultureInfo.DefaultThreadCurrentUICulture <- Fmt.inv
        try
            Console.OutputEncoding <- UTF8Encoding(false)
        with _ ->
            ()

        if argv.Length = 0 then
            usage ()
            2
        else
            try
                match argv.[0].ToLowerInvariant() with
                | "conformance"
                | "vectors" -> runConformance argv.[1..]
                | "selftest"
                | "test" -> SelfTest.run (vecDir argv.[1..])
                | "pipeline"
                | "run" -> runPipeline argv.[1..]
                | "help"
                | "--help"
                | "-h" ->
                    usage ()
                    0
                | _ ->
                    Console.Error.WriteLine("неизвестная команда: " + argv.[0])
                    usage ()
                    2
            with ex ->
                Console.Error.WriteLine("ОШИБКА: " + ex.GetType().Name + ": " + ex.Message)
                1







