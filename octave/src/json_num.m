function s = json_num(v)
% Число в стиле %.17g из C/C++: целые без дробной части, иначе кратчайшая
% запись, которая читается обратно в ТО ЖЕ double (для очень малых — экспонента,
% это валидный JSON и понятно парсеру Python).
%
% ЛОВУШКА OCTAVE: нет «кратчайшего» форматирования (в C# это "R"/G17, в Python
% repr). Поэтому пробуем %.1g, %.2g, ... %.17g и берём первую запись, которая
% возвращается в исходное число.
  v = double(v);
  if ~isscalar(v) || ~isfinite(v)
    s = '0';
    return;
  end
  if v == 0
    s = '0';
    return;
  end
  if abs(v) < 1e15 && v == round(v)
    s = sprintf('%.0f', v);      % printf здесь округляет половину к чётному
    return;
  end
  for digits = 1:17
    s = sprintf('%.*g', digits, v);
    if str2double(s) == v
      return;
    end
  end
  s = sprintf('%.17g', v);
end
