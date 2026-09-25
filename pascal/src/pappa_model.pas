unit pappa_model;
{ Модель PAPPA (Free Pascal): патчи с адаптивной степенью по нормированной
  координате, smoothstep-смешивание (partition of unity) и оконный гауссов фичер
  ям. Совпадает с референсом Python и остальными портами: тот же базис, та же
  политика степени («локоть»), тот же МНК (QR Хаусхолдера). Свип степеней —
  ОДНИМ накоплением Грама в базисе Чебышёва + RMSE по явным остаткам. }
{$mode objfpc}{$H+}

interface

uses
  SysUtils,
  Math, pappa_signal, pappa_linalg;

type
  TModelOptions = record
    NPatches: Integer;
    PhaseDeg: Double;
    DegMin, DegMax: Integer;
    OverlapTrain, OverlapUse, DegElbowTol, AmplitudeScale: Double;
    CoordMode: string;
  end;

  TPitShape = record
    SigmaDeg, CoreSigma, WindowSigma, PitMinAmp: Double;
    Tapering: Boolean;
  end;

  TMetrics = record
    AmplitudeMm, MeanRadiusMm, AmplitudeNorm, DegElbowTol: Double;
    RmseSelectedMm, RmseBestMm: Double;
    NTrainPoints: Integer;
  end;

  TStats = record
    RmseMm, MaeMm, MaxErrMm, Correlation: Double;
  end;

  TPatch = record
    CenterDeg: Double;
    Degree, NPoints: Integer;
    Coefs, PitOffsetsDeg, PitCoefs: TDoubleArray;
    Metrics: TMetrics;
    Stats: TStats;
  end;

  TPatchArray = array of TPatch;

  TDegreeChoice = record
    Deg: Integer;
    RmseSel, RmseBest: Double;
  end;

  TModel = class
  private
    FOpt: TModelOptions;
    FPit: TPitShape;
    FPits: TDoubleArray;
    FPatches: TPatchArray;
    FHalfSector: Double;
    FFitted: Boolean;
    function EstimateDegree(const Xs, Ys: TDoubleArray): TDegreeChoice;
    function WindowOf(const Angles, Radii: TDoubleArray; Center: Double;
      out Xs, Ys: TDoubleArray): Integer;
    function BuildPatch(C: Double; Deg: Integer; const Xs, Ys, PolyCoef
      : TDoubleArray; const KeptOffsets, KeptCoefs: TDoubleArray;
      const Est: TDegreeChoice; const Angles, Radii: TDoubleArray): TPatch;
  public
    constructor Create(const Opt: TModelOptions; const PitsDeg: TDoubleArray);
    procedure SetPitShape(const S: TPitShape);
    function HasPits: Boolean;
    function HalfTrain: Double;
    function HalfUse: Double;
    function PitShapeDeg(DDeg: Double): Double;
    function PitOffsets(CDeg, HalfWin: Double): TDoubleArray;
    function Weight(DDeg, HalfUseDeg: Double): Double;
    function Degrees: TIntArray;
    procedure Fit(const Angles, Radii: TDoubleArray);
    function EvalPart(const Angles: TDoubleArray; const Part: string): TDoubleArray;
    function Eval(const Angles: TDoubleArray): TDoubleArray;
    property Options: TModelOptions read FOpt;
    property PitShape: TPitShape read FPit;
    property Pits: TDoubleArray read FPits;
    property Patches: TPatchArray read FPatches;
    property HalfSector: Double read FHalfSector;
    property IsFitted: Boolean read FFitted;
  end;

function DefaultModelOptions: TModelOptions;
function DefaultPitShape: TPitShape;

implementation

function DefaultModelOptions: TModelOptions;
begin
  Result.NPatches := 7;
  Result.PhaseDeg := 24.75;
  Result.DegMin := 4;
  Result.DegMax := 14;
  Result.OverlapTrain := 15.0;
  Result.OverlapUse := 5.0;
  Result.DegElbowTol := 0.05;
  Result.AmplitudeScale := 180.0;
  Result.CoordMode := 'normalized';
end;

function DefaultPitShape: TPitShape;
begin
  Result.SigmaDeg := 3.0;
  Result.CoreSigma := 2.0;
  Result.WindowSigma := 3.2;
  Result.PitMinAmp := 3e-3;
  Result.Tapering := True;
