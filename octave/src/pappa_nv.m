function s = pappa_nv(s, args)
% Наложить пары «имя, значение» на структуру параметров.
%
% В Octave нет именованных аргументов (как @kwdef в Julia или **kwargs в
% Python), поэтому функции параметров принимают varargin и вызывают этот
% помощник: pappa_nv(struct(...), varargin).
  if mod(numel(args), 2) ~= 0
    error('pappa_nv: expected name/value pairs');
  end
  for k = 1:2:numel(args)
    name = args{k};
    if ~ischar(name)
      error('pappa_nv: option names must be strings');
    end
    if ~isfield(s, name)
      error(['pappa_nv: unknown option ' name]);
    end
    s.(name) = args{k + 1};
  end
end
