unit pappa_document;
{ Запись папки образца — тот же контракт, что у Python/C++/C/Go/JS/Java/Kotlin/Rust:
    <out_dir>/sample.json              манифест (format pappa-sample v1.0)
    <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
  Ключи и порядок повторяют cpp/sample_writer.cpp: папки от разных портов
  сравниваются численно (python/studies/verify_port.py). }
{$mode objfpc}{$H+}

interface

uses
  SysUtils, Classes, DateUtils,
  pappa_signal, pappa_json, pappa_cleaner, pappa_detector, pappa_model, pappa_csv;

const
  PORT_VERSION = '0.1.0';
  PORT_LANGUAGE = 'pascal';

type
  TSampleOptions = record
    InputCsv: string;
    Pits: Boolean;
    Description: string;
    Cleaner: TCleanerOptions;
    Detector: TDetectorOptions;
  end;

function DefaultSampleOptions: TSampleOptions;
function IsoUtcNow: string;
function SaveSectionDocument(const Path: string; Sec: TSectionModel): string;
function SaveSample(const OutDir, Name: string; const Sections: TSectionArray;
  const O: TSampleOptions): string;

implementation

type
  TWriter = class
  private
    FSB: string;
    FDepth: Integer;
  public
    function Ind: string;
    procedure ObjStart;
    procedure ObjEnd;
    procedure ArrStart;
    procedure ArrEnd;
    procedure Comma;
    procedure Key(const K: string);
    procedure StrVal(const S: string);
    procedure NumVal(V: Double);
    procedure IntVal(V: Integer);
    procedure BoolVal(V: Boolean);
    procedure Raw(const S: string);
    procedure KvStr(const K, V: string);
    procedure KvNum(const K: string; V: Double);
    procedure KvInt(const K: string; V: Integer);
    procedure KvBool(const K: string; V: Boolean);
    function Text: string;
  end;

function TWriter.Ind: string;
begin
  Result := StringOfChar(' ', FDepth * 2);
end;

procedure TWriter.ObjStart;
begin
  FSB := FSB + '{';
  Inc(FDepth);
  FSB := FSB + #10 + Ind;
end;

procedure TWriter.ObjEnd;
begin
  Dec(FDepth);
  FSB := FSB + #10 + Ind + '}';
end;

procedure TWriter.ArrStart;
begin
  FSB := FSB + '[';
  Inc(FDepth);
  FSB := FSB + #10 + Ind;
end;

procedure TWriter.ArrEnd;
begin
  Dec(FDepth);
  FSB := FSB + #10 + Ind + ']';
end;

procedure TWriter.Comma;
begin
  FSB := FSB + ',' + #10 + Ind;
end;

procedure TWriter.Key(const K: string);
begin
  FSB := FSB + Ind + '"' + K + '": ';
end;

procedure TWriter.StrVal(const S: string);
begin
  FSB := FSB + '"' + JsonEsc(S) + '"';
end;

procedure TWriter.NumVal(V: Double);
begin
  FSB := FSB + JsonNum(V);
end;

procedure TWriter.IntVal(V: Integer);
begin
  FSB := FSB + IntToStr(V);
end;

procedure TWriter.BoolVal(V: Boolean);
begin
  if V then FSB := FSB + 'true' else FSB := FSB + 'false';
end;

procedure TWriter.Raw(const S: string);
begin
  FSB := FSB + S;
end;

procedure TWriter.KvStr(const K, V: string);
begin
  Key(K); StrVal(V);
end;

procedure TWriter.KvNum(const K: string; V: Double);
begin
  Key(K); NumVal(V);
end;

procedure TWriter.KvInt(const K: string; V: Integer);
begin
  Key(K); IntVal(V);
end;

procedure TWriter.KvBool(const K: string; V: Boolean);
begin
  Key(K); BoolVal(V);
end;

function TWriter.Text: string;
begin
  Result := FSB;
end;

