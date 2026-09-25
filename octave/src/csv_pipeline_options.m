function o = csv_pipeline_options(varargin)
% Параметры пайплайна: модель + очиститель + детектор + флаги.
  o = struct('model', model_options(), 'cleaner', cleaner_options(), ...
             'detector', detector_options(), 'pits', true, 'verbose', true);
  o = pappa_nv(o, varargin);
end
