function d = model_degrees(m)
% Степени патчей по порядку (диагностика и конформанс-вектор).
  d = zeros(1, numel(m.patches));
  for k = 1:numel(m.patches)
    d(k) = m.patches{k}.degree;
  end
end
