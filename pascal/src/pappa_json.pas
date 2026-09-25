unit pappa_json;
{ Минимальный JSON: разбор и запись без внешних зависимостей.
  Объекты — параллельные массивы ключей/значений (порядок сохраняется). }
{$mode objfpc}{$H+}

interface

uses
  Math, SysUtils, Classes, pappa_signal;

type
  TJsonKind = (jkNull, jkBool, jkNum, jkStr, jkArr, jkObj);

  TJsonNode = class
  public
    Kind: TJsonKind;
    BoolVal: Boolean;
    NumVal: Double;
    StrVal: string;
    Arr: array of TJsonNode;
    ObjKeys: TStrArray;
    ObjVals: array of TJsonNode;
    destructor Destroy; override;
    function Has(const Key: string): Boolean;
    function Get(const Key: string): TJsonNode;
    function AsDouble: Double;
    function AsInt: Integer;
    function AsStr: string;
    function ArrCount: Integer;
    function Dbl(const Key: string): Double;
    function DblOr(const Key: string; Def: Double): Double;
    function Int(const Key: string): Integer;
    function IntOr(const Key: string; Def: Integer): Integer;
    function Text(const Key: string): string;
    function BoolOr(const Key: string; Def: Boolean): Boolean;
    function Doubles(const Key: string): TDoubleArray;
    function Ints(const Key: string): TIntArray;
    function AsDoublesArray: TDoubleArray;
  end;

function JsonParse(const S: string): TJsonNode;
function JsonNum(V: Double): string;
function JsonEsc(const S: string): string;
function ReadTextFile(const Path: string): string;
procedure WriteTextFile(const Path, Text: string);

implementation

type
  TJsonParser = class
  private
    FS: string;
    FI: Integer;
    procedure Ws;
    procedure Expect(const Lit: string);
    function ParseValue: TJsonNode;
    function ParseObject: TJsonNode;
    function ParseArray: TJsonNode;
    function ParseString: string;
    function ParseNumber: Double;
  public
    constructor Create(const S: string);
    function Parse: TJsonNode;
  end;

constructor TJsonParser.Create(const S: string);
begin
  inherited Create;
  FS := S;
  FI := 1;
end;

