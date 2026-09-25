function ok = conformance_near(a, b, rel, flr)
% Допуск «относительный с абсолютным полом»: |a−b| <= max(flr, rel·|b|).
  ok = abs(a - b) <= max(flr, rel * abs(b));
end
