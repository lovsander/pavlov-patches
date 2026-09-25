function step = signal_angular_step(angles)
% Медианный шаг сетки по углам (медиана ПОЛОЖИТЕЛЬНЫХ разностей, иначе 1).
  a = angles(:);
  n = numel(a);
  if n < 2
    step = 1;
    return;
  end
  d = diff(a);
  d = d(d > 0);
  if isempty(d)
    step = 1;
  else
    step = signal_median2(d);
  end
end
