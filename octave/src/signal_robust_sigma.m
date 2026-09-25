function s = signal_robust_sigma(values)
% Робастная оценка масштаба: 1.4826 · MAD (медианное абсолютное отклонение).
  if isempty(values)
    s = 0;
    return;
  end
  med = signal_median2(values);
  s = 1.4826 * signal_median2(abs(values(:) - med));
end