end;

constructor TModel.Create(const Opt: TModelOptions; const PitsDeg: TDoubleArray);
var
  I: Integer;
begin
  inherited Create;
  FOpt := Opt;
  FPit := DefaultPitShape;
  SetLength(FPits, Length(PitsDeg));
  for I := 0 to High(PitsDeg) do
  begin
    FPits[I] := FMod(PitsDeg[I], 360.0);
    if FPits[I] < 0 then FPits[I] := FPits[I] + 360.0;
  end;
  SetLength(FPatches, 0);
  FHalfSector := 0;
  FFitted := False;
end;

procedure TModel.SetPitShape(const S: TPitShape);
begin
  FPit := S;
end;

function TModel.HasPits: Boolean;
begin
  Result := Length(FPits) > 0;
end;

function TModel.HalfTrain: Double;
begin
  Result := FHalfSector + FOpt.OverlapTrain;
end;

function TModel.HalfUse: Double;
begin
  Result := FHalfSector + FOpt.OverlapUse;
end;

function TModel.PitShapeDeg(DDeg: Double): Double;
var
  D, Core, Edge, T: Double;
begin
  D := Abs(DDeg);
  Result := Exp(-(D * D) / (2 * FPit.SigmaDeg * FPit.SigmaDeg));
  if not FPit.Tapering then Exit;
  Core := FPit.CoreSigma * FPit.SigmaDeg;
  Edge := FPit.WindowSigma * FPit.SigmaDeg;
  if Edge <= Core then Exit;
  T := (Edge - D) / (Edge - Core);
  if T < 0 then T := 0;
  if T > 1 then T := 1;
  Result := Result * T * T * (3 - 2 * T);
end;

function TModel.PitOffsets(CDeg, HalfWin: Double): TDoubleArray;
var
  I, K: Integer;
  DX: Double;
begin
  SetLength(Result, Length(FPits));
  K := 0;
  for I := 0 to High(FPits) do
  begin
    DX := CircLocal(FPits[I], CDeg);
    if Abs(DX) <= HalfWin then
    begin
      Result[K] := DX;
      Inc(K);
    end;
  end;
  SetLength(Result, K);
end;

function TModel.Weight(DDeg, HalfUseDeg: Double): Double;
begin
  if DDeg <= FHalfSector then
    Result := 1.0
  else if DDeg <= HalfUseDeg then
    Result := SmoothStep(1.0 - (DDeg - FHalfSector) / (HalfUseDeg - FHalfSector))
  else
    Result := 0.0;
end;

function TModel.Degrees: TIntArray;
var
  I: Integer;
begin
  SetLength(Result, Length(FPatches));
  for I := 0 to High(FPatches) do
    Result[I] := FPatches[I].Degree;
end;

function TModel.EstimateDegree(const Xs, Ys: TDoubleArray): TDegreeChoice;
var
  N, Deg, DMax, P, A, C, NN, I: Integer;
  Degs: TIntArray;
  Rmses: TDoubleArray;
  Best: Double;
  BestDeg: Integer;
  AMat: TMatrix;
  Coefs, T, B: TDoubleArray;
  YRef, YC, SSE, Lim, RmseSel: Double;
  Gram: TMatrix;
  Rhs: TDoubleArray;
  PVal: Double;
