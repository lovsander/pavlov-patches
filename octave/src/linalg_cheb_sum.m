function s = linalg_cheb_sum(co, deg, x)
% Σ c_k·T_k(x) по схеме Кленшоу (устойчиво).
  b1 = 0;
  b2 = 0;
  for k = deg:-1:1
    b0 = 2 * x * b1 - b2 + co(k + 1);
    b2 = b1;
    b1 = b0;
  end
  s = x * b1 - b2 + co(1);
end
