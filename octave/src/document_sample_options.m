function o = document_sample_options(varargin)
% Параметры записи папки образца.
  o = struct('input_csv', '', 'pits', true, ...
             'description', 'PAPPA Octave port', ...
             'cleaner', cleaner_options(), 'detector', detector_options());
  o = pappa_nv(o, varargin);
end
