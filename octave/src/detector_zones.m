function zones = detector_zones(angles, values, o)
% Зоны, где индикатор превышает порог k.
  if nargin < 3
    o = detector_options();
  end
  zones = detector_mask_to_zones(angles, values(:) > o.k, o);
end