function DefaultSampleOptions: TSampleOptions;
begin
  Result.InputCsv := '';
  Result.Pits := True;
  Result.Description := 'PAPPA Free Pascal port';
  Result.Cleaner := DefaultCleanerOptions;
  Result.Detector := DefaultDetectorOptions;
end;

function IsoUtcNow: string;
var
  U: TDateTime;
begin
  U := LocalTimeToUniversal(Now);
  Result := FormatDateTime('yyyy-mm-dd', U) + 'T' +
            FormatDateTime('hh:nn:ss', U) + 'Z';
end;

procedure WritePatches(W: TWriter; M: TModel);
var
  I, J: Integer;
  P: TPatch;
begin
  W.Key('patches');
  W.ArrStart;
  for I := 0 to High(M.Patches) do
  begin
    P := M.Patches[I];
    if I > 0 then W.Raw(',' + #10 + W.Ind) else W.Raw(#10 + W.Ind);
    W.ObjStart;
    W.KvNum('center_deg', P.CenterDeg);   W.Comma;
    W.KvInt('degree', P.Degree);           W.Comma;
    W.KvInt('n_points', P.NPoints);        W.Comma;
    W.Key('coefs');
    W.ArrStart;
    for J := 0 to High(P.Coefs) do
    begin
      if J > 0 then W.Raw(', ');
      W.NumVal(P.Coefs[J]);
    end;
    W.ArrEnd;
    W.Comma;

    W.Key('metrics');
    W.ObjStart;
    W.KvNum('amplitude_mm', P.Metrics.AmplitudeMm);        W.Comma;
    W.KvNum('mean_radius_mm', P.Metrics.MeanRadiusMm);     W.Comma;
    W.KvNum('amplitude_norm', P.Metrics.AmplitudeNorm);    W.Comma;
    W.KvNum('deg_elbow_tol', P.Metrics.DegElbowTol);       W.Comma;
    W.KvNum('rmse_selected_mm', P.Metrics.RmseSelectedMm); W.Comma;
    W.KvNum('rmse_best_mm', P.Metrics.RmseBestMm);         W.Comma;
    W.KvInt('n_train_points', P.Metrics.NTrainPoints);
    W.ObjEnd;
    W.Comma;

    W.Key('stats');
    W.ObjStart;
    W.KvNum('rmse_mm', P.Stats.RmseMm);          W.Comma;
    W.KvNum('mae_mm', P.Stats.MaeMm);            W.Comma;
    W.KvNum('max_err_mm', P.Stats.MaxErrMm);     W.Comma;
    W.KvNum('correlation', P.Stats.Correlation);
    W.ObjEnd;

    { Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
      (включая пустой список): так ждёт загрузчик Python. }
    if M.HasPits then
    begin
      W.Comma;
      W.Key('pit_terms');
      W.ArrStart;
      for J := 0 to High(P.PitOffsetsDeg) do
      begin
        if J > 0 then W.Raw(', ');
        W.ObjStart;
        W.KvNum('dx_deg', P.PitOffsetsDeg[J]);  W.Comma;
        W.KvNum('amp', P.PitCoefs[J]);
        W.ObjEnd;
      end;
      W.ArrEnd;
    end;
    W.ObjEnd;
  end;
  if Length(M.Patches) > 0 then W.Raw(#10 + W.Ind);
  W.ArrEnd;
end;

function SaveSectionDocument(const Path: string; Sec: TSectionModel): string;
var
  W: TWriter;
  M: TModel;
  Opt: TModelOptions;
  PS: TPitShape;
  I: Integer;
begin
  M := Sec.Model;
  if (M = nil) or (not M.IsFitted) then
    raise Exception.Create('save_section_document: модель не обучена');
  W := TWriter.Create;
  try
    W.ObjStart;
    W.KvStr('format', 'pappa');   W.Comma;
    W.KvStr('version', '2.0');    W.Comma;
    if M.HasPits then W.KvStr('method', 'PitPatchApproximator')
    else W.KvStr('method', 'PatchApproximator');
    W.Comma;
    W.KvStr('created', IsoUtcNow);  W.Comma;

    W.Key('software');
    W.ObjStart;
    W.KvStr('language', PORT_LANGUAGE);  W.Comma;
    W.KvStr('pappa_version', PORT_VERSION);
    W.ObjEnd;
    W.Comma;

    W.Key('meta');
    W.ObjStart;
    W.KvInt('section_id', Sec.SectionId);   W.Comma;
    W.KvNum('height_mm', Sec.HeightMm);     W.Comma;
    W.KvStr('source', 'csv');               W.Comma;
    W.KvStr('description', Sec.Description);
    W.ObjEnd;
    W.Comma;

    W.Key('global');
    W.ObjStart;
    W.Key('units');
    W.ObjStart;
    W.KvStr('angle', 'degree');  W.Comma;
    W.KvStr('length', 'mm');
    W.ObjEnd;
    W.Comma;
    Opt := M.Options;
    W.KvInt('n_patches', Opt.NPatches);            W.Comma;
    W.KvNum('half_sector_deg', M.HalfSector);      W.Comma;
    W.KvNum('phase_deg', Opt.PhaseDeg);            W.Comma;
    W.KvNum('half_train_deg', M.HalfTrain);        W.Comma;
    W.KvNum('half_use_deg', M.HalfUse);            W.Comma;
    W.KvNum('overlap_train_deg', Opt.OverlapTrain); W.Comma;
    W.KvNum('overlap_use_deg', Opt.OverlapUse);    W.Comma;
    W.KvInt('deg_min', Opt.DegMin);                W.Comma;
    W.KvInt('deg_max', Opt.DegMax);                W.Comma;
    W.KvStr('coord_mode', Opt.CoordMode);          W.Comma;
    W.KvNum('deg_elbow_tol', Opt.DegElbowTol);     W.Comma;
    W.KvNum('amplitude_scale', Opt.AmplitudeScale);
    if M.HasPits then
    begin
      PS := M.PitShape;
      W.Comma;
      W.Key('pit');
      W.ObjStart;
      W.KvNum('sigma_deg', PS.SigmaDeg);         W.Comma;
      W.KvNum('core_sigma', PS.CoreSigma);       W.Comma;
      W.KvNum('window_sigma', PS.WindowSigma);   W.Comma;
      W.KvNum('pit_min_amp', PS.PitMinAmp);      W.Comma;
      W.KvBool('tapering', PS.Tapering);         W.Comma;
      W.Key('centers_deg');
      W.ArrStart;
      for I := 0 to High(M.Pits) do
      begin
        if I > 0 then W.Raw(', ');
        W.NumVal(M.Pits[I]);
      end;
      W.ArrEnd;
      W.ObjEnd;
    end;
    W.ObjEnd;
    W.Comma;

    WritePatches(W, M);
    W.Comma;

    W.Key('statistics');
    W.ObjStart;
    W.KvInt('n_points_total', Sec.NPointsTotal);     W.Comma;
    W.KvInt('n_outliers_removed', Sec.NOutliers);    W.Comma;
    W.KvNum('fit_time_ms', Sec.FitTimeMs);
    W.ObjEnd;

    W.ObjEnd;
    WriteTextFile(Path, W.Text + #10);
    Result := Path;
  finally
    W.Free;
  end;
end;

function SaveSample(const OutDir, Name: string; const Sections: TSectionArray;
  const O: TSampleOptions): string;
var
  W: TWriter;
  Ordered: TSectionArray;
  I, J: Integer;
  Tmp: TSectionModel;
  First: TModel;
  Opt: TModelOptions;
  PS: TPitShape;
  FileName, SectionPath: string;
begin
  ForceDirectories(IncludeTrailingPathDelimiter(OutDir) + 'sections');

  { порядок документов — по возрастанию section_id }
  SetLength(Ordered, Length(Sections));
  for I := 0 to High(Sections) do Ordered[I] := Sections[I];
  for I := 0 to High(Ordered) - 1 do
    for J := I + 1 to High(Ordered) do
      if Ordered[J].SectionId < Ordered[I].SectionId then
      begin
        Tmp := Ordered[I]; Ordered[I] := Ordered[J]; Ordered[J] := Tmp;
      end;
  if Length(Ordered) > 0 then First := Ordered[0].Model else First := nil;

  W := TWriter.Create;
  try
    W.ObjStart;
    W.KvStr('format', 'pappa-sample');  W.Comma;
    W.KvStr('version', '1.0');          W.Comma;
    W.KvStr('name', Name);              W.Comma;
    W.KvStr('created', IsoUtcNow);      W.Comma;

    W.Key('units');
    W.ObjStart;
    W.KvStr('angle', 'degree');  W.Comma;
    W.KvStr('length', 'mm');
    W.ObjEnd;
    W.Comma;

    W.Key('meta');
    W.ObjStart;
    W.KvStr('description', O.Description);
    W.ObjEnd;
    W.Comma;

    if O.InputCsv <> '' then
    begin
      W.Key('input');
      W.ObjStart;
      W.KvStr('csv', O.InputCsv);
      W.ObjEnd;
      W.Comma;
    end;

    W.Key('config');
    W.ObjStart;
    if First <> nil then Opt := First.Options else Opt := DefaultModelOptions;
    W.KvInt('n_patches', Opt.NPatches);         W.Comma;
    W.KvNum('phase_deg', Opt.PhaseDeg);         W.Comma;
    W.KvInt('deg_min', Opt.DegMin);             W.Comma;
    W.KvInt('deg_max', Opt.DegMax);             W.Comma;
    W.KvNum('overlap_train', Opt.OverlapTrain); W.Comma;
    W.KvNum('overlap_use', Opt.OverlapUse);     W.Comma;
    W.KvNum('deg_elbow_tol', Opt.DegElbowTol);  W.Comma;
    W.Key('cleaner');
    W.Raw('{"mode": "auto", "auto": {"method": "iqr", "baseline_deg": ' +
      JsonNum(O.Cleaner.BaselineDeg) + ', "iqr_k": ' + JsonNum(O.Cleaner.IqrK) + '}}');
    W.Comma;
    W.KvBool('pits', O.Pits);
    if O.Pits and (First <> nil) then
    begin
      PS := First.PitShape;
      W.Comma;
      W.KvNum('sigma_deg', PS.SigmaDeg);            W.Comma;
      W.KvNum('pit_core_sigma', PS.CoreSigma);      W.Comma;
      W.KvNum('pit_window_sigma', PS.WindowSigma);  W.Comma;
      W.KvNum('pit_min_amp', PS.PitMinAmp);         W.Comma;
      W.KvBool('tapering', PS.Tapering);
    end;
    W.Comma;
    W.Key('detector');
    W.Raw('null');
    W.ObjEnd;
    W.Comma;

    W.Key('sections');
    W.ArrStart;
    for I := 0 to High(Ordered) do
    begin
      FileName := Format('sections/%.2d.pappa.json', [I]);
      SectionPath := IncludeTrailingPathDelimiter(OutDir) + FileName;
      SaveSectionDocument(SectionPath, Ordered[I]);
      if I > 0 then W.Raw(',' + #10 + W.Ind) else W.Raw(#10 + W.Ind);
      W.ObjStart;
      W.KvInt('index', I);                              W.Comma;
      W.KvInt('section_id', Ordered[I].SectionId);      W.Comma;
      W.KvNum('height_mm', Ordered[I].HeightMm);        W.Comma;
      W.KvStr('file', FileName);                        W.Comma;
      W.KvInt('n_points', Ordered[I].NPointsTotal);     W.Comma;
      W.KvInt('n_outliers', Ordered[I].NOutliers);
      W.ObjEnd;
    end;
    if Length(Ordered) > 0 then W.Raw(#10 + W.Ind);
    W.ArrEnd;

    W.ObjEnd;
    WriteTextFile(IncludeTrailingPathDelimiter(OutDir) + 'sample.json', W.Text + #10);
    Result := OutDir;
  finally
    W.Free;
  end;
end;

end.
