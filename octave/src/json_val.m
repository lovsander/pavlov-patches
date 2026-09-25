function v = json_val(node, key, mode, def)
% Прочитать поле разобранного JSON-объекта.
%   mode: 'any' | 'num' | 'int' | 'text' | 'bool' | 'nums' | 'ints' | 'list'
%   def:  необязательное — что вернуть, если ключа нет или тип не тот
%         (аналог jdbl_or / jbool_or R-порта).
  if nargin < 3
    mode = 'any';
  end
  has_def = (nargin >= 4);
  if ~isstruct(node) || ~isfield(node, key)
    if has_def
      v = def;
      return;
    end
    error(['json_val: missing key ' key]);
  end
  raw = node.(key);
  switch mode
    case 'any'
      v = raw;
    case 'num'
      if isnumeric(raw) && isscalar(raw)
        v = double(raw);
      elseif has_def
        v = def;
      else
        error(['json_val: ' key ' is not a number']);
      end
    case 'int'
      if isnumeric(raw) && isscalar(raw)
        % округление «половина к чётному»: у Octave round() — от нуля
        v = signal_round_even(double(raw));
      elseif has_def
        v = def;
      else
        error(['json_val: ' key ' is not an integer']);
      end
    case 'text'
      if ischar(raw)
        v = raw;
      elseif has_def
        v = def;
      else
        error(['json_val: ' key ' is not a string']);
      end
    case 'bool'
      if islogical(raw) && isscalar(raw)
        v = raw;
      elseif has_def
        v = def;
      else
        error(['json_val: ' key ' is not a boolean']);
      end
    case 'nums'
      v = json_nums(raw);
    case 'ints'
      v = signal_round_even(json_nums(raw));
    case 'list'
      if iscell(raw)
        v = raw;
      elseif isnumeric(raw) && isempty(raw)
        v = {};
      elseif has_def
        v = def;
      else
        error(['json_val: ' key ' is not an array']);
      end
    otherwise
      error(['json_val: unknown mode ' mode]);
  end
end
