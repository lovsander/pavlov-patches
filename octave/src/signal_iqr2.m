function v = signal_iqr2(values)
% Межквартильный размах по перцентилям с линейной интерполяцией (P75 − P25).
  if isempty(values)
    v = 0;
    return;
  end
  v = signal_percentile(values, 75) - signal_percentile(values, 25);
end
