function v = json_parse(text)
% Минимальный JSON-парсер: объекты -> структуры (порядок полей = порядок в
% файле), массивы -> ячейки, числа -> double, true/false -> logical, null -> [].
% Внешних пакетов нет намеренно: порт должен работать на голом Octave.
%
% ЛОВУШКА OCTAVE (производительность, а не синтаксис): состояние парсера — это
% ДВУХЭЛЕМЕНТНЫЙ вектор [позиция, длина], а сам текст передаётся отдельным
% аргументом. Если сложить текст внутрь структуры состояния (как в R-порте с
% окружением p$s), то на каждом шаге по символу Octave копировал бы всю строку
% (в векторах конформанса это 40 КБ) — разбор растянулся бы на минуты.
  s = char(text);
  n = numel(s);
  if n == 0
    error('json_parse: empty input');
  end
  isws = (s == ' ') | (s == char(9)) | (s == char(10)) | (s == char(13));
  numc = (s >= '0' & s <= '9') | s == '+' | s == '-' | s == '.' | ...
         s == 'e' | s == 'E';
  st = skip_ws(isws, [1, n]);
  v = parse_value(s, numc, isws, st);
end

function st = skip_ws(isws, st)
  i = st(1);
  n = st(2);
  while i <= n && isws(i)
    i = i + 1;
  end
  st = [i, n];
end

function [v, st] = parse_value(s, numc, isws, st)
  i = st(1);
  n = st(2);
  if i > n
    error('json_parse: unexpected end of input');
  end
  c = s(i);
  if c == '{'
    [v, st] = parse_object(s, numc, isws, st);
  elseif c == '['
    [v, st] = parse_array(s, numc, isws, st);
  elseif c == '"'
    [v, st] = parse_string(s, st);
  elseif c == 't'
    st = expect_lit(s, st, 'true');
    v = true;
  elseif c == 'f'
    st = expect_lit(s, st, 'false');
    v = false;
  elseif c == 'n'
    st = expect_lit(s, st, 'null');
    v = [];
  else
    [v, st] = parse_number(s, numc, st);
  end
end

function [o, st] = parse_object(s, numc, isws, st)
  i = st(1);
  n = st(2);
  o = struct();
  st = skip_ws(isws, [i + 1, n]);            % {
  i = st(1);
  if i <= n && s(i) == '}'
    st = [i + 1, n];
    return;
  end
  while true
    [k, st] = parse_string(s, st);
    st = skip_ws(isws, st);
    i = st(1);
    if i > n || s(i) ~= ':'
      error('json_parse: expected '':''');
    end
    st = skip_ws(isws, [i + 1, n]);
    [val, st] = parse_value(s, numc, isws, st);
    o.(k) = val;                             % порядок полей = порядок в файле
    st = skip_ws(isws, st);
    i = st(1);
    if i > n
      error('json_parse: unexpected end of object');
    end
    c = s(i);
    st = [i + 1, n];
    if c == '}'
      return;
    end
    if c ~= ','
      error('json_parse: expected '','' or ''}''');
    end
    st = skip_ws(isws, st);
  end
end

function [a, st] = parse_array(s, numc, isws, st)
  i = st(1);
  n = st(2);
  a = {};
  st = skip_ws(isws, [i + 1, n]);            % [
  i = st(1);
  if i <= n && s(i) == ']'
    st = [i + 1, n];
    return;
  end
  while true
    [val, st] = parse_value(s, numc, isws, st);
    a{end + 1} = val;
    st = skip_ws(isws, st);
    i = st(1);
    if i > n
      error('json_parse: unexpected end of array');
    end
    c = s(i);
    st = [i + 1, n];
    if c == ']'
      return;
    end
    if c ~= ','
      error('json_parse: expected '','' or '']''');
    end
    st = skip_ws(isws, st);
  end
end

function [out, st] = parse_string(s, st)
  i = st(1);
  n = st(2);
  if s(i) ~= '"'
    error('json_parse: expected a string');
  end
  BS = char(92);
  i = i + 1;
  out = '';
  while true
    if i > n
      error('json_parse: unterminated string');
    end
    c = s(i);
    i = i + 1;
    if c == '"'
      st = [i, n];
      return;
    end
    if c ~= BS
      out(end + 1) = c;
      continue;
    end
    if i > n
      error('json_parse: unterminated escape');
    end
    e = s(i);
    i = i + 1;
    if e == 'n'
      out(end + 1) = char(10);
    elseif e == 't'
      out(end + 1) = char(9);
    elseif e == 'r'
      out(end + 1) = char(13);
    elseif e == 'b'
      out(end + 1) = char(8);
    elseif e == 'f'
      out(end + 1) = char(12);
    elseif e == 'u'
      if i + 3 > n
        error('json_parse: bad hex escape');
      end
      code = hex2dec(s(i:i + 3));
      i = i + 4;
      if code < 128
        out(end + 1) = char(code);
      else
        out(end + 1) = '?';     % порт ASCII-ориентирован, как и остальные
      end
    else
      out(end + 1) = e;
    end
  end
end

function [v, st] = parse_number(s, numc, st)
  i = st(1);
  n = st(2);
  j = i;
  while j <= n && numc(j)
    j = j + 1;
  end
  txt = s(i:(j - 1));
  v = str2double(txt);
  if isnan(v)
    error(['json_parse: bad number ' txt]);
  end
  st = [j, n];
end

function st = expect_lit(s, st, lit)
  i = st(1);
  n = st(2);
  if i + numel(lit) - 1 > n || ~strcmp(s(i:(i + numel(lit) - 1)), lit)
    error(['json_parse: expected ' lit]);
  end
  st = [i + numel(lit), n];
end
