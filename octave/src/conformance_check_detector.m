function r = conformance_check_detector(v)
% Вектор вида "detector": зоны и центры ям (допуск 1e-6° для центров, число
% зон — точно).
  cfg = json_val(v, 'config', 'any');
  exp_ = json_val(v, 'expected', 'any');
  input = json_val(v, 'input', 'any');
  angles = json_val(input, 'angles_deg', 'nums');
  radii = json_val(input, 'radii_mm', 'nums');

  o = detector_options('window_deg', json_val(cfg, 'window_deg', 'num'), ...
                       'wide_deg', json_val(cfg, 'wide_deg', 'num'), ...
                       'smooth_deg', json_val(cfg, 'smooth_deg', 'num'), ...
                       'k', json_val(cfg, 'k', 'num'), ...
                       'min_zone_deg', json_val(cfg, 'min_zone_deg', 'num'));
  zs = detector_zones(angles, detector_band(angles, radii, o), o);
  exp_zones = json_val(exp_, 'zones_deg', 'list', {});
  exp_pits = json_val(exp_, 'pits_deg', 'nums');
  notes = {};

  ok = numel(zs) == numel(exp_zones);
  if ~ok
    notes{end + 1} = sprintf('zones %d != %d', numel(zs), numel(exp_zones));
  end
  dev = 0;
  for i = 1:numel(exp_zones)
    if i > numel(zs)
      break;
    end
    e = json_nums(exp_zones{i});
    dev = max(dev, max(abs(zs{i}.lo - e(1)), abs(zs{i}.hi - e(2))));
  end
  if numel(zs) ~= numel(exp_pits)
    ok = false;
    notes{end + 1} = sprintf('pits %d != %d', numel(zs), numel(exp_pits));
  end
  for i = 1:numel(exp_pits)
    if i > numel(zs)
      break;
    end
    d = abs(detector_zone_center(zs{i}) - exp_pits(i));
    dev = max(dev, d);
    if d > 1e-6
      ok = false;
    end
  end

  detail = sprintf('zones %d/%d, pits %d/%d, max|d| %s deg', numel(zs), ...
                   numel(exp_zones), numel(zs), numel(exp_pits), ...
                   conformance_sig2(dev));
  r = conformance_outcome(ok, detail, notes);
end
