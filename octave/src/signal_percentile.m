function p = signal_percentile(values, q)
% Перцентиль с линейной интерполяцией (numpy.percentile / тип 7 у R).
% quantile()/prctile() из Octave не подходят: у них другие правила
% интерполяции и зависимость от пакета statistics.
  n = numel(values);
  if n == 0
    p = 0;
    return;
  end
  v = sort(values(:));
  pos = (q / 100) * (n - 1);     % позиция 0-based, как в numpy
  lo = floor(pos);
  fr = pos - lo;
  hi = min(lo + 1, n - 1);
  p = v(lo + 1) + fr * (v(hi + 1) - v(lo + 1));
end
