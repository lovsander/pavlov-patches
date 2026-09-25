function code = selftest_run(vec_dir)
% Самопроверка Octave-порта: конформанс-векторы, дымовое обучение на
% аналитическом профиле, ямный фичер и круговая проверка документа
% (записали -> разобрали обратно -> сверили контракт).
% Коды: 0 — всё прошло, 1 — есть падения.
%
% Счётчики передаются наружу и возвращаются обратно (в Octave нет ссылок):
% та же причина, по которой model_fit возвращает модель.
  PAPPA_VERSION = '0.1.0';
  if nargin < 1 || isempty(vec_dir)
    vec_dir = fullfile(fileparts(mfilename('fullpath')), '..', '..', ...
                       'spec', 'conformance', 'vectors');
  end
  passed = 0;
  failed = 0;

  fprintf('== conformance vectors ==\n');
  vectors = conformance_read_vectors(vec_dir);
  [passed, failed] = check(passed, failed, 'at least 4 vectors', numel(vectors) >= 4);
  for k = 1:numel(vectors)
    r = conformance_check_vector(vectors{k}.data);
    [passed, failed] = check(passed, failed, ...
                             sprintf('%s: %s', vectors{k}.file, r.detail), r.ok);
    for n = 1:numel(r.notes)
      fprintf('       -> %s\n', r.notes{n});
    end
  end

  fprintf('== signal utilities (numpy-compatible) ==\n');
  [passed, failed] = check(passed, failed, 'median2 of even n averages the middle two', ...
                           signal_median2([1 2 3 4]) == 2.5);
  [passed, failed] = check(passed, failed, 'median2 of odd n', signal_median2([1 2 3]) == 2);
  [passed, failed] = check(passed, failed, 'percentile 50 of [1..4] = 2.5', ...
                           signal_percentile(1:4, 50) == 2.5);
  [passed, failed] = check(passed, failed, 'percentile 0/100 = min/max', ...
                           signal_percentile(1:4, 0) == 1 && signal_percentile(1:4, 100) == 4);
  [passed, failed] = check(passed, failed, 'iqr of [1..4] = 1.5', signal_iqr2(1:4) == 1.5);
  [passed, failed] = check(passed, failed, 'circular distances', ...
                           signal_circ_dist(359, 1) == 2 && ...
                           signal_circ_local(1, 359) == 2 && ...
                           signal_circ_dist(0, 180) == 180);
  [passed, failed] = check(passed, failed, 'window 1 deg -> 3, 10 deg -> 11 points', ...
                           signal_window_points(0:359, 1) == 3 && ...
                           signal_window_points(0:359, 10) == 11);
  [passed, failed] = check(passed, failed, 'half-to-even rounding (Octave round differs)', ...
                           signal_round_even(0.5) == 0 && signal_round_even(2.5) == 2 && ...
                           signal_round_even(1.5) == 2);
  [passed, failed] = check(passed, failed, 'smoothstep at the edges and in the middle', ...
                           signal_smoothstep(-1) == 0 && signal_smoothstep(2) == 1 && ...
                           signal_smoothstep(0.5) == 0.5);
  mf = signal_median_filter([1 2 3 4 5 6 7 8 9], 3);
  [passed, failed] = check(passed, failed, 'median filter window is centred on the point', ...
                           mf(5) == 5 && mf(1) == 2);
  sm = signal_smooth_wrap([1 2 3 4 5 6 7 8 9], 3);
  [passed, failed] = check(passed, failed, 'ring smoothing is centred too', ...
                           abs(sm(5) - 5) < 1e-12);

  fprintf('== linear algebra ==\n');
  xs = [-2 -1 0 1 2];
  co = linalg_polyfit(xs, 2 + 3 * xs, 1);
  [passed, failed] = check(passed, failed, 'polyfit of a line gives [3, 2]', ...
                           max(abs(co - [3; 2])) < 1e-12);
  [passed, failed] = check(passed, failed, 'polyval (decreasing degree) 2*10 + 3 = 23', ...
                           abs(linalg_polyval([2; 3], 10) - 23) < 1e-12);
  [passed, failed] = check(passed, failed, 'cheb_sum equals the Chebyshev matrix sum', ...
                           abs(linalg_cheb_sum([1 2 3 4], 3, 0.3) - ...
                               sum([1 2 3 4] .* linalg_cheb_row(0.3, 3))) < 1e-12);

  fprintf('== JSON: writing and parsing ==\n');
  nums = [0.1, 24.75, -3.5, 1e-12, 15, 1e15];
  ok_nums = true;
  for k = 1:numel(nums)
    ok_nums = ok_nums && (str2double(json_num(nums(k))) == nums(k));
  end
  [passed, failed] = check(passed, failed, 'json_num round-trips six numbers', ok_nums);
  [passed, failed] = check(passed, failed, 'json_num: zero and integers without a fraction', ...
                           strcmp(json_num(0), '0') && strcmp(json_num(15), '15') && ...
                           strcmp(json_num(24.75), '24.75'));
  [passed, failed] = check(passed, failed, 'json_esc escapes quote and newline', ...
                           strcmp(json_esc(['a"b' char(10) 'c']), ['a\"b\nc']));
  doc = json_parse('{"a": [1, 2.5, true, null, "x\ny"], "b": {"c": -0.5}}');
  [passed, failed] = check(passed, failed, 'nested object and array are parsed', ...
                           numel(doc.a) == 5 && json_val(doc.b, 'c', 'num') == -0.5 && ...
                           islogical(doc.a{3}) && doc.a{3} && isempty(doc.a{4}));
  [passed, failed] = check(passed, failed, 'escaped newline inside a string', ...
                           strcmp(doc.a{5}, ['x' char(10) 'y']));
  rendered = json_render(struct('z', 1, 'a', json_raw('null')));
  [passed, failed] = check(passed, failed, 'json_render keeps field order and raw values', ...
                           strcmp(rendered, ['{' char(10) '  "z": 1,' char(10) ...
                                             '  "a": null' char(10) '}']));

  fprintf('== cleaner and detector boundaries ==\n');
  cl = cleaner_clean_iqr(0:9, repmat(40, 1, 10), cleaner_options('baseline_deg', 10));
  [passed, failed] = check(passed, failed, 'below min_points the cleaner is off', ...
                           cl.n_outliers == 0 && cl.window == 0);
  mask = false(1, 360);
  mask(11:21) = true;                        % углы 10..20
  zs = detector_mask_to_zones(0:359, mask, detector_options('min_zone_deg', 1));
  [passed, failed] = check(passed, failed, 'zone from a mask: half a step around the ends', ...
                           numel(zs) == 1 && abs(zs{1}.lo - 9.5) < 1e-12 && ...
                           abs(zs{1}.hi - 20.5) < 1e-12);
  ring = false(1, 360);
  ring([1:3, 358:360]) = true;               % через 0°: одна зона
  zs = detector_mask_to_zones(0:359, ring, detector_options('min_zone_deg', 1));
  [passed, failed] = check(passed, failed, 'a zone crossing 0 deg is merged', numel(zs) == 1);

  fprintf('== smooth sinusoid is reproduced ==\n');
  angles = 0:359;
  radii = 50 + 0.4 * sin(angles * pi / 180);
  m = model_new();
  m = model_fit(m, angles, radii);
  [passed, failed] = check(passed, failed, '7 patches', numel(m.patches) == 7);
  curve = model_eval(m, angles);
  max_dev = max(abs(curve(:)' - radii));
  [passed, failed] = check(passed, failed, ...
      sprintf('curve matches better than 1e-6 mm (max|d| = %.2e)', max_dev), max_dev < 1e-6);

  fprintf('== pit feature and document contract ==\n');
  % Ямы видны только на фоне высокочастотной подложки: на идеально гладком
  % профиле робастная sigma самого индикатора ~ 0, и нормировка обнуляет band
  % (та же ловушка, что описана в spec/conformance/README.md для вектора 03).
  ripple = 0.02 * sin(2 * pi * angles / 7);
  dips = 0.5 * exp(-((angles - 90) / 1.2) .^ 2) + ...
         0.5 * exp(-((angles - 210) / 1.2) .^ 2);
  pitted = radii + ripple - dips;
  pits = detector_pits(angles, pitted, detector_options());
  [passed, failed] = check(passed, failed, ...
      sprintf('detector finds 2 pits (got %d)', numel(pits)), numel(pits) == 2);
  ok_centres = numel(pits) == 2 && min(abs(pits - 90)) <= 2 && min(abs(pits - 210)) <= 2;
  [passed, failed] = check(passed, failed, 'pit centres land within 2 deg of the dips', ...
                           ok_centres);
  mp = model_new(model_options(), pits);
  mp = model_fit(mp, angles, pitted);
  kept = 0;
  for k = 1:numel(mp.patches)
    kept = kept + numel(mp.patches{k}.pit_offsets_deg);
  end
  [passed, failed] = check(passed, failed, ...
      sprintf('pit terms survive the amplitude cut (%d kept)', kept), kept > 0);

  csv_path = fullfile(tempdir(), 'pappa_octave_smoke.csv');
  lines = cell(1, 361);
  lines{1} = 'section_id,height_mm,angle_deg,radius_mm';
  for k = 1:360
    lines{k + 1} = sprintf('0,7.5,%d,%.10f', k - 1, pitted(k));
  end
  json_write_text(csv_path, [strjoin(lines, char(10)) char(10)]);
  rows = csv_load(csv_path);
  [passed, failed] = check(passed, failed, 'four-column CSV: all 360 rows are read', rows.n == 360);
  [passed, failed] = check(passed, failed, 'height column maps by NAME, not position', ...
                           rows.height_mm(1) == 7.5);
  sections = csv_process_sections(rows, csv_pipeline_options('verbose', false));
  [passed, failed] = check(passed, failed, 'one section is produced', numel(sections) == 1);

  out = tempname();
  document_write_sample(out, 'smoke', sections, ...
                        document_sample_options('input_csv', csv_path));
  manifest = json_read_text(fullfile(out, 'sample.json'));
  section_txt = json_read_text(fullfile(out, 'sections', '00.pappa.json'));
  [passed, failed] = check(passed, failed, 'manifest: format pappa-sample', ...
                           ~isempty(strfind(manifest, '"format": "pappa-sample"')));
  [passed, failed] = check(passed, failed, 'section: format pappa', ...
                           ~isempty(strfind(section_txt, '"format": "pappa"')));
  [passed, failed] = check(passed, failed, 'section: method names the pit variant', ...
                           ~isempty(strfind(section_txt, '"PitPatchApproximator"')));
  [passed, failed] = check(passed, failed, 'section: statistics block present', ...
                           ~isempty(strfind(section_txt, '"statistics"')));
  want_terms = 0;
  if model_has_pits(sections{1}.model)
    want_terms = numel(sections{1}.model.patches);
  end
  got_terms = numel(strfind(section_txt, '"pit_terms"'));
  [passed, failed] = check(passed, failed, ...
      sprintf('pit_terms key on every patch (%d)', got_terms), got_terms == want_terms);
  [passed, failed] = check(passed, failed, 'no CRLF in the written file', ...
                           isempty(strfind(manifest, char(13))));
  parsed = json_parse(manifest);
  [passed, failed] = check(passed, failed, 'manifest parses back', ...
                           strcmp(json_val(parsed, 'name', 'text'), 'smoke'));
  parsed_sec = json_parse(section_txt);
  [passed, failed] = check(passed, failed, 'section document parses back', ...
                           numel(json_val(parsed_sec, 'patches', 'list')) == 7);
  [passed, failed] = check(passed, failed, 'JSON null becomes an empty value', ...
                           isempty(json_val(json_val(parsed, 'config', 'any'), 'detector', 'any')));
  sw = json_val(parsed_sec, 'software', 'any');
  [passed, failed] = check(passed, failed, 'software block records the port', ...
                           strcmp(json_val(sw, 'language', 'text'), 'octave') && ...
                           strcmp(json_val(sw, 'pappa_version', 'text'), PAPPA_VERSION));

  fprintf('\nTotal: %d OK, %d FAIL\n', passed, failed);
  if failed == 0
    fprintf('RESULT: the Octave port passes its self-test\n');
    code = 0;
  else
    fprintf('RESULT: %d check(s) failed\n', failed);
    code = 1;
  end
end

function [passed, failed] = check(passed, failed, name, cond)
% Печать одной проверки и подсчёт итогов (счётчики возвращаются наружу:
% в Octave нет ссылок — см. model_fit).
  if cond
    passed = passed + 1;
    fprintf('  OK   %s\n', name);
  else
    failed = failed + 1;
    fprintf('  FAIL %s\n', name);
  end
end
