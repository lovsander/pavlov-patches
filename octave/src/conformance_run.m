function code = conformance_run(vec_dir)
% Проверка порта по конформанс-векторам (spec/conformance/vectors).
% Коды: 0 — всё сошлось, 1 — расхождения, 2 — нет каталога векторов.
  PAPPA_VERSION = '0.1.0';
  try
    vectors = conformance_read_vectors(vec_dir);
  catch err
    fprintf('no vectors directory: %s (%s)\n', vec_dir, err.message);
    code = 2;
    return;
  end

  fprintf('Octave port PAPPA: %d vectors (pappa %s, Octave %s)\n', ...
          numel(vectors), PAPPA_VERSION, version());

  bad = 0;
  for k = 1:numel(vectors)
    r = conformance_check_vector(vectors{k}.data);
    if r.ok
      tag = 'OK  ';
    else
      tag = 'FAIL';
      bad = bad + 1;
    end
    fprintf('%-46s %s %s\n', vectors{k}.file, tag, r.detail);
    for n = 1:min(4, numel(r.notes))
      fprintf('%52s-> %s\n', '', r.notes{n});
    end
  end

  if bad == 0
    fprintf('RESULT: the Octave port passes every vector\n');
    code = 0;
  else
    fprintf('RESULT: %d vector(s) differ\n', bad);
    code = 1;
  end
end
