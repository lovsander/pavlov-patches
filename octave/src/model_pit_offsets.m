function dx = model_pit_offsets(m, center_deg, half_win_deg)
% Смещения видимых ям в локальной системе патча (°).
  if isempty(m.pits)
    dx = [];
    return;
  end
  d = signal_circ_local(m.pits, center_deg);
  dx = d(abs(d) <= half_win_deg);
end
