program conformance;
{ Проверка Free Pascal порта PAPPA по конформанс-векторам.
  Запуск: conformance.exe [каталог с векторами]
  Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога. }
{$mode objfpc}{$H+}

uses
  SysUtils, Classes, pappa_signal, pappa_json, pappa_conformance;

var
  Dir, Line: string;
  Vectors: TVectorArray;
  I, J, Bad: Integer;
  R: TOutcome;
begin
  if ParamCount >= 1 then Dir := ParamStr(1) else Dir := '../spec/conformance/vectors';
  try
    Vectors := LoadVectors(Dir);
  except
    on E: Exception do
    begin
      WriteLn(E.Message);
      Halt(2);
    end;
  end;

  WriteLn(Format('Free Pascal порт PAPPA: %d векторов (FPC %s)',
    [Length(Vectors), {$I %FPCVERSION%}]));

  Bad := 0;
  for I := 0 to High(Vectors) do
  begin
    R := CheckVector(Vectors[I].Data);
    if not R.Ok then Inc(Bad);
    Line := Vectors[I].FileName;
    while Length(Line) < 46 do Line := Line + ' ';
    if R.Ok then Line := Line + 'OK    ' else Line := Line + 'FAIL  ';
    WriteLn(Line + R.Detail);
    for J := 0 to High(R.Notes) do
      WriteLn(StringOfChar(' ', 52) + '-> ' + R.Notes[J]);
  end;

  if Bad = 0 then
    WriteLn('ВЫВОД: Free Pascal порт проходит все векторы')
  else
    WriteLn(Format('ВЫВОД: расхождений %d', [Bad]));
  Halt(Bad);
end.
