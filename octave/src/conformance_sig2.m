function s = conformance_sig2(x)
% Число в отчёте с двумя значащими цифрами (как format(digits = 2) в R).
  if x == 0
    s = '0';
  else
    s = sprintf('%.1e', x);
  end
end
