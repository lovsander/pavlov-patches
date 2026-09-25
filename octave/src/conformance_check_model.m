function r = conformance_check_model(v)
% Вектор вида "model": степени, коэффициенты патчей, ямные термы и контур.
% Допуски — как у остальных портов: контур 1e-6 мм, коэффициенты
% max(coefs_abs_floor, coefs_rel·|c_ожид|), смещения ям 1e-9°.
  cfg = json_val(v, 'config', 'any');
  exp_ = json_val(v, 'expected', 'any');
  tol = json_val(v, 'tolerance', 'any');
  input = json_val(v, 'input', 'any');
  notes = {};
  ok = true;

  opt = model_options('n_patches', json_val(cfg, 'n_patches', 'int'), ...
                      'phase_deg', json_val(cfg, 'phase_deg', 'num'), ...
                      'deg_min', json_val(cfg, 'deg_min', 'int'), ...
                      'deg_max', json_val(cfg, 'deg_max', 'int'), ...
                      'overlap_train', json_val(cfg, 'overlap_train', 'num'), ...
                      'overlap_use', json_val(cfg, 'overlap_use', 'num'), ...
                      'deg_elbow_tol', json_val(cfg, 'deg_elbow_tol', 'num'), ...
                      'amplitude_scale', json_val(cfg, 'amplitude_scale', 'num', 180), ...
                      'coord_mode', json_val(cfg, 'coord_mode', 'text'));
  pits_deg = json_val(cfg, 'pits_deg', 'nums');
  m = model_new(opt, pits_deg);
  if ~isempty(pits_deg)
    m.pit_shape.sigma_deg = json_val(cfg, 'sigma_deg', 'num');
    m.pit_shape.core_sigma = json_val(cfg, 'pit_core_sigma', 'num');
    m.pit_shape.window_sigma = json_val(cfg, 'pit_window_sigma', 'num');
    m.pit_shape.pit_min_amp = json_val(cfg, 'pit_min_amp', 'num');
    m.pit_shape.tapering = json_val(cfg, 'tapering', 'bool', true);
  end
  m = model_fit(m, json_val(input, 'angles_deg', 'nums'), ...
                json_val(input, 'radii_mm', 'nums'));

  want_deg = json_val(exp_, 'degrees', 'ints');
  got_deg = model_degrees(m);
  deg_ok = numel(want_deg) == numel(got_deg) && all(want_deg == got_deg);
  if ~deg_ok
    ok = false;
    notes{end + 1} = sprintf('degrees %s != %s', ...
                             conformance_join_ints(got_deg), ...
                             conformance_join_ints(want_deg));
  end

  rel = json_val(tol, 'coefs_rel', 'num');
  flr = json_val(tol, 'coefs_abs_floor', 'num');
  max_c = 0;
  bad_c = 0;
  coefs_nodes = json_val(exp_, 'coefs', 'list', {});
  for i = 1:numel(coefs_nodes)
    ref = json_nums(coefs_nodes{i});
    if i <= numel(m.patches)
      got = m.patches{i}.coefs(:)';
    else
      got = [];
    end
    if numel(got) ~= numel(ref)
      ok = false;
      bad_c = bad_c + 1;
      continue;
    end
    for j = 1:numel(ref)
      max_c = max(max_c, abs(got(j) - ref(j)));
      if ~conformance_near(got(j), ref(j), rel, flr)
        ok = false;
        bad_c = bad_c + 1;
      end
    end
  end

  max_pit = 0;
  bad_pit = 0;
  pit_nodes = json_val(exp_, 'pit_terms', 'list', {});
  for i = 1:numel(pit_nodes)
    ref_dx = json_val(pit_nodes{i}, 'dx_deg', 'nums');
    ref_amp = json_val(pit_nodes{i}, 'amp', 'nums');
    if i <= numel(m.patches)
      got_dx = m.patches{i}.pit_offsets_deg(:)';
      got_amp = m.patches{i}.pit_coefs(:)';
    else
      got_dx = [];
      got_amp = [];
    end
    if numel(got_dx) ~= numel(ref_dx)
      ok = false;
      bad_pit = bad_pit + 1;
      continue;
    end
    for j = 1:numel(ref_dx)
      da = abs(got_dx(j) - ref_dx(j));
      max_pit = max([max_pit, da, abs(got_amp(j) - ref_amp(j))]);
      if da > 1e-9 || ~conformance_near(got_amp(j), ref_amp(j), rel, flr)
        ok = false;
        bad_pit = bad_pit + 1;
      end
    end
  end

  curve = json_val(exp_, 'curve', 'any');
  ca = json_val(curve, 'angles_deg', 'nums');
  cr = json_val(curve, 'radii_mm', 'nums');
  got_curve = model_eval(m, ca);
  max_r = max(abs(got_curve(:)' - cr));
  if max_r > json_val(tol, 'curve_mm', 'num')
    ok = false;
  end

  detail = sprintf(['degrees %s, coefs max|d| %s (bad %d), pit terms max|d| %s ' ...
                    '(bad %d), curve max|d| %s mm'], conformance_word(deg_ok), ...
                   conformance_sig2(max_c), bad_c, conformance_sig2(max_pit), ...
                   bad_pit, conformance_sig2(max_r));
  r = conformance_outcome(ok, detail, notes);
end
