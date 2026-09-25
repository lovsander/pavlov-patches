unit pappa_conformance;
{ Проверка порта по конформанс-векторам (spec/conformance/vectors).
  Допуски — те же, что у C++/Go/C/JS/Java/Kotlin/Rust: контур 1e-6 мм,
  коэффициенты max(1e-8, 1e-9·|c|), детектор 1e-6°, очистка — доля точек (frac). }
{$mode objfpc}{$H+}

interface

uses
  Math, SysUtils, Classes,
  pappa_signal, pappa_json, pappa_cleaner, pappa_detector, pappa_model;

type
  TOutcome = record
    Ok: Boolean;
    Detail: string;
    Notes: TStrArray;
  end;

  TVector = class
  public
    FileName: string;
    Data: TJsonNode;
    destructor Destroy; override;
  end;

  TVectorArray = array of TVector;

function LoadVectors(const Dir: string): TVectorArray;
function CheckVector(V: TJsonNode): TOutcome;

implementation

destructor TVector.Destroy;
begin
  Data.Free;
  inherited Destroy;
end;

function LoadVectors(const Dir: string): TVectorArray;
var
  SR: TSearchRec;
  Names: TStrArray;
  I, J, K: Integer;
  Tmp: string;
  V: TVector;
begin
  SetLength(Result, 0);
  SetLength(Names, 0);
  if FindFirst(IncludeTrailingPathDelimiter(Dir) + '*.json', faAnyFile, SR) = 0 then
  begin
    repeat
      SetLength(Names, Length(Names) + 1);
      Names[High(Names)] := SR.Name;
    until FindNext(SR) <> 0;
    FindClose(SR);
  end;
  if Length(Names) = 0 then
    raise Exception.CreateFmt('нет каталога векторов: %s', [Dir]);
  { сортировка имён }
  for I := 0 to High(Names) - 1 do
    for J := I + 1 to High(Names) do
      if Names[J] < Names[I] then
      begin
        Tmp := Names[I]; Names[I] := Names[J]; Names[J] := Tmp;
      end;

  K := 0;
  SetLength(Result, Length(Names));
  for I := 0 to High(Names) do
  begin
    V := TVector.Create;
    V.FileName := Names[I];
    V.Data := JsonParse(ReadTextFile(IncludeTrailingPathDelimiter(Dir) + Names[I]));
    Result[K] := V;
    Inc(K);
  end;
end;

function Near(A, B, Rel, Flr: Double): Boolean;
begin
  Result := Abs(A - B) <= Flr;
  if not Result then
    Result := Abs(A - B) <= Rel * Abs(B);
end;

function CheckModel(V: TJsonNode): TOutcome;
var
  Cfg, Exp, Tol, Input: TJsonNode;
  Opt: TModelOptions;
  PS: TPitShape;
  PitsDeg: TDoubleArray;
  M: TModel;
  WantDeg, GotDeg: TIntArray;
  DegOk, Ok: Boolean;
  Rel, Flr, MaxC, MaxPit, MaxR: Double;
  BadC, BadPit, I, J: Integer;
  CoefsN, TermsN: TJsonNode;
  RefD, RefA, GotD, GotA, CA, CR, Got: TDoubleArray;
  Tmp: TJsonNode;
