program pappa;
{ Пайплайн PAPPA на Free Pascal: CSV с сечениями -> папка образца.
  Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
    <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
  Проверка: python python/studies/verify_port.py --cpp-dir <out-dir>
  Запуск: pappa.exe --input FILE.csv --out-dir DIR [--name NAME]
          [--description ТЕКСТ] [--no-pits] [--quiet] }
{$mode objfpc}{$H+}

uses
  SysUtils, Classes, pappa_signal, pappa_json, pappa_csv, pappa_document;

procedure Usage;
begin
  WriteLn('PAPPA (Free Pascal): --input FILE.csv --out-dir DIR [--name NAME] ' +
          '[--description ТЕКСТ] [--no-pits] [--quiet]');
end;

var
  Input, OutDir, Name, Description: string;
  Pits, Quiet: Boolean;
  I: Integer;
  Opt: TPipelineOptions;
  Rows: TRowArray;
  Sections: TSectionArray;
  Sample: TSampleOptions;
  Root: string;
begin
  Input := ''; OutDir := ''; Name := 'sample';
  Description := 'PAPPA Free Pascal port';
  Pits := True; Quiet := False;

  I := 1;
  while I <= ParamCount do
  begin
    if ParamStr(I) = '--input' then
    begin
      Inc(I);
      if I <= ParamCount then Input := ParamStr(I);
    end
    else if ParamStr(I) = '--out-dir' then
    begin
      Inc(I);
      if I <= ParamCount then OutDir := ParamStr(I);
    end
    else if ParamStr(I) = '--name' then
    begin
      Inc(I);
      if I <= ParamCount then Name := ParamStr(I);
    end
    else if ParamStr(I) = '--description' then
    begin
      Inc(I);
      if I <= ParamCount then Description := ParamStr(I);
    end
    else if ParamStr(I) = '--no-pits' then Pits := False
    else if ParamStr(I) = '--quiet' then Quiet := True
    else
    begin
      Usage;
      Halt(2);
    end;
    Inc(I);
  end;
  if (Input = '') or (OutDir = '') then
  begin
    Usage;
    Halt(2);
  end;

  try
    Rows := LoadCsv(Input);
    WriteLn(Format('PAPPA (Free Pascal): %d точек, вход %s', [Length(Rows), Input]));

    Opt := DefaultPipelineOptions;
    Opt.Pits := Pits;
    Opt.Verbose := not Quiet;
    Sections := ProcessSections(Rows, Opt);

    Sample := DefaultSampleOptions;
    Sample.InputCsv := Input;
    Sample.Pits := Pits;
    Sample.Description := Description;
    Sample.Cleaner := Opt.Cleaner;
    Sample.Detector := Opt.Detector;
    Root := SaveSample(OutDir, Name, Sections, Sample);

    WriteLn;
    WriteLn('Образец записан: ' + Root);
    WriteLn('  манифест: ' + IncludeTrailingPathDelimiter(Root) + 'sample.json');
    WriteLn(Format('  сечений:  %d (sections/*.pappa.json)', [Length(Sections)]));
    WriteLn;
    WriteLn('Сверка с референсом Python:');
    WriteLn('  python python/studies/verify_port.py --cpp-dir ' + Root);
  except
    on E: Exception do
    begin
      WriteLn(StdErr, 'Ошибка: ' + E.Message);
      Halt(1);
    end;
  end;
end.
