function coefs = linalg_polyfit(xs, ys, deg)
% МНК-полином степени deg: коэффициенты по УБЫВАНИЮ степени (как np.polyfit).
  xs = xs(:);
  a = zeros(numel(xs), deg + 1);
  for pw = 0:deg
    a(:, deg + 1 - pw) = xs .^ pw;   % столбцы по убыванию степени
  end
  coefs = linalg_lstsq(a, ys);
end
