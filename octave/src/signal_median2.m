function m = signal_median2(values)
% Медиана как numpy.median: для чётного n — среднее двух центральных значений.
% Считаем сами, а не median(): у неё другое поведение на NaN/пустом входе,
% а референс numpy-совместим.
  n = numel(values);
  if n == 0
    m = 0;
    return;
  end
  v = sort(values(:));
  if mod(n, 2) == 1
    m = v((n + 1) / 2);
  else
    m = 0.5 * (v(n / 2) + v(n / 2 + 1));
  end
end
