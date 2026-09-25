% Самопроверка Octave-порта PAPPA (векторы + дымовое обучение + документ).
% Запуск: octave-cli --no-gui --quiet --no-init-file octave/bin/selftest.m [каталог векторов]
% Коды:   0 — всё прошло; 1 — есть падения.
% ПРО КОДИРОВКУ: исполняемый текст — ASCII (см. bin/conformance.m).

this_dir = fileparts(mfilename('fullpath'));
addpath(fullfile(this_dir, '..', 'src'));

args = argv();
if numel(args) >= 1 && ~isempty(args{1})
  vec_dir = args{1};
else
  vec_dir = fullfile(this_dir, '..', '..', 'spec', 'conformance', 'vectors');
end

exit(selftest_run(vec_dir));
