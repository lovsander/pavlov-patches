function out_dir = document_write_sample(out_dir, name, sections, o)
% Записать папку образца — тот же контракт, что у Python/C++/C/Go/JS/Java/
% Kotlin/Rust/Pascal/Swift/Julia/R/C#:
%     <out_dir>/sample.json              манифест (format pappa-sample v1.0)
%     <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
  if nargin < 4
    o = document_sample_options();
  end
  sec_dir = fullfile(out_dir, 'sections');
  if ~exist(sec_dir, 'dir')
    mkdir(sec_dir);
  end

  if ~isempty(sections)
    ids = zeros(1, numel(sections));
    for k = 1:numel(sections)
      ids(k) = sections{k}.section_id;
    end
    [~, ord] = sortrows([ids(:), (1:numel(sections))']);
    sections = sections(ord);
  end
  if isempty(sections)
    fm = [];
  else
    fm = sections{1}.model;
  end

  t = struct();
  t.format = 'pappa-sample';
  t.version = '1.0';
  t.name = name;
  t.created = document_iso_now();
  t.units = struct('angle', 'degree', 'length', 'mm');
  t.meta = struct('description', o.description);
  if ~isempty(o.input_csv)
    t.input = struct('csv', o.input_csv);
  end

  cfg = struct();
  cfg.n_patches = gopt(fm, 'n_patches', 0);
  cfg.phase_deg = gopt(fm, 'phase_deg', 0);
  cfg.deg_min = gopt(fm, 'deg_min', 0);
  cfg.deg_max = gopt(fm, 'deg_max', 0);
  cfg.overlap_train = gopt(fm, 'overlap_train', 0);
  cfg.overlap_use = gopt(fm, 'overlap_use', 0);
  cfg.deg_elbow_tol = gopt(fm, 'deg_elbow_tol', 0);
  % Компактный объект cleaner — ОДНОЙ строкой, как в cpp/sample_writer.cpp,
  % поэтому значение вставляется дословно (json_raw).
  cfg.cleaner = json_raw(sprintf( ...
      '{"mode": "auto", "auto": {"method": "iqr", "baseline_deg": %s, "iqr_k": %s}}', ...
      json_num(o.cleaner.baseline_deg), json_num(o.cleaner.iqr_k)));
  cfg.pits = o.pits;
  if o.pits && ~isempty(fm)
    ps = fm.pit_shape;
    cfg.sigma_deg = ps.sigma_deg;
    cfg.pit_core_sigma = ps.core_sigma;
    cfg.pit_window_sigma = ps.window_sigma;
    cfg.pit_min_amp = ps.pit_min_amp;
    cfg.tapering = ps.tapering;
  end
  cfg.detector = json_raw('null');
  t.config = cfg;

  list = cell(1, numel(sections));
  for i = 1:numel(sections)
    s = sections{i};
    file = sprintf('sections/%02d.pappa.json', i - 1);
    document_write_section(fullfile(out_dir, file), s);
    e = struct();
    e.index = i - 1;
    e.section_id = s.section_id;
    e.height_mm = s.height_mm;
    e.file = file;
    e.n_points = s.n_points_total;
    e.n_outliers = s.n_outliers;
    list{i} = e;
  end
  t.sections = list;

  json_write_text(fullfile(out_dir, 'sample.json'), [json_render(t) char(10)]);
end

function v = gopt(fm, name, def)
% Значение параметра модели для манифеста (или запасное, если модели нет).
  if isempty(fm)
    v = def;
  else
    v = fm.options.(name);
  end
end
