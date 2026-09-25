function rows = csv_load(path)
% Чтение CSV ПО ЗАГОЛОВКУ: колонки ищутся по именам, а не по позициям
% (в python/synthetic_data.csv их двенадцать, и порядок менять можно).
%
% textscan читает все колонки строками (число полей берём из заголовка), а
% нужные четыре конвертируются str2double сразу массивом — это и быстрее
% построчного разбора, и не зависит от порядка колонок.
  fid = fopen(path, 'r');
  if fid < 0
    error(['csv_load: cannot open ' path]);
  end
  header = fgetl(fid);
  if ~ischar(header)
    fclose(fid);
    error('csv_load: empty CSV');
  end
  cols = strtrim(strsplit(header, ',', 'collapsedelimiters', false));
  i_sec = find_col(cols, 'section_id');
  i_h = find_col(cols, 'height_mm');
  i_a = find_col(cols, 'angle_deg');
  i_r = find_col(cols, 'radius_mm');
  fmt = repmat('%s', 1, numel(cols));
  data = textscan(fid, fmt, 'Delimiter', ',');
  fclose(fid);

  if numel(data) < max([i_sec, i_h, i_a, i_r])
    error('csv_load: not enough data columns');
  end
  section_id = parse_col_num(data{i_sec}, 'section_id');
  height_mm = parse_col_num(data{i_h}, 'height_mm');
  angle_deg = parse_col_num(data{i_a}, 'angle_deg');
  radius_mm = parse_col_num(data{i_r}, 'radius_mm');
  if isempty(section_id)
    error('csv_load: no data rows');
  end
  if any(section_id ~= floor(section_id))
    error('csv_load: section_id is not an integer');
  end

  rows = struct('n', numel(section_id), 'section_id', section_id(:), ...
                'height_mm', height_mm(:), 'angle_deg', angle_deg(:), ...
                'radius_mm', radius_mm(:));
end

function i = find_col(cols, name)
  i = find(strcmp(cols, name), 1);
  if isempty(i)
    error(['csv_load: no column ' name]);
  end
end

function v = parse_col_num(c, name)
  if ~iscell(c)
    error(['csv_load: column ' name ' is missing']);
  end
  v = str2double(c);
  k = find(isnan(v), 1);
  if ~isempty(k)
    error(['csv_load: not a number in column ' name ': ' c{k}]);
  end
end
