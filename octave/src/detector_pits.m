function pits = detector_pits(angles, radii, o)
% Центры ям (°) — по индикатору band_indicator.
  if nargin < 3
    o = detector_options();
  end
  zones = detector_zones(angles, detector_band(angles, radii, o), o);
  pits = zeros(1, numel(zones));
  for k = 1:numel(zones)
    pits(k) = detector_zone_center(zones{k});
  end
end