begin
  N := Length(Xs);
  if N < 5 then
  begin
    Result.Deg := FOpt.DegMin;
    Result.RmseSel := 0;
    Result.RmseBest := 0;
    Exit;
  end;

  SetLength(Degs, 0);
  SetLength(Rmses, 0);
  BestDeg := FOpt.DegMin;
  Best := 1e308;

  if FOpt.CoordMode = 'raw' then
  begin
    { Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1]. }
    Deg := FOpt.DegMin;
    while Deg <= FOpt.DegMax do
    begin
      SetLength(AMat, N);
      for I := 0 to N - 1 do
      begin
        SetLength(AMat[I], Deg + 1);
        PVal := 1.0;
        for A := 0 to Deg do
        begin
          AMat[I][Deg - A] := PVal;
          PVal := PVal * Xs[I];
        end;
      end;
      Coefs := LstSqQR(AMat, Ys);
      SSE := 0;
      for I := 0 to N - 1 do
      begin
        PVal := Polyval(Coefs, Xs[I]) - Ys[I];
        SSE := SSE + PVal * PVal;
      end;
      SetLength(Degs, Length(Degs) + 1);
      Degs[High(Degs)] := Deg;
      SetLength(Rmses, Length(Rmses) + 1);
      Rmses[High(Rmses)] := Sqrt(SSE / N);
      if Rmses[High(Rmses)] < Best then
      begin
        Best := Rmses[High(Rmses)];
        BestDeg := Deg;
      end;
      Deg := Deg + 2;
    end;
  end
  else
  begin
    DMax := FOpt.DegMax;
    P := DMax + 1;
    YRef := 0;
    for I := 0 to N - 1 do YRef := YRef + Ys[I];
    YRef := YRef / N;
    SetLength(Gram, P);
    for A := 0 to P - 1 do
    begin
      SetLength(Gram[A], P);
      for C := 0 to P - 1 do Gram[A][C] := 0;
    end;
    SetLength(Rhs, P);
    for A := 0 to P - 1 do Rhs[A] := 0;

    for I := 0 to N - 1 do
    begin
      T := ChebRow(Xs[I], DMax);
      YC := Ys[I] - YRef;
      for A := 0 to P - 1 do
      begin
        Rhs[A] := Rhs[A] + T[A] * YC;
        for C := A to P - 1 do
          Gram[A][C] := Gram[A][C] + T[A] * T[C];
      end;
    end;
    for A := 0 to P - 1 do
      for C := A + 1 to P - 1 do
        Gram[C][A] := Gram[A][C];

    Deg := FOpt.DegMin;
    while Deg <= DMax do
    begin
      NN := Deg + 1;
      SetLength(AMat, NN);
      SetLength(B, NN);
      for A := 0 to NN - 1 do
      begin
        SetLength(AMat[A], NN);
        for C := 0 to NN - 1 do AMat[A][C] := Gram[A][C];
        B[A] := Rhs[A];
      end;
      Coefs := LstSqQR(AMat, B);
      SSE := 0;
      for I := 0 to N - 1 do
      begin
        PVal := ChebSum(Coefs, Deg, Xs[I]) - (Ys[I] - YRef);
        SSE := SSE + PVal * PVal;
      end;
      SetLength(Degs, Length(Degs) + 1);
      Degs[High(Degs)] := Deg;
      SetLength(Rmses, Length(Rmses) + 1);
      Rmses[High(Rmses)] := Sqrt(SSE / N);
      if Rmses[High(Rmses)] < Best then
      begin
        Best := Rmses[High(Rmses)];
        BestDeg := Deg;
      end;
      Deg := Deg + 2;
    end;
  end;

  Lim := Best * (1.0 + FOpt.DegElbowTol);
  Result.Deg := BestDeg;
  RmseSel := Best;
  for I := 0 to High(Degs) do
    if Rmses[I] <= Lim then
    begin
      Result.Deg := Degs[I];
      RmseSel := Rmses[I];
      Break;
    end;
  Result.RmseSel := RmseSel;
  Result.RmseBest := Best;
end;

function TModel.WindowOf(const Angles, Radii: TDoubleArray; Center: Double;
  out Xs, Ys: TDoubleArray): Integer;
var
  I, K: Integer;
  Half, DX: Double;
  Norm: Boolean;
  Shift: array[0..2] of Double;
  S: Integer;
begin
  Half := HalfTrain;
  Norm := FOpt.CoordMode <> 'raw';
  Shift[0] := -360.0; Shift[1] := 0.0; Shift[2] := 360.0;
  SetLength(Xs, Length(Angles) * 3);
  SetLength(Ys, Length(Angles) * 3);
  K := 0;
  for S := 0 to 2 do
    for I := 0 to High(Angles) do
    begin
      DX := Angles[I] + Shift[S] - Center;
      if (DX >= -Half) and (DX <= Half) then
      begin
        if Norm then Xs[K] := DX / Half else Xs[K] := DX;
        Ys[K] := Radii[I];
        Inc(K);
      end;
    end;
  SetLength(Xs, K);
  SetLength(Ys, K);
  Result := K;
end;

{ Метрики и статистика патча по его обучающему окну (полный базис). }
function TModel.BuildPatch(C: Double; Deg: Integer; const Xs, Ys, PolyCoef
  : TDoubleArray; const KeptOffsets, KeptCoefs: TDoubleArray;
  const Est: TDegreeChoice; const Angles, Radii: TDoubleArray): TPatch;
