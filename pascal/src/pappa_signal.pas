unit pappa_signal;
{ Сигнальные утилиты — поведение как у numpy и как в остальных портах:
  медиана (чётное n — среднее двух центральных), перцентиль с линейной
  интерполяцией, MAD/робастная sigma, IQR, окна по кольцу. }
{$mode objfpc}{$H+}

interface

uses
  Math;

type
  TDoubleArray = array of Double;
  TIntArray = array of Integer;
  TStrArray = array of string;

function SortDoubles(const V: TDoubleArray): TDoubleArray;
function Median(const V: TDoubleArray): Double;
function PercentileLinear(const V: TDoubleArray; Q: Double): Double;
function IQR(const V: TDoubleArray): Double;
function MAD(const V: TDoubleArray): Double;
function RobustSigma(const V: TDoubleArray): Double;
function AngularStep(const Angles: TDoubleArray): Double;
function WindowPoints(const Angles: TDoubleArray; SpanDeg: Double): Integer;
function MedianFilterWrap(const X: TDoubleArray; Window: Integer): TDoubleArray;
function SmoothWrap(const X: TDoubleArray; Window: Integer): TDoubleArray;
function CircDist(A, B: Double): Double;
function CircLocal(A, B: Double): Double;
function SmoothStep(T: Double): Double;
{ Округление «половина к чётному» — как Python round() и math.RoundToEven в Go. }
function RoundTiesEven(X: Double): Int64;

implementation

{ Быстрая сортировка (итеративная, с медианой из трёх как опорной) — без обобщений. }
procedure QuickSort(var A: TDoubleArray; L, R: Integer);
var
  I, J: Integer;
  Piv, T: Double;
begin
  while L < R do
  begin
    I := L; J := R;
    Piv := A[L + (R - L) div 2];
    repeat
      while A[I] < Piv do Inc(I);
      while A[J] > Piv do Dec(J);
      if I <= J then
      begin
        T := A[I]; A[I] := A[J]; A[J] := T;
        Inc(I); Dec(J);
      end;
    until I > J;
    if (J - L) < (R - I) then
    begin
      if L < J then QuickSort(A, L, J);
      L := I;
    end
    else
    begin
      if I < R then QuickSort(A, I, R);
      R := J;
    end;
  end;
end;

function SortDoubles(const V: TDoubleArray): TDoubleArray;
begin
  Result := Copy(V);
  if Length(Result) > 1 then
    QuickSort(Result, 0, High(Result));
end;

function Median(const V: TDoubleArray): Double;
var
  N: Integer;
  S: TDoubleArray;
begin
  N := Length(V);
  if N = 0 then Exit(0.0);
  S := SortDoubles(V);
  if Odd(N) then
    Result := S[N div 2]
  else
    Result := 0.5 * (S[N div 2 - 1] + S[N div 2]);
end;

function PercentileLinear(const V: TDoubleArray; Q: Double): Double;
var
  N, Lo, Hi: Integer;
  S: TDoubleArray;
  Pos, Frac: Double;
begin
  N := Length(V);
  if N = 0 then Exit(0.0);
  S := SortDoubles(V);
  Pos := (Q / 100.0) * (N - 1);
  Lo := Floor(Pos);
  Frac := Pos - Lo;
  Hi := Lo + 1;
  if Hi > N - 1 then Hi := N - 1;
  Result := S[Lo] + Frac * (S[Hi] - S[Lo]);
end;

function IQR(const V: TDoubleArray): Double;
begin
  if Length(V) = 0 then Exit(0.0);
  Result := PercentileLinear(V, 75.0) - PercentileLinear(V, 25.0);
end;

function MAD(const V: TDoubleArray): Double;
var
  I: Integer;
  M: Double;
  D: TDoubleArray;
begin
  if Length(V) = 0 then Exit(0.0);
  M := Median(V);
  SetLength(D, Length(V));
  for I := 0 to High(V) do
    D[I] := Abs(V[I] - M);
  Result := Median(D);
