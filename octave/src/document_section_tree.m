function t = document_section_tree(sec)
% Дерево документа сечения (формат "pappa", версия 2.0). Порядок ключей —
% как в cpp/sample_writer.cpp; проверяется spec/check_schema.py, а числа
% сверяются python/studies/verify_port.py.
  m = sec.model;
  if ~m.is_fitted
    error('document_section_tree: model is not fitted');
  end
  if model_has_pits(m)
    method = 'PitPatchApproximator';
  else
    method = 'PatchApproximator';
  end
  opt = m.options;

  t = struct();
  t.format = 'pappa';
  t.version = '2.0';
  t.method = method;
  t.created = document_iso_now();
  t.software = struct('language', 'octave', 'pappa_version', '0.1.0');
  t.meta = struct('section_id', sec.section_id, 'height_mm', sec.height_mm, ...
                  'source', 'csv', 'description', sec.description);

  g = struct();
  g.units = struct('angle', 'degree', 'length', 'mm');
  g.n_patches = opt.n_patches;
  g.half_sector_deg = m.half_sector;
  g.phase_deg = opt.phase_deg;
  g.half_train_deg = model_half_train(m);
  g.half_use_deg = model_half_use(m);
  g.overlap_train_deg = opt.overlap_train;
  g.overlap_use_deg = opt.overlap_use;
  g.deg_min = opt.deg_min;
  g.deg_max = opt.deg_max;
  g.coord_mode = opt.coord_mode;
  g.deg_elbow_tol = opt.deg_elbow_tol;
  g.amplitude_scale = opt.amplitude_scale;
  if model_has_pits(m)
    ps = m.pit_shape;
    g.pit = struct('sigma_deg', ps.sigma_deg, 'core_sigma', ps.core_sigma, ...
                   'window_sigma', ps.window_sigma, ...
                   'pit_min_amp', ps.pit_min_amp, 'tapering', ps.tapering, ...
                   'centers_deg', m.pits(:)');
  end
  t.global = g;

  t.patches = document_patches_tree(m);
  t.statistics = struct('n_points_total', sec.n_points_total, ...
                        'n_outliers_removed', sec.n_outliers, ...
                        'fit_time_ms', sec.fit_time_ms);
end
