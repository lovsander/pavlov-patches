unit pappa_detector;
{ Детектор ям (трещин) — повторение python/pappa/analysis/zones.py:
    band = |узкая медиана (1°) − широкая медиана (10°)|, сглаженная (2°),
    нормированная на свою робастную sigma (безразмерный индикатор в «MAD-ах»);
    зоны = участки, где индикатор > k, длиной не короче min_zone_deg. }
{$mode objfpc}{$H+}

interface

uses
  pappa_signal;

type
  TDetectorOptions = record
    WindowDeg: Double;
    WideDeg: Double;
    SmoothDeg: Double;
    K: Double;
    MinZoneDeg: Double;
  end;

  TZone = record
    Lo, Hi: Double;
  end;

  TZoneArray = array of TZone;

function DefaultDetectorOptions: TDetectorOptions;
function BandIndicator(const Angles, Radii: TDoubleArray; const O: TDetectorOptions): TDoubleArray;
function MaskToZones(const Angles: TDoubleArray; const Mask: array of Boolean;
  const O: TDetectorOptions): TZoneArray;
function Zones(const Angles, Values: TDoubleArray; const O: TDetectorOptions): TZoneArray;
function Pits(const Angles, Radii: TDoubleArray; const O: TDetectorOptions): TDoubleArray;

implementation

function DefaultDetectorOptions: TDetectorOptions;
begin
  Result.WindowDeg := 1.0;
  Result.WideDeg := 10.0;
  Result.SmoothDeg := 2.0;
  Result.K := 5.5;
  Result.MinZoneDeg := 2.0;
end;

function BandIndicator(const Angles, Radii: TDoubleArray; const O: TDetectorOptions): TDoubleArray;
var
  N, I: Integer;
  Narrow, Wide, Band: TDoubleArray;
  S: Double;
begin
  N := Length(Radii);
  Narrow := MedianFilterWrap(Radii, WindowPoints(Angles, O.WindowDeg));
  Wide := MedianFilterWrap(Radii, WindowPoints(Angles, O.WideDeg));
  SetLength(Band, N);
  for I := 0 to N - 1 do Band[I] := Abs(Narrow[I] - Wide[I]);

  Result := SmoothWrap(Band, WindowPoints(Angles, O.SmoothDeg));
  S := RobustSigma(Result);
  if S > 1e-12 then
    for I := 0 to N - 1 do Result[I] := Result[I] / S
  else
    for I := 0 to N - 1 do Result[I] := 0.0;
end;

function MaskToZones(const Angles: TDoubleArray; const Mask: array of Boolean;
  const O: TDetectorOptions): TZoneArray;
var
  N, I, J, Count, Out: Integer;
  Any: Boolean;
  Diffs: TDoubleArray;
  Z: TZoneArray;
  Step, FirstHi, LastLo: Double;
begin
  SetLength(Result, 0);
  N := Length(Angles);
  Any := False;
  for I := 0 to N - 1 do
    if Mask[I] then Any := True;
  if not Any then Exit;

  { шаг сетки: медиана разностей углов (или 1, если разностей нет) }
  SetLength(Diffs, N - 1);
  for I := 1 to N - 1 do Diffs[I - 1] := Angles[I] - Angles[I - 1];
  if Length(Diffs) = 0 then Step := 1.0 else Step := Median(Diffs);

  SetLength(Z, N);
  Count := 0;
  I := 0;
  while I < N do
  begin
    if not Mask[I] then
    begin
      Inc(I);
      Continue;
    end;
    J := I;
    while (J + 1 < N) and Mask[J + 1] do Inc(J);
    Z[Count].Lo := Angles[I] - Step / 2;
    Z[Count].Hi := Angles[J] + Step / 2;
    Inc(Count);
    I := J + 1;
  end;

  { Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона. }
  if (Count > 1) and Mask[0] and Mask[N - 1] then
  begin
    FirstHi := Z[0].Hi;
    LastLo := Z[Count - 1].Lo;
    { z1..z(k-2) сдвигаем влево, объединённую зону пишем в конец }
    for I := 1 to Count - 2 do
      Z[I - 1] := Z[I];
    Z[Count - 2].Lo := LastLo - 360.0;
    Z[Count - 2].Hi := FirstHi;
    Dec(Count);
  end;

  Out := 0;
  for I := 0 to Count - 1 do
    if (Z[I].Hi - Z[I].Lo) >= O.MinZoneDeg then
    begin
      Z[Out] := Z[I];
      Inc(Out);
    end;
  SetLength(Result, Out);
  for I := 0 to Out - 1 do
    Result[I] := Z[I];
end;

function Zones(const Angles, Values: TDoubleArray; const O: TDetectorOptions): TZoneArray;
var
  I: Integer;
  Mask: array of Boolean;
begin
  SetLength(Mask, Length(Values));
  for I := 0 to High(Values) do Mask[I] := Values[I] > O.K;
  Result := MaskToZones(Angles, Mask, O);
end;

function Pits(const Angles, Radii: TDoubleArray; const O: TDetectorOptions): TDoubleArray;
var
  Band: TDoubleArray;
  Z: TZoneArray;
  I: Integer;
begin
  Band := BandIndicator(Angles, Radii, O);
  Z := Zones(Angles, Band, O);
  SetLength(Result, Length(Z));
  for I := 0 to High(Z) do
    Result[I] := 0.5 * (Z[I].Lo + Z[I].Hi);
end;

end.
