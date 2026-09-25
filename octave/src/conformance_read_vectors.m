function vectors = conformance_read_vectors(dir_path)
% Векторы каталога: массив ячеек структур {file, data} по возрастанию имён
% файлов (порядок как в остальных портах).
  if ~exist(dir_path, 'dir')
    error(['no vectors directory: ' dir_path]);
  end
  d = dir(fullfile(dir_path, '*.json'));
  if isempty(d)
    error(['no vectors directory: ' dir_path]);
  end
  names = sort({d.name});
  vectors = cell(1, numel(names));
  for k = 1:numel(names)
    txt = json_read_text(fullfile(dir_path, names{k}));
    vectors{k} = struct('file', names{k}, 'data', json_parse(txt));
  end
end
