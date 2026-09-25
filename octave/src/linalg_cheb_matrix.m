function t = linalg_cheb_matrix(x, deg_max)
% Столбцы T_0(x)..T_deg_max(x) — базис Чебышёва (x ∈ [−1, 1]).
  x = x(:);
  n = numel(x);
  t = ones(n, deg_max + 1);
  if deg_max >= 1
    t(:, 2) = x;
  end
  for k = 3:(deg_max + 1)
    t(:, k) = 2 * x .* t(:, k - 1) - t(:, k - 2);
  end
end
