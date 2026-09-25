function r = json_raw(text)
% Маркер «вставить этот фрагмент JSON как есть».
% Нужен там, где референс пишет не структуру, а готовый текст: null в поле
% detector и компактный объект cleaner в манифесте образца.
  r = struct('pappa_raw_json', char(text));
end
