function out = signal_smooth_wrap(x, window)
% Скользящее среднее по кольцу (окно в точках); сумма делится на w — как в
% остальных портах (не mean(), чтобы порядок суммирования был тем же).
  x = x(:);
  n = numel(x);
  w = signal_odd_window(window, n);
  if w < 3 || n < 3
    out = x;
    return;
  end
  h = (w - 1) / 2;
  idx = mod((1:n)' - h - 1 + (0:w - 1), n) + 1;   % см. signal_median_filter
  out = sum(x(idx), 2) / w;
end
