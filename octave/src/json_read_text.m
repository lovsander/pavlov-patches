function txt = json_read_text(path)
% Весь файл как строка байтов (наши JSON/CSV — ASCII/UTF-8 без BOM).
  fid = fopen(path, 'r');
  if fid < 0
    error(['json_read_text: cannot open ' path]);
  end
  txt = char(fread(fid, Inf, 'uint8=>char')');
  fclose(fid);
end
