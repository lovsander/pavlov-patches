function zones = detector_mask_to_zones(angles, mask, o)
% Непрерывные зоны по маске; углы — по возрастанию. Зона — структура lo/hi,
% список зон — массив ячеек (в Octave массив структур с полем-списком
% «схлопывается» в структурный массив, поэтому именно ячейки).
  if nargin < 3
    o = detector_options();
  end
  angles = angles(:);
  mask = mask(:);
  n = numel(angles);
  zones = {};
  if ~any(mask)
    return;
  end

  d = diff(angles);
  if isempty(d)
    step = 1;
  else
    step = signal_median2(d);
  end

  i = 1;
  while i <= n
    if ~mask(i)
      i = i + 1;
      continue;
    end
    j = i;
    while j + 1 <= n && mask(j + 1)
      j = j + 1;
    end
    zones{end + 1} = struct('lo', angles(i) - step / 2, ...
                            'hi', angles(j) + step / 2);
    i = j + 1;
  end

  % Кольцо: зона, доходящая до 360° и начинающаяся с 0°, — это одна зона.
  if numel(zones) > 1 && mask(1) && mask(n)
    merged = {struct('lo', zones{numel(zones)}.lo - 360, 'hi', zones{1}.hi)};
    for k = 2:(numel(zones) - 1)
      merged{end + 1} = zones{k};
    end
    zones = merged;
  end

  keep = false(1, numel(zones));
  for k = 1:numel(zones)
    keep(k) = (zones{k}.hi - zones{k}.lo) >= o.min_zone_deg;
  end
  zones = zones(keep);
end
