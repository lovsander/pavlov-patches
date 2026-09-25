function h = model_half_train(m)
% Полуширина ОБУЧАЮЩЕГО окна патча (полсектора + overlap_train).
  h = m.half_sector + m.options.overlap_train;
end
