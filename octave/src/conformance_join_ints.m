function s = conformance_join_ints(v)
% Целочисленный вектор строкой для отчёта, например [4, 6, 8].
  if isempty(v)
    s = '[]';
    return;
  end
  s = ['[' strjoin(arrayfun(@(x) sprintf('%d', x), v, 'UniformOutput', false), ', ') ']'];
end
