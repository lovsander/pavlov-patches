function m = model_new(o, pits_deg)
% Новая (необученная) модель.
%
% ЛОВУШКА OCTAVE (архитектура порта): структуры здесь — ЗНАЧЕНИЯ, а не ссылки.
% В R модель была окружением, в Julia — mutable struct; поэтому каждый
% «мутатор» в этом порте возвращает модель обратно: m = model_fit(m, ...).
% Забыть присваивание — значит молча работать со старой моделью.
  if nargin < 1 || isempty(o)
    o = model_options();
  end
  if nargin < 2
    pits_deg = [];
  end
  m = struct();
  m.options = o;
  m.pit_shape = struct('sigma_deg', 3.0, 'core_sigma', 2.0, ...
                       'window_sigma', 3.2, 'pit_min_amp', 3e-3, ...
                       'tapering', true);
  m.pits = mod(pits_deg(:)', 360);
  m.patches = {};
  m.half_sector = 0;
  m.is_fitted = false;
end
