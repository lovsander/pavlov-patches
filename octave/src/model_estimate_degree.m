function est = model_estimate_degree(m, xs, ys)
% Правило «локтя»: наименьшая чётная степень, на которой RMSE обучающего окна
% не хуже лучшей более чем на deg_elbow_tol.
% Возвращает [степень, RMSE выбранной, лучшая RMSE].
%
% Свип степеней — ОДНОЙ матрицей Грама в базисе Чебышёва и RMSE по явным
% остаткам (в нормированном режиме); в режиме coord_mode == "raw" базис
% Чебышёва неприменим (x вне [−1, 1]) — там прямой полиномиальный МНК.
  xs = xs(:);
  ys = ys(:);
  n = numel(xs);
  if n < 5
    est = [m.options.deg_min, 0, 0];
    return;
  end

  degs = [];
  rmses = [];
  best_deg = m.options.deg_min;
  best = Inf;

  if strcmp(m.options.coord_mode, 'raw')
    for deg = m.options.deg_min:2:m.options.deg_max
      a = zeros(n, deg + 1);
      for pw = 0:deg
        a(:, deg + 1 - pw) = xs .^ pw;
      end
      co = linalg_lstsq(a, ys);
      r = sqrt(sum((a * co - ys) .^ 2) / n);
      degs(end + 1) = deg;
      rmses(end + 1) = r;
      if r < best
        best = r;
        best_deg = deg;
      end
    end
  else
    dmax = m.options.deg_max;
    yref = sum(ys) / n;
    tt = linalg_cheb_matrix(xs, dmax);
    yc = ys - yref;
    gram = tt' * tt;          % (в R — crossprod, в Octave — просто tt'*tt)
    rhs = tt' * yc;           % столбец p×1, как crossprod в R
    for deg = m.options.deg_min:2:dmax
      nn = deg + 1;
      co = linalg_lstsq(gram(1:nn, 1:nn), rhs(1:nn));
      r = sqrt(sum((tt(:, 1:nn) * co - yc) .^ 2) / n);
      degs(end + 1) = deg;
      rmses(end + 1) = r;
      if r < best
        best = r;
        best_deg = deg;
      end
    end
  end

  limit = best * (1 + m.options.deg_elbow_tol);
  sel = best_deg;
  rmse_sel = best;
  for k = 1:numel(degs)
    if rmses(k) <= limit
      sel = degs(k);
      rmse_sel = rmses(k);
      break;
    end
  end
  est = [sel, rmse_sel, best];
end
