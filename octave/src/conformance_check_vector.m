function r = conformance_check_vector(v)
% Проверка одного вектора по его виду (kind).
  kind = json_val(v, 'kind', 'text');
  if strcmp(kind, 'model')
    r = conformance_check_model(v);
  elseif strcmp(kind, 'detector')
    r = conformance_check_detector(v);
  else
    r = conformance_check_cleaner(v);
  end
end
