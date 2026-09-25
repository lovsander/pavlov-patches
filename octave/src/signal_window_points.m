function w = signal_window_points(angles, span_deg)
% Ширина окна в точках: round(span/шаг) «половина к чётному», нечётная,
% не шире массива (минимум 3).
  n = numel(angles);
  if n < 3
    w = max(1, n);
    return;
  end
  w = signal_round_even(span_deg / signal_angular_step(angles));
  w = signal_odd_window(w, n);
  if w < 3
    w = 3;
  end
end
