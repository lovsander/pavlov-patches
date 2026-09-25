function m = model_fit(m, angles, radii)
% Обучение модели: патчи с адаптивной степенью, smoothstep-смешивание и
% оконный гауссов фичер ям. Совпадает с референсом Python и остальными
% портами: тот же базис, та же политика степени, тот же МНК.
%
% ВНИМАНИЕ: модель передаётся по значению — результат нужно присвоить:
%   m = model_fit(m, angles, radii);
  if numel(angles) ~= numel(radii)
    error('model_fit: lengths differ');
  end
  if numel(angles) < 10
    error('model_fit: too few points');
  end
  angles = angles(:);
  radii = radii(:);

  sector = 360 / m.options.n_patches;
  m.half_sector = sector / 2;
  centers = mod((0:(m.options.n_patches - 1)) * sector + m.half_sector + ...
                m.options.phase_deg, 360);
  ht = model_half_train(m);
  m.patches = {};

  for ci = 1:numel(centers)
    c0 = centers(ci);
    [xs, ys] = model_window_of(m, angles, radii, c0);
    n = numel(xs);
    if n < 5
      continue;
    end

    est = model_estimate_degree(m, xs, ys);
    deg = est(1);
    rmse_sel = est(2);
    rmse_best = est(3);

    offs = model_pit_offsets(m, c0, ht);
    ncol = deg + 1 + numel(offs);
    a = zeros(n, ncol);
    for pw = 0:deg
      a(:, deg + 1 - pw) = xs .^ pw;
    end
    for j = 1:numel(offs)
      a(:, deg + 1 + j) = model_pit_shape_deg(m, abs(xs * ht - offs(j)));
    end
    co = linalg_lstsq(a, ys);
    poly_coef = co(1:(deg + 1));

    % Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
    kept_offsets = [];
    kept_coefs = [];
    for j = 1:numel(offs)
      shape = model_pit_shape_deg(m, abs(xs * ht - offs(j)));
      max_abs = max(abs(co(deg + 1 + j) * shape));
      if max_abs >= m.pit_shape.pit_min_amp
        kept_offsets(end + 1) = offs(j);
        kept_coefs(end + 1) = co(deg + 1 + j);
      end
    end

    m.patches{end + 1} = model_build_patch(m, c0, deg, xs, ys, poly_coef, ...
                                           kept_offsets, kept_coefs, ...
                                           rmse_sel, rmse_best, angles, radii);
  end
  m.is_fitted = true;
end

function p = model_build_patch(m, c0, deg, xs, ys, poly_coef, kept_offsets, ...
                               kept_coefs, rmse_sel, rmse_best, angles, radii)
% Метрики и статистика патча по его обучающему окну (полный базис).
% Подфункция того же файла: снаружи не вызывается, отдельный .m не нужен.
  n = numel(xs);
  ht = model_half_train(m);
  sse = 0;
  sae = 0;
  mx = 0;
  fit_vals = zeros(n, 1);
  for i = 1:n
    v = linalg_polyval(poly_coef, xs(i));
    for j = 1:numel(kept_offsets)
      v = v + kept_coefs(j) * model_pit_shape_deg(m, abs(xs(i) * ht - kept_offsets(j)));
    end
    fit_vals(i) = v;
    e = v - ys(i);
    sse = sse + e * e;
    sae = sae + abs(e);
    mx = max(mx, abs(e));
  end

  nf = n;
  mf = sum(fit_vals) / nf;
  my = sum(ys) / nf;
  cov = 0;
  vf = 0;
  vy = 0;
  for i = 1:n
    df = fit_vals(i) - mf;
    dy = ys(i) - my;
    cov = cov + df * dy;
    vf = vf + df * df;
    vy = vy + dy * dy;
  end
  if vf > 0 && vy > 0
    corr = cov / sqrt(vf * vy);
  else
    corr = 0;
  end

  % Справочные метрики сектора: P95 − P5 и среднее по точкам сектора.
  dist = abs(mod(angles - c0 + 180, 360) - 180);
  sec = radii(dist <= m.half_sector);
  amp = 0;
  mean_sec = 0;
  if numel(sec) >= 5
    amp = signal_percentile(sec, 95) - signal_percentile(sec, 5);
    mean_sec = sum(sec) / numel(sec);
  end
  if mean_sec > 0
    amp_norm = amp / mean_sec;
  else
    amp_norm = 0;
  end

  p = struct();
  p.center_deg = c0;
  p.degree = deg;
  p.n_points = n;
  p.coefs = poly_coef(:);
  p.pit_offsets_deg = kept_offsets(:);
  p.pit_coefs = kept_coefs(:);
  p.metrics = struct('amplitude_mm', amp, 'mean_radius_mm', mean_sec, ...
                     'amplitude_norm', amp_norm, ...
                     'deg_elbow_tol', m.options.deg_elbow_tol, ...
                     'rmse_selected_mm', rmse_sel, 'rmse_best_mm', rmse_best, ...
                     'n_train_points', n);
  p.stats = struct('rmse_mm', sqrt(sse / nf), 'mae_mm', sae / nf, ...
                   'max_err_mm', mx, 'correlation', corr);
end