var
  N, I, J, K: Integer;
  V, E, SSE, SAE, MX, MF, MY, COV, VF, VY, CORR, HalfTrain_: Double;
  FitVals, Sec: TDoubleArray;
  Amp, MeanSec: Double;
begin
  N := Length(Xs);
  HalfTrain_ := HalfTrain;
  SSE := 0; SAE := 0; MX := 0;
  SetLength(FitVals, N);
  for I := 0 to N - 1 do
  begin
    V := Polyval(PolyCoef, Xs[I]);
    for J := 0 to High(KeptOffsets) do
      V := V + KeptCoefs[J] * PitShapeDeg(Abs(Xs[I] * HalfTrain_ - KeptOffsets[J]));
    FitVals[I] := V;
    E := V - Ys[I];
    SSE := SSE + E * E;
    SAE := SAE + Abs(E);
    if Abs(E) > MX then MX := Abs(E);
  end;
  MF := 0; MY := 0;
  for I := 0 to N - 1 do
  begin
    MF := MF + FitVals[I];
    MY := MY + Ys[I];
  end;
  MF := MF / N; MY := MY / N;
  COV := 0; VF := 0; VY := 0;
  for I := 0 to N - 1 do
  begin
    COV := COV + (FitVals[I] - MF) * (Ys[I] - MY);
    VF := VF + (FitVals[I] - MF) * (FitVals[I] - MF);
    VY := VY + (Ys[I] - MY) * (Ys[I] - MY);
  end;
  if (VF > 0) and (VY > 0) then CORR := COV / Sqrt(VF * VY) else CORR := 0;

  { Справочные метрики сектора: P95 − P5 и среднее по точкам сектора. }
  SetLength(Sec, Length(Angles));
  K := 0;
  for I := 0 to High(Angles) do
    if CircDist(Angles[I], C) <= FHalfSector then
    begin
      Sec[K] := Radii[I];
      Inc(K);
    end;
  SetLength(Sec, K);
  Amp := 0; MeanSec := 0;
  if Length(Sec) >= 5 then
  begin
    Amp := PercentileLinear(Sec, 95.0) - PercentileLinear(Sec, 5.0);
    for I := 0 to High(Sec) do MeanSec := MeanSec + Sec[I];
    MeanSec := MeanSec / Length(Sec);
  end;

  Result.CenterDeg := C;
  Result.Degree := Deg;
  Result.NPoints := N;
  Result.Coefs := PolyCoef;
  Result.PitOffsetsDeg := KeptOffsets;
  Result.PitCoefs := KeptCoefs;
  Result.Metrics.AmplitudeMm := Amp;
  Result.Metrics.MeanRadiusMm := MeanSec;
  if MeanSec > 0 then Result.Metrics.AmplitudeNorm := Amp / MeanSec
  else Result.Metrics.AmplitudeNorm := 0;
  Result.Metrics.DegElbowTol := FOpt.DegElbowTol;
  Result.Metrics.RmseSelectedMm := Est.RmseSel;
  Result.Metrics.RmseBestMm := Est.RmseBest;
  Result.Metrics.NTrainPoints := N;
  Result.Stats.RmseMm := Sqrt(SSE / N);
  Result.Stats.MaeMm := SAE / N;
  Result.Stats.MaxErrMm := MX;
  Result.Stats.Correlation := CORR;
end;

procedure TModel.Fit(const Angles, Radii: TDoubleArray);
var
  I, J, P, N, Deg, NCol, K: Integer;
  Sector, C, HalfTrain_, MaxAbs, DDeg, X: Double;
  Centers, Offs, Xs, Ys, PolyCoef: TDoubleArray;
  Est: TDegreeChoice;
  AMat: TMatrix;
  Coefs: TDoubleArray;
  KeptOffsets, KeptCoefs: TDoubleArray;
  Patch: TPatch;
