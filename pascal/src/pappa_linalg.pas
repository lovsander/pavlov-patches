unit pappa_linalg;
{ Линейная алгебра: МНК через QR отражениями Хаусхолдера (как np.polyfit /
  np.linalg.lstsq) + базис Чебышёва для быстрого выбора степени. }
{$mode objfpc}{$H+}

interface

uses
  SysUtils, Math,
  pappa_signal;

type
  TMatrix = array of TDoubleArray;

function LstSqQR(const AIn: TMatrix; const BIn: TDoubleArray): TDoubleArray;
function Polyval(const Coefs: TDoubleArray; X: Double): Double;
function Polyfit(const Xs, Ys: TDoubleArray; Deg: Integer): TDoubleArray;
function ChebRow(X: Double; DegMax: Integer): TDoubleArray;
function ChebSum(const C: TDoubleArray; Deg: Integer; X: Double): Double;

implementation

function LstSqQR(const AIn: TMatrix; const BIn: TDoubleArray): TDoubleArray;
var
  M, N, I, J, K: Integer;
  A: TMatrix;
  B, V: TDoubleArray;
  Norm, Alpha, VNorm2, S, C, Cb, Sb, D: Double;
begin
  M := Length(AIn);
  if M = 0 then raise Exception.Create('lstsq: пустая матрица');
  N := Length(AIn[0]);
  if Length(BIn) <> M then raise Exception.Create('lstsq: длины A и b не совпадают');
  if M < N then raise Exception.Create('lstsq: нужно m >= n');

  SetLength(A, M);
  for I := 0 to M - 1 do A[I] := Copy(AIn[I]);
  B := Copy(BIn);

  for K := 0 to N - 1 do
  begin
    Norm := 0;
    for I := K to M - 1 do Norm := Norm + A[I][K] * A[I][K];
    Norm := Sqrt(Norm);
    if Norm < 1e-300 then Continue;

    if A[K][K] > 0 then Alpha := -Norm else Alpha := Norm;
    SetLength(V, M);
    for I := K to M - 1 do V[I] := A[I][K];
    V[K] := V[K] - Alpha;
    VNorm2 := 0;
    for I := K to M - 1 do VNorm2 := VNorm2 + V[I] * V[I];
    if VNorm2 < 1e-300 then Continue;

    for J := K to N - 1 do
    begin
      S := 0;
      for I := K to M - 1 do S := S + V[I] * A[I][J];
      C := 2 * S / VNorm2;
      for I := K to M - 1 do A[I][J] := A[I][J] - C * V[I];
    end;
    Sb := 0;
    for I := K to M - 1 do Sb := Sb + V[I] * B[I];
    Cb := 2 * Sb / VNorm2;
    for I := K to M - 1 do B[I] := B[I] - Cb * V[I];
  end;

  SetLength(Result, N);
  for I := N - 1 downto 0 do
  begin
    S := B[I];
    for J := I + 1 to N - 1 do S := S - A[I][J] * Result[J];
    D := A[I][I];
    if Abs(D) < 1e-300 then raise Exception.Create('lstsq: вырожденная система');
    Result[I] := S / D;
  end;
end;

function Polyval(const Coefs: TDoubleArray; X: Double): Double;
var
  I: Integer;
begin
  Result := 0;
  for I := 0 to High(Coefs) do
    Result := Result * X + Coefs[I];
end;

function Polyfit(const Xs, Ys: TDoubleArray; Deg: Integer): TDoubleArray;
var
  M, N, I, J: Integer;
  A: TMatrix;
  P: Double;
begin
  M := Length(Xs);
  N := Deg + 1;
  SetLength(A, M);
  for I := 0 to M - 1 do
  begin
    SetLength(A[I], N);
    P := 1;
    for J := 0 to N - 1 do
    begin
      A[I][N - 1 - J] := P;
      P := P * Xs[I];
    end;
  end;
  Result := LstSqQR(A, Ys);
end;

function ChebRow(X: Double; DegMax: Integer): TDoubleArray;
var
  K: Integer;
begin
  SetLength(Result, DegMax + 1);
  Result[0] := 1;
  if DegMax >= 1 then Result[1] := X;
  for K := 2 to DegMax do
    Result[K] := 2 * X * Result[K - 1] - Result[K - 2];
end;

function ChebSum(const C: TDoubleArray; Deg: Integer; X: Double): Double;
var
  K: Integer;
  B0, B1, B2: Double;
begin
  B1 := 0; B2 := 0;
  for K := Deg downto 1 do
  begin
    B0 := 2 * X * B1 - B2 + C[K];
    B2 := B1;
    B1 := B0;
  end;
  Result := X * B1 - B2 + C[0];
end;

end.
