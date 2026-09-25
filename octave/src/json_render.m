function s = json_render(v)
% Документ как текст JSON: отступ 2 пробела, ключи — в порядке полей структуры
% (та же форма, что JsonWriter в cpp/sample_writer.cpp и writers остальных
% портов).
%
% ЛОВУШКА OCTAVE (краеугольная для этого порта): писатель — НЕ буфер с
% мутацией, как в R (там копились куски в окружении). Строим обычное дерево
% структур/ячеек, а этот рендерер обходит его. Отсюда два требования:
%   * порядок ПОЛЕЙ задаётся порядком создания структуры (struct(...) или
%     присваиваний) — Octave его сохраняет, и это то, чем мы управляем форму;
%   * значение-«вставить как есть» оборачивается json_raw().
  s = json_val_text(v, 0);
end

function s = json_val_text(v, depth)
% Рендер значения на заданной глубине (нужна для правильных отступов).
  if ischar(v)
    s = ['"' json_esc(v) '"'];
  elseif islogical(v) && isscalar(v)
    if v
      s = 'true';
    else
      s = 'false';
    end
  elseif isstruct(v)
    s = render_struct(v, depth);
  elseif iscell(v)
    s = render_array(v, depth);
  elseif isnumeric(v)
    if isscalar(v)
      s = json_num(v);          % скаляр — просто число, не массив из одного
    else
      s = render_numbers(v, depth);
    end
  else
    error('json_render: unsupported value type');
  end
end

function s = render_struct(v, depth)
  if isfield(v, 'pappa_raw_json')
    s = v.pappa_raw_json;
    return;
  end
  names = fieldnames(v);
  if isempty(names)
    s = '{}';
    return;
  end
  ind = indent_for(depth + 1);
  parts = cell(1, numel(names));
  for k = 1:numel(names)
    parts{k} = [ind '"' names{k} '": ' json_val_text(v.(names{k}), depth + 1)];
  end
  s = ['{' char(10) strjoin(parts, [',' char(10)]) char(10) indent_for(depth) '}'];
end

function s = render_array(c, depth)
% Массив (патчи, ямы, термы): каждый элемент — со своей строки.
  if isempty(c)
    s = '[]';
    return;
  end
  ind = indent_for(depth + 1);
  parts = cell(1, numel(c));
  for k = 1:numel(c)
    parts{k} = [ind json_val_text(c{k}, depth + 1)];
  end
  s = ['[' char(10) strjoin(parts, [',' char(10)]) char(10) indent_for(depth) ']'];
end

function s = render_numbers(v, depth)
% Числовой вектор — ОДНОЙ строкой значений через запятую с пробелом
% (как coefs/centers_deg в остальных портах).
  if isempty(v)
    s = '[]';
    return;
  end
  nums = cell(1, numel(v));
  for k = 1:numel(v)
    nums{k} = json_num(v(k));
  end
  ind = indent_for(depth + 1);
  s = ['[' char(10) ind strjoin(nums, ', ') char(10) indent_for(depth) ']'];
end

function ind = indent_for(depth)
  ind = repmat(' ', 1, 2 * depth);
end
