function v = json_nums(raw)
% Значение JSON-массива как числовая строка-вектор (парсер отдаёт массивы
% ячейками скаляров, поэтому нужна конвертация — аналог jdoubles в R-порте).
  if isnumeric(raw)
    v = double(raw(:))';
    return;
  end
  if ~iscell(raw)
    error('json_nums: expected a JSON array');
  end
  v = zeros(1, numel(raw));
  for k = 1:numel(raw)
    x = raw{k};
    if ~isnumeric(x) || ~isscalar(x)
      error('json_nums: array element is not a number');
    end
    v(k) = double(x);
  end
end
