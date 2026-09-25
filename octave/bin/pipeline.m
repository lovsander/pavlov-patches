% Пайплайн PAPPA на Octave: CSV с сечениями -> папка образца.
% Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
%   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
% Проверка: python python/studies/verify_port.py --py-dir samples/synthetic_sphere \
%                                               --cpp-dir <out-dir>
% Запуск: octave-cli --no-gui --quiet --no-init-file octave/bin/pipeline.m \
%           --input FILE.csv --out-dir DIR [--name NAME] [--description TEXT] \
%           [--no-pits] [--quiet]
%
% ПРО КОДИРОВКУ: исполняемый текст — ASCII (см. bin/conformance.m); описание
% лучше передавать ASCII-строкой, потому что кириллицу в аргументах командной
% строки Windows PowerShell портит ещё до запуска Octave.

this_dir = fileparts(mfilename('fullpath'));
addpath(fullfile(this_dir, '..', 'src'));

args = argv();
input = '';
out_dir = '';
name = 'sample';
description = 'PAPPA Octave port';
pits = true;
quiet = false;

i = 1;
while i <= numel(args)
  a = args{i};
  if strcmp(a, '--input')
    i = i + 1;
    if i <= numel(args)
      input = args{i};
    end
  elseif strcmp(a, '--out-dir')
    i = i + 1;
    if i <= numel(args)
      out_dir = args{i};
    end
  elseif strcmp(a, '--name')
    i = i + 1;
    if i <= numel(args)
      name = args{i};
    end
  elseif strcmp(a, '--description')
    i = i + 1;
    if i <= numel(args)
      description = args{i};
    end
  elseif strcmp(a, '--no-pits')
    pits = false;
  elseif strcmp(a, '--quiet')
    quiet = true;
  else
    fprintf(['PAPPA (Octave): --input FILE.csv --out-dir DIR [--name NAME] ' ...
             '[--description TEXT] [--no-pits] [--quiet]\n']);
    exit(2);
  end
  i = i + 1;
end
if isempty(input) || isempty(out_dir)
  fprintf(['PAPPA (Octave): --input FILE.csv --out-dir DIR [--name NAME] ' ...
           '[--description TEXT] [--no-pits] [--quiet]\n']);
  exit(2);
end

rows = csv_load(input);
fprintf('PAPPA (Octave): %d points, input %s\n', rows.n, input);

opt = csv_pipeline_options('pits', pits, 'verbose', ~quiet);
sections = csv_process_sections(rows, opt);

opts = document_sample_options('input_csv', input, 'pits', pits, ...
                               'description', description, ...
                               'cleaner', opt.cleaner, 'detector', opt.detector);
root = document_write_sample(out_dir, name, sections, opts);

fprintf('\n');
fprintf('sample written: %s\n', root);
fprintf('  manifest: %s\n', fullfile(root, 'sample.json'));
fprintf('  sections: %d (sections/*.pappa.json)\n', numel(sections));
fprintf('\n');
fprintf('compare with the Python reference:\n');
fprintf('  python python/studies/verify_port.py --cpp-dir %s\n', root);
exit(0);
