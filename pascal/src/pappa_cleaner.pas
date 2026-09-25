unit pappa_cleaner;
{ Авто-очистка выбросов (метод "iqr"): снимаем форму профиля медианным фильтром
  по кольцу, считаем остаток и его робастный масштаб; порог — усы Тьюки.
  Повторяет AutoOutlierCleaner (python/pappa/core/outlier_cleaner.py). }
{$mode objfpc}{$H+}

interface

uses
  Math, pappa_signal;

type
  TCleanerOptions = record
    BaselineDeg: Double;
    IqrK: Double;
    MaxRemovedFrac: Double;
    MinPoints: Integer;
  end;

  TCleanResult = record
    Mask: array of Boolean;
    NOutliers: Integer;
    Window: Integer;
  end;

function DefaultCleanerOptions: TCleanerOptions;
function CleanIQR(const Angles, Radii: TDoubleArray; const O: TCleanerOptions): TCleanResult;

implementation

function DefaultCleanerOptions: TCleanerOptions;
begin
  Result.BaselineDeg := 1.0;
  Result.IqrK := 3.0;
  Result.MaxRemovedFrac := 0.5;
  Result.MinPoints := 20;
end;

function CleanIQR(const Angles, Radii: TDoubleArray; const O: TCleanerOptions): TCleanResult;
var
  N, I, W, Cap, Flagged, K: Integer;
  Base, Res, Sev, Kept: TDoubleArray;
  Center, Spread, Denom, Level: Double;
begin
  N := Length(Radii);
  SetLength(Result.Mask, N);
  for I := 0 to N - 1 do Result.Mask[I] := False;
  Result.NOutliers := 0;
  Result.Window := 0;
  if N < O.MinPoints then Exit;

  W := WindowPoints(Angles, O.BaselineDeg);
  Base := MedianFilterWrap(Radii, W);
  SetLength(Res, N);
  for I := 0 to N - 1 do Res[I] := Radii[I] - Base[I];

  Center := Median(Res);
  Spread := IQR(Res);
  if Spread > 1e-12 then Denom := Spread else Denom := 1.0;  { защита референса }

  SetLength(Sev, N);
  Flagged := 0;
  for I := 0 to N - 1 do
  begin
    Sev[I] := Abs(Res[I] - Center) / Denom;
    Result.Mask[I] := Sev[I] > O.IqrK;
    if Result.Mask[I] then Inc(Flagged);
  end;

  { Предохранитель: не выбрасываем больше MaxRemovedFrac точек. }
  Cap := Trunc(Floor(O.MaxRemovedFrac * N));
  if (Cap > 0) and (Cap < N) and (Flagged > Cap) then
  begin
    SetLength(Kept, Flagged);
    K := 0;
    for I := 0 to N - 1 do
      if Result.Mask[I] then
      begin
        Kept[K] := Sev[I]; Inc(K);
      end;
    Kept := SortDoubles(Kept);
    Level := Kept[Length(Kept) - Cap];
    Flagged := 0;
    for I := 0 to N - 1 do
    begin
      Result.Mask[I] := Result.Mask[I] and (Sev[I] >= Level);
      if Result.Mask[I] then Inc(Flagged);
    end;
  end;
  Result.NOutliers := Flagged;
  Result.Window := W;
end;

end.