procedure TJsonParser.Ws;
begin
  while (FI <= Length(FS)) and (FS[FI] in [#9, #10, #13, ' ']) do Inc(FI);
end;

procedure TJsonParser.Expect(const Lit: string);
var
  I: Integer;
begin
  for I := 1 to Length(Lit) do
  begin
    if (FI > Length(FS)) or (FS[FI] <> Lit[I]) then
      raise Exception.CreateFmt('JSON: ожидался литерал %s', [Lit]);
    Inc(FI);
  end;
end;

function TJsonParser.ParseValue: TJsonNode;
begin
  Ws;
  case FS[FI] of
    '{': Result := ParseObject;
    '[': Result := ParseArray;
    '"': begin
           Result := TJsonNode.Create;
           Result.Kind := jkStr;
           Result.StrVal := ParseString;
         end;
    't': begin
           Expect('true');
           Result := TJsonNode.Create;
           Result.Kind := jkBool;
           Result.BoolVal := True;
         end;
    'f': begin
           Expect('false');
           Result := TJsonNode.Create;
           Result.Kind := jkBool;
           Result.BoolVal := False;
         end;
    'n': begin
           Expect('null');
           Result := TJsonNode.Create;
           Result.Kind := jkNull;
         end;
  else
    begin
      Result := TJsonNode.Create;
      Result.Kind := jkNum;
      Result.NumVal := ParseNumber;
    end;
  end;
end;

function TJsonParser.ParseObject: TJsonNode;
var
  Key: string;
begin
  Result := TJsonNode.Create;
  Result.Kind := jkObj;
  Inc(FI);                       { открывающая скобка съедена }
  Ws;
  if FS[FI] = '}' then
  begin
    Inc(FI);
    Exit;
  end;
  while True do
  begin
    Ws;
    Key := ParseString;
    Ws;
    if FS[FI] <> ':' then raise Exception.Create('JSON: ожидалось '':''');
    Inc(FI);
    SetLength(Result.ObjKeys, Length(Result.ObjKeys) + 1);
    Result.ObjKeys[High(Result.ObjKeys)] := Key;
    SetLength(Result.ObjVals, Length(Result.ObjVals) + 1);
    Result.ObjVals[High(Result.ObjVals)] := ParseValue;
    Ws;
    if FS[FI] = '}' then
    begin
      Inc(FI);
      Exit;
    end;
    if FS[FI] <> ',' then raise Exception.Create('JSON: ожидалась '','' или ''}''');
    Inc(FI);
  end;
end;

function TJsonParser.ParseArray: TJsonNode;
begin
  Result := TJsonNode.Create;
  Result.Kind := jkArr;
  Inc(FI);                       { открывающая скобка съедена }
  Ws;
  if FS[FI] = ']' then
  begin
    Inc(FI);
    Exit;
  end;
  while True do
  begin
    SetLength(Result.Arr, Length(Result.Arr) + 1);
    Result.Arr[High(Result.Arr)] := ParseValue;
    Ws;
    if FS[FI] = ']' then
    begin
      Inc(FI);
      Exit;
    end;
    if FS[FI] <> ',' then raise Exception.Create('JSON: ожидалась '','' или '']''');
    Inc(FI);
  end;
end;

function TJsonParser.ParseString: string;
var
  C, E: Char;
  Hex: string;
  Code: Integer;
begin
  if FS[FI] <> '"' then raise Exception.Create('JSON: ожидалась строка');
  Inc(FI);
  Result := '';
  while True do
  begin
    C := FS[FI];
    Inc(FI);
    if C = '"' then Exit;
    if C <> '\' then
    begin
      Result := Result + C;
      Continue;
    end;
    E := FS[FI];
    Inc(FI);
    case E of
      'n': Result := Result + #10;
      't': Result := Result + #9;
      'r': Result := Result + #13;
      'b': Result := Result + #8;
      'f': Result := Result + #12;
      'u': begin
             Hex := Copy(FS, FI, 4);
             Inc(FI, 4);
             Code := StrToInt('$' + Hex);
             if Code < 128 then Result := Result + Chr(Code)
             else Result := Result + '?';   { вне ASCII в наших векторах не встречается }
           end;
    else
      Result := Result + E;
    end;
  end;
end;

function TJsonParser.ParseNumber: Double;
var
  Start: Integer;
  Txt: string;
begin
  Start := FI;
  while (FI <= Length(FS)) and (FS[FI] in ['+', '-', '0'..'9', '.', 'e', 'E']) do Inc(FI);
  Txt := Copy(FS, Start, FI - Start);
  if not TryStrToFloat(Txt, Result) then
    raise Exception.CreateFmt('JSON: плохое число %s', [Txt]);
end;

function TJsonParser.Parse: TJsonNode;
begin
  Result := ParseValue;
end;

function JsonParse(const S: string): TJsonNode;
var
  P: TJsonParser;
begin
  P := TJsonParser.Create(S);
  try
    Result := P.Parse;
  finally
    P.Free;
  end;
end;

destructor TJsonNode.Destroy;
var
  I: Integer;
begin
  for I := 0 to High(Arr) do Arr[I].Free;
  for I := 0 to High(ObjVals) do ObjVals[I].Free;
  inherited Destroy;
end;

function TJsonNode.Has(const Key: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to High(ObjKeys) do
    if ObjKeys[I] = Key then Exit(True);
end;

function TJsonNode.Get(const Key: string): TJsonNode;
var
  I: Integer;
begin
  for I := 0 to High(ObjKeys) do
    if ObjKeys[I] = Key then Exit(ObjVals[I]);
  raise Exception.CreateFmt('JSON: нет ключа %s', [Key]);
end;

function TJsonNode.AsDouble: Double;
begin
  if Kind <> jkNum then raise Exception.Create('JSON: ожидалось число');
  Result := NumVal;
end;

function TJsonNode.AsInt: Integer;
begin
  Result := Trunc(AsDouble);
end;

function TJsonNode.AsStr: string;
begin
  if Kind <> jkStr then raise Exception.Create('JSON: ожидалась строка');
  Result := StrVal;
end;

function TJsonNode.ArrCount: Integer;
begin
  if Kind <> jkArr then raise Exception.Create('JSON: ожидался массив');
  Result := Length(Arr);
end;

function TJsonNode.Dbl(const Key: string): Double;
begin
  Result := Get(Key).AsDouble;
end;

function TJsonNode.DblOr(const Key: string; Def: Double): Double;
begin
  if Has(Key) and (Get(Key).Kind = jkNum) then Result := Get(Key).NumVal
  else Result := Def;
end;

function TJsonNode.Int(const Key: string): Integer;
begin
  Result := Get(Key).AsInt;
end;

function TJsonNode.IntOr(const Key: string; Def: Integer): Integer;
begin
  if Has(Key) and (Get(Key).Kind = jkNum) then Result := Trunc(Get(Key).NumVal)
  else Result := Def;
end;

function TJsonNode.Text(const Key: string): string;
begin
  Result := Get(Key).AsStr;
end;

function TJsonNode.BoolOr(const Key: string; Def: Boolean): Boolean;
begin
  if Has(Key) and (Get(Key).Kind = jkBool) then Result := Get(Key).BoolVal
  else Result := Def;
end;

function TJsonNode.Doubles(const Key: string): TDoubleArray;
var
  N: TJsonNode;
  I: Integer;
begin
  N := Get(Key);
  if N.Kind <> jkArr then raise Exception.Create('JSON: ожидался массив чисел');
  SetLength(Result, Length(N.Arr));
  for I := 0 to High(N.Arr) do Result[I] := N.Arr[I].AsDouble;
end;

function TJsonNode.Ints(const Key: string): TIntArray;
var
  N: TJsonNode;
  I: Integer;
begin
  N := Get(Key);
  if N.Kind <> jkArr then raise Exception.Create('JSON: ожидался массив чисел');
  SetLength(Result, Length(N.Arr));
  for I := 0 to High(N.Arr) do Result[I] := Trunc(N.Arr[I].AsDouble);
end;

{ Значения самого узла-массива как массив чисел. }
function TJsonNode.AsDoublesArray: TDoubleArray;
var
  I: Integer;
begin
  if Kind <> jkArr then raise Exception.Create('JSON: ожидался массив');
  SetLength(Result, Length(Arr));
  for I := 0 to High(Arr) do Result[I] := Arr[I].AsDouble;
end;

{ Число в стиле %.17g из C/C++: целые без дробной части, иначе 17 значащих цифр
  (ffGeneral сам переходит к экспоненте для очень больших/малых значений). }
function JsonNum(V: Double): string;
var
  Dummy: Integer;
begin
  if (not IsInfinite(V)) and (V = 0) then Exit('0');
  if IsInfinite(V) or IsNan(V) then Exit('0');
  if (Abs(V) < 1e15) and (V = Int(V)) then
  begin
    Dummy := Trunc(V);
    Exit(IntToStr(Dummy));
  end;
  Result := FloatToStrF(V, ffGeneral, 17, 0);
end;

function JsonEsc(const S: string): string;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    case C of
      '"': Result := Result + '\"';
      '\': Result := Result + '\\';
      #10: Result := Result + '\n';
      #13: Result := Result + '\r';
      #9: Result := Result + '\t';
    else
      Result := Result + C;
    end;
  end;
end;

function ReadTextFile(const Path: string): string;
var
  F: TFileStream;
begin
  F := TFileStream.Create(Path, fmOpenRead or fmShareDenyNone);
  try
    SetLength(Result, F.Size);
    if F.Size > 0 then F.ReadBuffer(Result[1], F.Size);
  finally
    F.Free;
  end;
end;

procedure WriteTextFile(const Path, Text: string);
var
  F: TFileStream;
begin
  F := TFileStream.Create(Path, fmCreate);
  try
    if Length(Text) > 0 then F.WriteBuffer(Text[1], Length(Text));
  finally
    F.Free;
  end;
end;

initialization
  { Документ должен быть одинаковым при любой локали: точка как разделитель. }
  DefaultFormatSettings.DecimalSeparator := '.';
  DefaultFormatSettings.ThousandSeparator := #0;

end.
