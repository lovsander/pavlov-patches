function d = signal_circ_local(a, b)
% Локальное смещение по кольцу (−180..180°); см. замечание про mod/rem в
% signal_circ_dist.
  d = mod(a - b + 180, 360) - 180;
end
