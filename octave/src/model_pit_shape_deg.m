function v = model_pit_shape_deg(m, d_deg)
% Оконный гаусс ямной фичи как функция расстояния от центра ямы (°):
% exp(−d²/2σ²) с опциональной smoothstep-отсечкой на границе окна.
  d = abs(d_deg);
  sigma = m.pit_shape.sigma_deg;
  base = exp(-(d .* d) / (2 * sigma * sigma));
  if ~m.pit_shape.tapering
    v = base;
    return;
  end
  core = m.pit_shape.core_sigma * sigma;
  edge = m.pit_shape.window_sigma * sigma;
  if edge <= core
    v = base;
    return;
  end
  t = min(max((edge - d) / (edge - core), 0), 1);
  v = base .* t .* t .* (3 - 2 * t);
end
