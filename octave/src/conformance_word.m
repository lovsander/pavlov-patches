function s = conformance_word(ok)
% Словесная оценка совпадения для строки отчёта.
  if ok
    s = 'match';
  else
    s = 'DIFFER';
  end
end
