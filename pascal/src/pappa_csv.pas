unit pappa_csv;
{ Чтение CSV по заголовку и посекционный расчёт (как go/pappa/csv.go). }
{$mode objfpc}{$H+}

interface

uses
  SysUtils, Classes, DateUtils,
  pappa_signal, pappa_json, pappa_cleaner, pappa_detector, pappa_model;

type
  TRow = record
    SectionId: Integer;
    HeightMm, AngleDeg, RadiusMm: Double;
  end;

  TRowArray = array of TRow;

  TSectionModel = class
  public
    SectionId: Integer;
    HeightMm: Double;
    Model: TModel;
    NPointsTotal, NOutliers, NUsed: Integer;
    FitTimeMs: Double;
    Description: string;
    Pits: TDoubleArray;
    constructor Create;
    destructor Destroy; override;
  end;

  TSectionArray = array of TSectionModel;

  TPipelineOptions = record
    Model: TModelOptions;
    Cleaner: TCleanerOptions;
    Detector: TDetectorOptions;
    Pits, Verbose: Boolean;
  end;

function DefaultPipelineOptions: TPipelineOptions;
function SplitComma(const S: string): TStrArray;
function LoadCsv(const Path: string): TRowArray;
function ProcessSections(const Rows: TRowArray; const Opt: TPipelineOptions): TSectionArray;

implementation

constructor TSectionModel.Create;
begin
  inherited Create;
  Model := nil;
  SetLength(Pits, 0);
end;

destructor TSectionModel.Destroy;
begin
  Model.Free;
  inherited Destroy;
end;

function DefaultPipelineOptions: TPipelineOptions;
begin
  Result.Model := DefaultModelOptions;
  Result.Cleaner := DefaultCleanerOptions;
  Result.Detector := DefaultDetectorOptions;
  Result.Pits := True;
  Result.Verbose := True;
end;

function SplitComma(const S: string): TStrArray;
var
  I, K: Integer;
  Cur: string;
begin
  SetLength(Result, Length(S) + 1);
  K := 0;
  Cur := '';
  for I := 1 to Length(S) do
  begin
    if S[I] = ',' then
    begin
      Result[K] := Trim(Cur);
      Inc(K);
      Cur := '';
    end
    else
      Cur := Cur + S[I];
  end;
  Result[K] := Trim(Cur);
  Inc(K);
  SetLength(Result, K);
end;

function FindCol(const Head: TStrArray; const Name: string): Integer;
var
  I: Integer;
begin
  for I := 0 to High(Head) do
    if Head[I] = Name then Exit(I);
  Result := -1;
end;

function LoadCsv(const Path: string): TRowArray;
var
  Text, Line: string;
  Lines: TStrArray;
  Head, F: TStrArray;
  I, K, No, ISec, IH, IA, IR, Need: Integer;
