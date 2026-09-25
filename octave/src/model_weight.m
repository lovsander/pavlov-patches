function w = model_weight(m, d_deg, half_use_deg)
% Вес патча (partition of unity): 1 внутри сектора, smoothstep в перекрытии,
% 0 снаружи окна применения.
  if d_deg <= m.half_sector
    w = 1;
  elseif d_deg <= half_use_deg
    w = signal_smoothstep(1 - (d_deg - m.half_sector) / (half_use_deg - m.half_sector));
  else
    w = 0;
  end
end
