function out = detector_band(angles, radii, o)
% Безразмерный индикатор ям (в «MAD-ах»):
%   band = |узкая медиана − широкая медиана|, сглаженный,
%   нормированный на свою робастную sigma.
  if nargin < 3
    o = detector_options();
  end
  angles = angles(:);
  radii = radii(:);
  narrow = signal_median_filter(radii, signal_window_points(angles, o.window_deg));
  wide = signal_median_filter(radii, signal_window_points(angles, o.wide_deg));
  band = abs(narrow - wide);

  out = signal_smooth_wrap(band, signal_window_points(angles, o.smooth_deg));
  s = signal_robust_sigma(out);
  if s > 1e-12
    out = out / s;
  else
    out = zeros(size(out));    % гладкий профиль: индикатор без масштаба
  end
end