begin
  SetLength(Result, 0);
  Text := ReadTextFile(Path);
  { разбиваем на строки по #10/#13 }
  SetLength(Lines, Length(Text) + 1);
  K := 0;
  Line := '';
  for I := 1 to Length(Text) do
  begin
    if (Text[I] = #10) or (Text[I] = #13) then
    begin
      if Trim(Line) <> '' then
      begin
        Lines[K] := Line;
        Inc(K);
      end;
      Line := '';
    end
    else
      Line := Line + Text[I];
  end;
  if Trim(Line) <> '' then
  begin
    Lines[K] := Line;
    Inc(K);
  end;
  SetLength(Lines, K);
  if K = 0 then raise Exception.CreateFmt('пустой CSV: %s', [Path]);

  Head := SplitComma(Lines[0]);
  ISec := FindCol(Head, 'section_id');
  IH := FindCol(Head, 'height_mm');
  IA := FindCol(Head, 'angle_deg');
  IR := FindCol(Head, 'radius_mm');
  if ISec < 0 then raise Exception.Create('в CSV нет колонки section_id');
  if IH < 0 then raise Exception.Create('в CSV нет колонки height_mm');
  if IA < 0 then raise Exception.Create('в CSV нет колонки angle_deg');
  if IR < 0 then raise Exception.Create('в CSV нет колонки radius_mm');
  Need := ISec;
  if IH > Need then Need := IH;
  if IA > Need then Need := IA;
  if IR > Need then Need := IR;

  No := 0;
  SetLength(Result, K - 1);
  for I := 1 to K - 1 do
  begin
    F := SplitComma(Lines[I]);
    if Length(F) <= Need then Continue;
    Result[No].SectionId := StrToInt(F[ISec]);
    Result[No].HeightMm := StrToFloat(F[IH]);
    Result[No].AngleDeg := StrToFloat(F[IA]);
    Result[No].RadiusMm := StrToFloat(F[IR]);
    Inc(No);
  end;
  SetLength(Result, No);
  if No = 0 then raise Exception.Create('в CSV нет строк с данными');
end;

function ProcessSections(const Rows: TRowArray; const Opt: TPipelineOptions): TSectionArray;
var
  Ids: TIntArray;
  I, J, K, Sid, N, Count, NOut: Integer;
  Group: TRowArray;
  Angles, Radii, AClean, RClean: TDoubleArray;
  CR: TCleanResult;
  PitCenters: TDoubleArray;
  M: TModel;
  Sec: TSectionModel;
  T0: TDateTime;
begin
  SetLength(Result, 0);
  SetLength(Ids, 0);
  for I := 0 to High(Rows) do
  begin
    if Length(Ids) = 0 then
    begin
      SetLength(Ids, 1);
      Ids[0] := Rows[I].SectionId;
    end
    else
    begin
      K := 0;
      for J := 0 to High(Ids) do
        if Ids[J] = Rows[I].SectionId then Inc(K);
      if K = 0 then
      begin
        SetLength(Ids, Length(Ids) + 1);
        Ids[High(Ids)] := Rows[I].SectionId;
      end;
    end;
  end;
  { сортировка идентификаторов }
  for I := 0 to High(Ids) - 1 do
    for J := I + 1 to High(Ids) do
      if Ids[J] < Ids[I] then
      begin
        K := Ids[I]; Ids[I] := Ids[J]; Ids[J] := K;
      end;

  for I := 0 to High(Ids) do
  begin
    Sid := Ids[I];
    SetLength(Group, 0);
    for J := 0 to High(Rows) do
      if Rows[J].SectionId = Sid then
      begin
        SetLength(Group, Length(Group) + 1);
        Group[High(Group)] := Rows[J];
      end;
    { сортировка точек сечения по углу (простая вставка) }
    for J := 1 to High(Group) do
    begin
      K := J - 1;
      while (K >= 0) and (Group[K].AngleDeg > Group[K + 1].AngleDeg) do
      begin
        Group[K + 1] := Group[K];
        Dec(K);
      end;
    end;
    N := Length(Group);
    SetLength(Angles, N);
    SetLength(Radii, N);
    for J := 0 to N - 1 do
    begin
      Angles[J] := Group[J].AngleDeg;
      Radii[J] := Group[J].RadiusMm;
    end;

    CR := CleanIQR(Angles, Radii, Opt.Cleaner);
    SetLength(AClean, N);
    SetLength(RClean, N);
    Count := 0;
    for J := 0 to N - 1 do
      if not CR.Mask[J] then
      begin
        AClean[Count] := Angles[J];
        RClean[Count] := Radii[J];
        Inc(Count);
      end;
    SetLength(AClean, Count);
    SetLength(RClean, Count);
    NOut := CR.NOutliers;

    if Opt.Pits then PitCenters := Pits(AClean, RClean, Opt.Detector)
    else SetLength(PitCenters, 0);
    M := TModel.Create(Opt.Model, PitCenters);
    T0 := Now;
    M.Fit(AClean, RClean);

    Sec := TSectionModel.Create;
    Sec.SectionId := Sid;
    Sec.HeightMm := Group[0].HeightMm;
    Sec.Model := M;
    Sec.NPointsTotal := N;
    Sec.NOutliers := NOut;
    Sec.NUsed := Count;
    Sec.Pits := PitCenters;
    Sec.FitTimeMs := MilliSecondsBetween(Now, T0);
    Sec.Description := Format('сечение %d, h=%.0f мм', [Sid, Group[0].HeightMm]);

    if Opt.Verbose then
      WriteLn(Format('  секция %d (h=%.0f мм): точек %d, выброшено %d, ям найдено %d, обучение %.0f мс',
        [Sid, Sec.HeightMm, N, NOut, Length(PitCenters), Sec.FitTimeMs]));

    SetLength(Result, Length(Result) + 1);
    Result[High(Result)] := Sec;
  end;
end;

end.
