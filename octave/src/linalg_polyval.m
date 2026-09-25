function y = linalg_polyval(coefs, x)
% Полином по схеме Горнера; коэффициенты по УБЫВАНИЮ степени (как polyfit).
  y = 0;
  for k = 1:numel(coefs)
    y = y * x + coefs(k);
  end
end
