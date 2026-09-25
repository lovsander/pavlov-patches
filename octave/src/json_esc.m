function s = json_esc(v)
% Экранирование строки для JSON (кавычка, обратный слэш, управляющие символы).
%
% escape-последовательности собираются из ЧИСЛОВЫХ кодов: в одинарных кавычках
% Octave обратный слэш не является управляющим, но полагаться на это в коде,
% который сам печатает слэши, не стоит.
  str = char(v);
  BS = char(92);       % обратный слэш
  DQ = char(34);       % двойная кавычка
  out = '';
  for k = 1:numel(str)
    c = str(k);
    code = double(c);
    if c == DQ
      out = [out '\"'];
    elseif c == BS
      out = [out '\\'];
    elseif code == 10
      out = [out '\n'];
    elseif code == 13
      out = [out '\r'];
    elseif code == 9
      out = [out '\t'];
    elseif code < 32
      out = [out sprintf('\\u%04x', code)];
    else
      out = [out c];
    end
  end
  s = out;
end
