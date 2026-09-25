function [xs, ys] = model_window_of(m, angles, radii, center)
% Точки обучающего окна патча в локальной координате (нормированной или сырой).
% Порядок обхода — как в остальных портах: сдвиги −360, 0, +360, внутри — по
% возрастанию угла.
  half = model_half_train(m);
  norm = ~strcmp(m.options.coord_mode, 'raw');
  angles = angles(:);
  radii = radii(:);
  dxs = [];
  ys = [];
  for shift = [-360, 0, 360]
    dx = angles + shift - center;
    keep = (dx >= -half) & (dx <= half);
    dxs = [dxs; dx(keep)];
    ys = [ys; radii(keep)];
  end
  if norm
    xs = dxs / half;
  else
    xs = dxs;
  end
end
