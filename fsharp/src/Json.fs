/// Минимальный JSON: разбор и запись без внешних зависимостей.
///
/// Разобранное значение — размеченное объединение (в F# это дешевле и безопаснее,
/// чем boxed object в C#-порте): объект -> JOfObj (Dictionary), массив -> JOfArr,
/// число -> float (как в Python-референсе, целые тоже), строка -> string.
module Pappa.Json

open System
open System.Collections.Generic
open System.Globalization
open System.Text

/// Узел разобранного JSON.
type JVal =
    | JNull
    | JOfBool of bool
    | JOfNum of float
    | JOfStr of string
    | JOfArr of JVal list
    | JOfObj of Dictionary<string, JVal>

/// Рекурсивный спуск — ровно столько, сколько нужно векторам и документам.
type private Parser(text: string) =
    let s = text
    let mutable i = 0

    let ws () =
        while i < s.Length && Char.IsWhiteSpace s.[i] do
            i <- i + 1

    let expect (lit: string) =
        if i + lit.Length > s.Length || String.CompareOrdinal(s, i, lit, 0, lit.Length) <> 0 then
            failwith ("JSON: ожидался литерал " + lit + " в позиции " + string i)
        i <- i + lit.Length

    let rec value () : JVal =
        match s.[i] with
        | '{' -> objBody ()
        | '[' -> arrBody ()
        | '"' -> JOfStr (strBody ())
        | 't' ->
            expect "true"
            JOfBool true
        | 'f' ->
            expect "false"
            JOfBool false
        | 'n' ->
            expect "null"
            JNull
        | _ -> JOfNum (number ())

    and objBody () : JVal =
        let m = Dictionary<string, JVal>()
        i <- i + 1
        ws ()
        if s.[i] = '}' then
            i <- i + 1
            JOfObj m
        else
            let mutable go = true
            while go do
                ws ()
                let k = strBody ()
                ws ()
                if s.[i] <> ':' then failwith ("JSON: ожидалось ':' в позиции " + string i)
                i <- i + 1
                ws ()
                m.[k] <- value ()
                ws ()
                let c = s.[i]
                i <- i + 1
                if c = '}' then go <- false
                elif c <> ',' then failwith "JSON: ожидалась ',' или '}'"
            JOfObj m

    and arrBody () : JVal =
        let acc = ResizeArray<JVal>()
        i <- i + 1
        ws ()
        if s.[i] = ']' then
            i <- i + 1
            JOfArr (List.ofSeq acc)
        else
            let mutable go = true
            while go do
                ws ()
                acc.Add(value ())
                ws ()
                let c = s.[i]
                i <- i + 1
                if c = ']' then go <- false
                elif c <> ',' then failwith "JSON: ожидалась ',' или ']'"
            JOfArr (List.ofSeq acc)

    and strBody () : string =
        if s.[i] <> '"' then failwith ("JSON: ожидалась строка в позиции " + string i)
        i <- i + 1
        let b = StringBuilder()
        let mutable go = true
        while go do
            let c = s.[i]
            i <- i + 1
            if c = '"' then go <- false
            elif c <> '\\' then b.Append(c) |> ignore
            else
                let esc = s.[i]
                i <- i + 1
                match esc with
                | 'n' -> b.Append('\n') |> ignore
                | 't' -> b.Append('\t') |> ignore
                | 'r' -> b.Append('\r') |> ignore
                | 'b' -> b.Append('\b') |> ignore
                | 'f' -> b.Append('\f') |> ignore
                | 'u' ->
                    b.Append(char (Convert.ToInt32(s.Substring(i, 4), 16))) |> ignore
                    i <- i + 4
                | other -> b.Append(other) |> ignore
        b.ToString()

    and number () : float =
        let start = i
        while i < s.Length && "+-0123456789.eE".IndexOf(s.[i]) >= 0 do
            i <- i + 1
        let t = s.Substring(start, i - start)
        match Double.TryParse(t, NumberStyles.Float, Fmt.inv) with
        | true, v -> v
        | _ -> failwith ("JSON: плохое число " + t)

    member _.Run() : JVal =
        ws ()
        value ()

/// Разбор произвольного JSON.
let parse (text: string) : JVal = (Parser(text)).Run()

/// Разбор JSON-объекта (верхний уровень обязан быть объектом).
let parseObject (text: string) : Dictionary<string, JVal> =
    match parse text with
    | JOfObj m -> m
    | _ -> failwith "JSON: ожидался объект"

// ---------- доступ к разобранному ----------

let objOf (v: JVal) : Dictionary<string, JVal> =
    match v with
    | JOfObj m -> m
    | _ -> failwith "JSON: ожидался объект"

let arrOf (v: JVal) : JVal list =
    match v with
    | JOfArr a -> a
    | _ -> failwith "JSON: ожидался массив"

let has (m: Dictionary<string, JVal>) (k: string) : bool = m.ContainsKey(k)

let getOpt (m: Dictionary<string, JVal>) (k: string) : JVal option =
    match m.TryGetValue(k) with
    | true, v -> Some v
    | _ -> None

/// Отсутствующий ключ -> JNull (как object-версия в C#: null).
let get (m: Dictionary<string, JVal>) (k: string) : JVal =
    match getOpt m k with
    | Some v -> v
    | None -> JNull

let dbl (m: Dictionary<string, JVal>) (k: string) (def: float) : float =
    match getOpt m k with
    | Some (JOfNum d) -> d
    | _ -> def

let intOf (m: Dictionary<string, JVal>) (k: string) (def: int) : int =
    match getOpt m k with
    | Some (JOfNum d) -> int d
    | _ -> def

let strOf (m: Dictionary<string, JVal>) (k: string) (def: string) : string =
    match getOpt m k with
    | Some (JOfStr s) -> s
    | _ -> def

let boolOf (m: Dictionary<string, JVal>) (k: string) (def: bool) : bool =
    match getOpt m k with
    | Some (JOfBool b) -> b
    | _ -> def

let doubles (m: Dictionary<string, JVal>) (k: string) : float[] =
    arrOf (get m k)
    |> List.map (fun v ->
        match v with
        | JOfNum d -> d
        | _ -> nan)
    |> List.toArray

let ints (m: Dictionary<string, JVal>) (k: string) : int[] =
    arrOf (get m k)
    |> List.map (fun v ->
        match v with
        | JOfNum d -> int d
        | _ -> 0)
    |> List.toArray

/// Число в документе: целые — без дробной части, иначе shortest round-trip
/// (.NET Core 3.0+ печатает кратчайшую строку, которая читается обратно).
/// Очень большие/малые значения уходят в экспоненциальную форму "1E-12" —
/// это валидный JSON, Python его читает.
let num (v: float) : string =
    if Double.IsNaN v || Double.IsInfinity v then "0"
    elif v = Math.Round(v, MidpointRounding.ToEven) && Math.Abs(v) < 1e15 then (int64 v).ToString(Fmt.inv)
    else v.ToString("R", Fmt.inv)

let escape (s: string) : string =
    let b = StringBuilder(s.Length + 8)
    for c in s do
        match c with
        | '"' -> b.Append("\\\"") |> ignore
        | '\\' -> b.Append("\\\\") |> ignore
        | '\n' -> b.Append("\\n") |> ignore
        | '\r' -> b.Append("\\r") |> ignore
        | '\t' -> b.Append("\\t") |> ignore
        | other -> b.Append(other) |> ignore
    b.ToString()
