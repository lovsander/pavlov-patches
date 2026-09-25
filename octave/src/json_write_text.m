function json_write_text(path, text)
% Запись БАЙТАМИ: Octave не переводит \n в \r\n (проверено на 11.3), но fwrite
% фиксирует это независимо от платформы — файлы совпадают с остальными портами
% побайтно, включая завершающий перевод строки.
  fid = fopen(path, 'w');
  if fid < 0
    error(['json_write_text: cannot open ' path]);
  end
  fwrite(fid, uint8(char(text)), 'uint8');
  fclose(fid);
end