begin
  Cfg := V.Get('config');
  Exp := V.Get('expected');
  Tol := V.Get('tolerance');
  Input := V.Get('input');

  Opt.NPatches := Cfg.Int('n_patches');
  Opt.PhaseDeg := Cfg.Dbl('phase_deg');
  Opt.DegMin := Cfg.Int('deg_min');
  Opt.DegMax := Cfg.Int('deg_max');
  Opt.OverlapTrain := Cfg.Dbl('overlap_train');
  Opt.OverlapUse := Cfg.Dbl('overlap_use');
  Opt.DegElbowTol := Cfg.Dbl('deg_elbow_tol');
  Opt.AmplitudeScale := Cfg.DblOr('amplitude_scale', 180.0);
  Opt.CoordMode := Cfg.Text('coord_mode');
  PitsDeg := Cfg.Doubles('pits_deg');

  M := TModel.Create(Opt, PitsDeg);
  try
    if Length(PitsDeg) > 0 then
    begin
      PS.SigmaDeg := Cfg.Dbl('sigma_deg');
      PS.CoreSigma := Cfg.Dbl('pit_core_sigma');
      PS.WindowSigma := Cfg.Dbl('pit_window_sigma');
      PS.PitMinAmp := Cfg.Dbl('pit_min_amp');
      PS.Tapering := Cfg.BoolOr('tapering', True);
      M.SetPitShape(PS);
    end;
    M.Fit(Input.Doubles('angles_deg'), Input.Doubles('radii_mm'));

    Ok := True;
    SetLength(Result.Notes, 0);
    WantDeg := Exp.Ints('degrees');
    GotDeg := M.Degrees;
    DegOk := Length(WantDeg) = Length(GotDeg);
    if DegOk then
      for I := 0 to High(WantDeg) do
        if WantDeg[I] <> GotDeg[I] then DegOk := False;
    if not DegOk then
    begin
      Ok := False;
      SetLength(Result.Notes, Length(Result.Notes) + 1);
      Result.Notes[High(Result.Notes)] := 'степени не совпали';
    end;

    Rel := Tol.Dbl('coefs_rel');
    Flr := Tol.Dbl('coefs_abs_floor');
    MaxC := 0; BadC := 0;
    CoefsN := Exp.Get('coefs');
    for I := 0 to CoefsN.ArrCount - 1 do
    begin
      RefD := CoefsN.Arr[I].AsDoublesArray;
      if I <= High(M.Patches) then GotD := M.Patches[I].Coefs
      else SetLength(GotD, 0);
      if Length(GotD) <> Length(RefD) then
      begin
        Ok := False; Inc(BadC); Continue;
      end;
      for J := 0 to High(RefD) do
      begin
        if Abs(GotD[J] - RefD[J]) > MaxC then MaxC := Abs(GotD[J] - RefD[J]);
        if not Near(GotD[J], RefD[J], Rel, Flr) then
        begin
          Ok := False; Inc(BadC);
        end;
      end;
    end;

    MaxPit := 0; BadPit := 0;
    TermsN := Exp.Get('pit_terms');
    for I := 0 to TermsN.ArrCount - 1 do
    begin
      Tmp := TermsN.Arr[I];
      RefD := Tmp.Doubles('dx_deg');
      RefA := Tmp.Doubles('amp');
      if I <= High(M.Patches) then
      begin
        GotD := M.Patches[I].PitOffsetsDeg;
        GotA := M.Patches[I].PitCoefs;
      end
      else
      begin
        SetLength(GotD, 0);
        SetLength(GotA, 0);
      end;
      if Length(GotD) <> Length(RefD) then
      begin
        Ok := False; Inc(BadPit); Continue;
      end;
      for J := 0 to High(RefD) do
      begin
        if Abs(GotD[J] - RefD[J]) > MaxPit then MaxPit := Abs(GotD[J] - RefD[J]);
        if Abs(GotA[J] - RefA[J]) > MaxPit then MaxPit := Abs(GotA[J] - RefA[J]);
        if (Abs(GotD[J] - RefD[J]) > 1e-9) or (not Near(GotA[J], RefA[J], Rel, Flr)) then
        begin
          Ok := False; Inc(BadPit);
        end;
      end;
    end;

    Tmp := Exp.Get('curve');
    CA := Tmp.Doubles('angles_deg');
    CR := Tmp.Doubles('radii_mm');
    Got := M.Eval(CA);
    MaxR := 0;
    for I := 0 to High(CR) do
      if Abs(Got[I] - CR[I]) > MaxR then MaxR := Abs(Got[I] - CR[I]);
    if MaxR > Tol.Dbl('curve_mm') then Ok := False;

    Result.Ok := Ok;
    Result.Detail := Format('степени %s, коэфф. max|Δ| %.2e (плохих %d), ' +
      'термины ям max|Δ| %.2e (плохих %d), контур max|Δ| %.2e мм',
      [BoolToStr(DegOk, 'совпали', 'РАСХОДЯТСЯ'), MaxC, BadC, MaxPit, BadPit, MaxR]);
  finally
    M.Free;
  end;
end;

function CheckDetector(V: TJsonNode): TOutcome;
var
  Cfg, Exp, Input: TJsonNode;
  O: TDetectorOptions;
  Angles, Radii, Band: TDoubleArray;
  ZArr: TZoneArray;
  ExpZones: TJsonNode;
  ExpPits: TDoubleArray;
  Ok: Boolean;
  Dev, D: Double;
  I: Integer;
