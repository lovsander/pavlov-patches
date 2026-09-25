function t = linalg_cheb_row(x, deg_max)
% Строка T_0(x)..T_deg_max(x) — тот же рекуррентный ряд, что и в матрице.
  t = zeros(1, deg_max + 1);
  t(1) = 1;
  if deg_max >= 1
    t(2) = x;
  end
  for k = 3:(deg_max + 1)
    t(k) = 2 * x * t(k - 1) - t(k - 2);
  end
end
