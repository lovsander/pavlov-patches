function h = model_half_use(m)
% Полуширина окна ПРИМЕНЕНИЯ патча (полсектора + overlap_use).
  h = m.half_sector + m.options.overlap_use;
end
