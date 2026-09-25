function o = cleaner_options(varargin)
% Параметры авто-очистки (замена @kwdef-структуры остальных портов).
  o = struct('baseline_deg', 1.0, 'iqr_k', 3.0, ...
             'max_removed_frac', 0.5, 'min_points', 20);
  o = pappa_nv(o, varargin);
end
