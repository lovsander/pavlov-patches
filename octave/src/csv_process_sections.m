function sections = csv_process_sections(rows, opt)
% Посекционный расчёт: сортировка по углу, авто-очистка, детектор ям, обучение.
% Возвращает массив ячеек структур-сечений (для документа).
  if nargin < 2
    opt = csv_pipeline_options();
  end
  ids = unique(rows.section_id);
  sections = {};
  for si = 1:numel(ids)
    sid = ids(si);
    idx = find(rows.section_id == sid);
    % sortrows по (угол, исходный индекс) — устойчивая сортировка независимо от
    % версии Octave (её sort тоже устойчив, но полагаться на это не будем).
    [~, ord] = sortrows([rows.angle_deg(idx), (1:numel(idx))']);
    idx = idx(ord);
    n = numel(idx);
    angles = rows.angle_deg(idx);
    radii = rows.radius_mm(idx);

    cl = cleaner_clean_iqr(angles, radii, opt.cleaner);
    keep = ~cl.mask;
    a_clean = angles(keep);
    r_clean = radii(keep);

    if opt.pits
      pits = detector_pits(a_clean, r_clean, opt.detector);
    else
      pits = [];
    end
    m = model_new(opt.model, pits);

    t0 = tic;
    m = model_fit(m, a_clean, r_clean);
    fit_ms = toc(t0) * 1000;

    h = signal_round_even(rows.height_mm(idx(1)));
    if opt.verbose
      deg_str = strjoin(arrayfun(@(d) sprintf('%d', d), model_degrees(m), ...
                                 'UniformOutput', false), ', ');
      fprintf(['  section %d (h=%d mm): points %d, outliers %d, pits %d, ' ...
               'degrees [%s], fit %.1f ms\n'], ...
              sid, h, n, cl.n_outliers, numel(pits), deg_str, fit_ms);
    end

    sec = struct();
    sec.section_id = sid;
    sec.height_mm = h;
    sec.model = m;
    sec.n_points_total = n;
    sec.n_outliers = cl.n_outliers;
    sec.n_used = numel(a_clean);
    sec.fit_time_ms = fit_ms;
    sec.description = sprintf('сечение %d, h=%d мм', sid, h);
    sec.pits = pits;
    sections{end + 1} = sec;
  end
end