end;

function RobustSigma(const V: TDoubleArray): Double;
begin
  Result := 1.4826 * MAD(V);
end;

function AngularStep(const Angles: TDoubleArray): Double;
var
  I, K: Integer;
  D: TDoubleArray;
  S: Double;
begin
  if Length(Angles) < 2 then Exit(1.0);
  SetLength(D, Length(Angles) - 1);
  K := 0;
  for I := 1 to High(Angles) do
  begin
    S := Angles[I] - Angles[I - 1];
    if S > 0 then
    begin
      D[K] := S; Inc(K);
    end;
  end;
  if K = 0 then Exit(1.0);
  SetLength(D, K);
  Result := Median(D);
end;

function WindowPoints(const Angles: TDoubleArray; SpanDeg: Double): Integer;
var
  N, W: Int64;
begin
  N := Length(Angles);
  if N < 3 then Exit(Int64(1) * N);
  W := RoundTiesEven(SpanDeg / AngularStep(Angles));
  if (W mod 2) = 0 then Inc(W);
  if W < 3 then W := 3;
  if W > N then
    if Odd(N) then W := N else W := N - 1;
  if W < 3 then W := 3;
  Result := W;
end;

function OddWindow(Window, N: Integer): Integer;
begin
  Result := Window;
  if (Result mod 2) = 0 then Inc(Result);
  if Result < 3 then Result := 3;
  if Result > N then
    if Odd(N) then Result := N else Result := N - 1;
end;

function WrapIndex(I, N: Integer): Integer;
begin
  Result := ((I mod N) + N) mod N;
end;

function MedianFilterWrap(const X: TDoubleArray; Window: Integer): TDoubleArray;
var
  N, W, H, I, K: Integer;
  Win: TDoubleArray;
begin
  N := Length(X);
  W := OddWindow(Window, N);
  SetLength(Result, N);
  if (W < 3) or (N < 3) then
  begin
    for I := 0 to N - 1 do Result[I] := Median(X);
    Exit;
  end;
  H := (W - 1) div 2;
  SetLength(Win, W);
  for I := 0 to N - 1 do
  begin
    for K := 0 to W - 1 do
      Win[K] := X[WrapIndex(I - H + K, N)];
    Result[I] := Median(Win);
  end;
end;

function SmoothWrap(const X: TDoubleArray; Window: Integer): TDoubleArray;
var
  N, W, H, I, K: Integer;
  S: Double;
begin
  N := Length(X);
  W := OddWindow(Window, N);
  SetLength(Result, N);
  if (W < 3) or (N < 3) then
  begin
    Result := Copy(X);
    Exit;
  end;
  H := (W - 1) div 2;
  for I := 0 to N - 1 do
  begin
    S := 0;
    for K := -H to H do
      S := S + X[WrapIndex(I + K, N)];
    Result[I] := S / W;
  end;
end;

function CircDist(A, B: Double): Double;
var
  D: Double;
begin
  D := FMod(A - B + 180.0, 360.0);
  if D < 0 then D := D + 360.0;
  Result := Abs(D - 180.0);
end;

function CircLocal(A, B: Double): Double;
var
  D: Double;
begin
  D := FMod(A - B + 180.0, 360.0);
  if D < 0 then D := D + 360.0;
  Result := D - 180.0;
end;

function SmoothStep(T: Double): Double;
begin
  if T < 0 then Exit(0.0);
  if T > 1 then Exit(1.0);
  Result := T * T * (3.0 - 2.0 * T);
end;

function RoundTiesEven(X: Double): Int64;
var
  F: Double;
  L: Int64;
begin
  F := Floor(X);
  L := Trunc(F);
  if (X - F) > 0.5 then
    Result := L + 1
  else if (X - F) < 0.5 then
    Result := L
  else
    Result := L + (L and 1);   { ровно половина -> к чётному }
end;

end.
