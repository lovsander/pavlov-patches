function o = model_options(varargin)
% Параметры модели PAPPA (патчи, степени, окна, режим координаты).
  o = struct('n_patches', 7, 'phase_deg', 24.75, 'deg_min', 4, 'deg_max', 14, ...
             'overlap_train', 15.0, 'overlap_use', 5.0, 'deg_elbow_tol', 0.05, ...
             'amplitude_scale', 180.0, 'coord_mode', 'normalized');
  o = pappa_nv(o, varargin);
end