begin
  Cfg := V.Get('config');
  Exp := V.Get('expected');
  Input := V.Get('input');
  O.WindowDeg := Cfg.Dbl('window_deg');
  O.WideDeg := Cfg.Dbl('wide_deg');
  O.SmoothDeg := Cfg.Dbl('smooth_deg');
  O.K := Cfg.Dbl('k');
  O.MinZoneDeg := Cfg.Dbl('min_zone_deg');

  Angles := Input.Doubles('angles_deg');
  Radii := Input.Doubles('radii_mm');
  Band := BandIndicator(Angles, Radii, O);
  ZArr := Zones(Angles, Band, O);
  ExpZones := Exp.Get('zones_deg');
  ExpPits := Exp.Doubles('pits_deg');
  SetLength(Result.Notes, 0);

  Ok := Length(ZArr) = ExpZones.ArrCount;
  if not Ok then
  begin
    SetLength(Result.Notes, Length(Result.Notes) + 1);
    Result.Notes[High(Result.Notes)] :=
      Format('зон %d != %d', [Length(ZArr), ExpZones.ArrCount]);
  end;
  Dev := 0;
  for I := 0 to ExpZones.ArrCount - 1 do
    if I < Length(ZArr) then
    begin
      D := Abs(ZArr[I].Lo - ExpZones.Arr[I].Arr[0].AsDouble);
      if D > Dev then Dev := D;
      D := Abs(ZArr[I].Hi - ExpZones.Arr[I].Arr[1].AsDouble);
      if D > Dev then Dev := D;
    end;
  if Length(ZArr) <> Length(ExpPits) then
  begin
    Ok := False;
    SetLength(Result.Notes, Length(Result.Notes) + 1);
    Result.Notes[High(Result.Notes)] :=
      Format('ям %d != %d', [Length(ZArr), Length(ExpPits)]);
  end;
  for I := 0 to High(ExpPits) do
    if I < Length(ZArr) then
    begin
      D := Abs(0.5 * (ZArr[I].Lo + ZArr[I].Hi) - ExpPits[I]);
      if D > Dev then Dev := D;
      if D > 1e-6 then Ok := False;
    end;

  Result.Ok := Ok;
  Result.Detail := Format('зон %d/%d, ям %d/%d, max|Δ| %.2e°',
    [Length(ZArr), ExpZones.ArrCount, Length(ZArr), Length(ExpPits), Dev]);
end;

function CheckCleaner(V: TJsonNode): TOutcome;
var
  Cfg, Exp, Input, Tol: TJsonNode;
  O: TCleanerOptions;
  Angles, Radii: TDoubleArray;
  RefMask: array of Boolean;
  Idx: TIntArray;
  CR: TCleanResult;
  N, I, Extra, Missing, Got, TolN, Want: Integer;
  Frac: Double;
begin
  Cfg := V.Get('config');
  Exp := V.Get('expected');
  Input := V.Get('input');
  Tol := V.Get('tolerance');
  O := DefaultCleanerOptions;
  O.BaselineDeg := Cfg.Dbl('baseline_deg');
  O.IqrK := Cfg.Dbl('iqr_k');

  Angles := Input.Doubles('angles_deg');
  Radii := Input.Doubles('radii_mm');
  CR := CleanIQR(Angles, Radii, O);
  N := Length(Radii);
  SetLength(RefMask, N);
  for I := 0 to N - 1 do RefMask[I] := False;
  Idx := Exp.Ints('mask_true_indices');
  for I := 0 to High(Idx) do
    if (Idx[I] >= 0) and (Idx[I] < N) then RefMask[Idx[I]] := True;

  Extra := 0; Missing := 0; Got := 0;
  for I := 0 to N - 1 do
    if CR.Mask[I] then
    begin
      Inc(Got);
      if not RefMask[I] then Inc(Extra);
    end
    else if RefMask[I] then
      Inc(Missing);
  Frac := Tol.DblOr('frac', 0.02);
  TolN := Trunc(Floor(Frac * N));
  if TolN < 1 then TolN := 1;
  Want := Exp.Int('n_outliers');
  Result.Ok := (Extra <= TolN) and (Missing <= TolN) and (Abs(Got - Want) <= TolN);
  SetLength(Result.Notes, 0);
  Result.Detail := Format('выбросов %d (эталон %d), лишних %d, пропущено %d',
    [Got, Want, Extra, Missing]);
end;

function CheckVector(V: TJsonNode): TOutcome;
var
  Kind: string;
begin
  Kind := V.Text('kind');
  if Kind = 'model' then Result := CheckModel(V)
  else if Kind = 'detector' then Result := CheckDetector(V)
  else Result := CheckCleaner(V);
end;

end.
