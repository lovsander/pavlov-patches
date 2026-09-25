function document_write_section(path, sec)
% Записать документ одного сечения (pappa v2.0); завершающий перевод строки —
% как у остальных портов.
  json_write_text(path, [json_render(document_section_tree(sec)) char(10)]);
end
