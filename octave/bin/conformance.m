% Проверка Octave-порта PAPPA по конформанс-векторам.
% Запуск: octave-cli --no-gui --quiet --no-init-file octave/bin/conformance.m [каталог]
% Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога векторов.
%
% Свой каталог скрипт узнаёт через mfilename('fullpath') (аналог @__DIR__),
% аргументы после имени скрипта — из argv().
%
% ПРО КОДИРОВКУ: весь ИСПОЛНЯЕМЫЙ текст этого порта — ASCII (сообщения
% по-английски); кириллица осталась только в комментариях и в поле description
% документов (там её ждёт сверка с остальными портами). Причина та же, что у
% .ps1-файлов репозитория: консоль Windows в разных кодовых страницах иначе
% печатает мусор, а JSON-строки от этого не страдают — они пишутся байтами.

this_dir = fileparts(mfilename('fullpath'));
addpath(fullfile(this_dir, '..', 'src'));

args = argv();
if numel(args) >= 1 && ~isempty(args{1})
  vec_dir = args{1};
else
  vec_dir = fullfile(this_dir, '..', '..', 'spec', 'conformance', 'vectors');
end

exit(conformance_run(vec_dir));
