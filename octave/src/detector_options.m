function o = detector_options(varargin)
% Параметры детектора ям (трещин).
  o = struct('window_deg', 1.0, 'wide_deg', 10.0, 'smooth_deg', 2.0, ...
             'k', 5.5, 'min_zone_deg', 2.0);
  o = pappa_nv(o, varargin);
end