begin
  if Length(Angles) <> Length(Radii) then
    raise Exception.Create('fit: длины не совпадают');
  if Length(Angles) < 10 then
    raise Exception.Create('fit: слишком мало точек');

  Sector := 360.0 / FOpt.NPatches;
  FHalfSector := Sector / 2;
  SetLength(Centers, FOpt.NPatches);
  for I := 0 to FOpt.NPatches - 1 do
  begin
    C := FMod(I * Sector + FHalfSector + FOpt.PhaseDeg, 360.0);
    if C < 0 then C := C + 360.0;
    Centers[I] := C;
  end;
  HalfTrain_ := HalfTrain;
  SetLength(FPatches, 0);

  for I := 0 to High(Centers) do
  begin
    C := Centers[I];
    N := WindowOf(Angles, Radii, C, Xs, Ys);
    if N < 5 then Continue;
    Est := EstimateDegree(Xs, Ys);
    Deg := Est.Deg;

    Offs := PitOffsets(C, HalfTrain_);
    NCol := Deg + 1 + Length(Offs);
    SetLength(AMat, N);
    for P := 0 to N - 1 do
    begin
      SetLength(AMat[P], NCol);
      X := 1.0;
      for K := Deg downto 0 do
      begin
        AMat[P][K] := X;
        X := X * Xs[P];
      end;
      for J := 0 to High(Offs) do
        AMat[P][Deg + 1 + J] := PitShapeDeg(Abs(Xs[P] * HalfTrain_ - Offs[J]));
    end;
    Coefs := LstSqQR(AMat, Ys);
    SetLength(PolyCoef, Deg + 1);
    for K := 0 to Deg do PolyCoef[K] := Coefs[K];

    { Отсечка ям, которые в окне патча «не видны» (PitMinAmp). }
    SetLength(KeptOffsets, Length(Offs));
    SetLength(KeptCoefs, Length(Offs));
    K := 0;
    for J := 0 to High(Offs) do
    begin
      MaxAbs := 0;
      for P := 0 to N - 1 do
      begin
        DDeg := Abs(Xs[P] * HalfTrain_ - Offs[J]);
        if Abs(Coefs[Deg + 1 + J] * PitShapeDeg(DDeg)) > MaxAbs then
          MaxAbs := Abs(Coefs[Deg + 1 + J] * PitShapeDeg(DDeg));
      end;
      if MaxAbs >= FPit.PitMinAmp then
      begin
        KeptOffsets[K] := Offs[J];
        KeptCoefs[K] := Coefs[Deg + 1 + J];
        Inc(K);
      end;
    end;
    SetLength(KeptOffsets, K);
    SetLength(KeptCoefs, K);

    Patch := BuildPatch(C, Deg, Xs, Ys, PolyCoef, KeptOffsets, KeptCoefs, Est, Angles, Radii);
    SetLength(FPatches, Length(FPatches) + 1);
    FPatches[High(FPatches)] := Patch;
  end;
  FFitted := True;
end;

function TModel.EvalPart(const Angles: TDoubleArray; const Part: string): TDoubleArray;
var
  I, J, K: Integer;
  A, W, DX, X, V, SumWV, SumW, HalfUse_, HalfTrain_: Double;
  Raw: Boolean;
begin
  if not FFitted then
    raise Exception.Create('Сначала вызовите fit()');
  HalfUse_ := HalfUse;
  HalfTrain_ := HalfTrain;
  Raw := FOpt.CoordMode = 'raw';
  SetLength(Result, Length(Angles));
  for K := 0 to High(Angles) do
  begin
    A := Angles[K];
    SumWV := 0; SumW := 0;
    for I := 0 to High(FPatches) do
    begin
      W := Weight(CircDist(A, FPatches[I].CenterDeg), HalfUse_);
      if W <= 0 then Continue;
      DX := CircLocal(A, FPatches[I].CenterDeg);
      if Raw then X := DX else X := DX / HalfTrain_;
      V := 0;
      if Part <> 'pit' then V := V + Polyval(FPatches[I].Coefs, X);
      if Part <> 'poly' then
        for J := 0 to High(FPatches[I].PitOffsetsDeg) do
          V := V + FPatches[I].PitCoefs[J] *
            PitShapeDeg(Abs(X * HalfTrain_ - FPatches[I].PitOffsetsDeg[J]));
      SumWV := SumWV + W * V;
      SumW := SumW + W;
    end;
    if SumW > 0 then Result[K] := SumWV / SumW else Result[K] := 0;
  end;
end;

function TModel.Eval(const Angles: TDoubleArray): TDoubleArray;
begin
  Result := EvalPart(Angles, 'total');
end;

end.

