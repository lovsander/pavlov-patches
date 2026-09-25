function r = conformance_check_cleaner(v)
% Вектор вида "cleaner": сравнение маски выбросов по ДОЛЕ точек (frac) —
% зона на самом пороге может «дрогнуть» на точку сетки.
  cfg = json_val(v, 'config', 'any');
  exp_ = json_val(v, 'expected', 'any');
  input = json_val(v, 'input', 'any');
  tol = json_val(v, 'tolerance', 'any');
  angles = json_val(input, 'angles_deg', 'nums');
  radii = json_val(input, 'radii_mm', 'nums');

  o = cleaner_options('baseline_deg', json_val(cfg, 'baseline_deg', 'num'), ...
                      'iqr_k', json_val(cfg, 'iqr_k', 'num'));
  res = cleaner_clean_iqr(angles, radii, o);
  mask = res.mask(:)';

  n = numel(radii);
  ref = false(1, n);
  idx = json_val(exp_, 'mask_true_indices', 'ints');   % индексы 0-based
  for k = 1:numel(idx)
    j = idx(k) + 1;                                    % -> 1-based
    if j >= 1 && j <= n
      ref(j) = true;
    end
  end

  got = sum(mask);
  extra = sum(mask & ~ref);
  missing = sum(~mask & ref);
  tol_n = max(1, floor(json_val(tol, 'frac', 'num') * n));
  want = json_val(exp_, 'n_outliers', 'int');
  ok = extra <= tol_n && missing <= tol_n && abs(got - want) <= tol_n;

  detail = sprintf('outliers %d (reference %d), extra %d, missing %d', ...
                   got, want, extra, missing);
  r = conformance_outcome(ok, detail);
end
