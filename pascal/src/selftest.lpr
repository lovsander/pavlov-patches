program selftest;
{ Самопроверка Free Pascal порта: конформанс-векторы + дымовой тест пайплайна.
  Запуск: selftest.exe [каталог с векторами]
  Код возврата: 0 — всё прошло, 1 — расхождения. }
{$mode objfpc}{$H+}

uses
  SysUtils, Classes, pappa_signal, pappa_json, pappa_model, pappa_csv,
  pappa_document, pappa_conformance;

var
  Dir: string;
  Vectors: TVectorArray;
  I, Failures, N: Integer;
  R: TOutcome;
  M: TModel;
  Angles, Radii, Curve: TDoubleArray;
  CsvText, TmpPath: string;
  Rows: TRowArray;
  MaxErr: Double;

procedure Check(Ok: Boolean; const What: string);
begin
  if Ok then WriteLn('  [ok] ' + What) else WriteLn('  [FAIL] ' + What);
  if not Ok then Inc(Failures);
end;

begin
  Failures := 0;
  if ParamCount >= 1 then Dir := ParamStr(1) else Dir := '../spec/conformance/vectors';
  WriteLn('Free Pascal SelfTest: ' + Dir);

  Vectors := LoadVectors(Dir);
  WriteLn(Format('векторы конформанса (%d):', [Length(Vectors)]));
  Check(Length(Vectors) >= 4, 'не меньше 4 векторов');
  for I := 0 to High(Vectors) do
  begin
    R := CheckVector(Vectors[I].Data);
    Check(R.Ok, Vectors[I].FileName + ' — ' + R.Detail);
  end;

  WriteLn('дымовой тест пайплайна (гладкая синусоида, 360 точек):');
  CsvText := 'section_id,height_mm,angle_deg,radius_mm' + #10;
  for N := 0 to 359 do
    CsvText := CsvText + Format('0,0,%d,%.6f', [N, 50 + 0.4 * Sin(N * Pi / 180)]) + #10;
  TmpPath := IncludeTrailingPathDelimiter(GetTempDir) + 'pappa_fpc_smoke.csv';
  WriteTextFile(TmpPath, CsvText);

  Rows := LoadCsv(TmpPath);
  DeleteFile(TmpPath);
  Check(Length(Rows) = 360, 'разбор CSV: 360 точек');

  SetLength(Angles, Length(Rows));
  SetLength(Radii, Length(Rows));
  for I := 0 to High(Rows) do
  begin
    Angles[I] := Rows[I].AngleDeg;
    Radii[I] := Rows[I].RadiusMm;
  end;
  M := TModel.Create(DefaultModelOptions, nil);
  try
    M.Fit(Angles, Radii);
    Check(Length(M.Patches) = 7, Format('патчей %d', [Length(M.Patches)]));
    Curve := M.Eval(Angles);
    MaxErr := 0;
    for I := 0 to High(Radii) do
      if Abs(Curve[I] - Radii[I]) > MaxErr then MaxErr := Abs(Curve[I] - Radii[I]);
    Check(MaxErr < 1e-6, Format('контур гладкой синусоиды: max|Δ| = %.2e мм', [MaxErr]));
  finally
    M.Free;
  end;

  if Failures = 0 then WriteLn('ВЫВОД: SelfTest пройден')
  else WriteLn(Format('ВЫВОД: провалов %d', [Failures]));
  Halt(Failures);
end.
